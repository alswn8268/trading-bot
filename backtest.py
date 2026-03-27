"""
백테스트 엔진
- 전략 객체 + OHLCV DataFrame → 매매 시뮬레이션
- 슬라이딩 윈도우: 각 봉마다 그 시점까지의 데이터만 전달
- 수수료, 손절/익절 적용
- 결과: 거래 목록, 수익률 곡선, 통계 요약
"""
import copy
import logging
import pandas as pd
import numpy as np
from typing import Optional
from strategies import get_strategy

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# 결과 데이터클래스 (dict 반환으로 JSON 직렬화 용이)
# ──────────────────────────────────────────────────────────
def _empty_result(symbol: str, strategy_name: str, reason: str) -> dict:
    return {
        "symbol": symbol,
        "strategy": strategy_name,
        "error": reason,
        "trades": [],
        "equity_curve": [],
        "stats": {},
    }


# ──────────────────────────────────────────────────────────
# 핵심 엔진
# ──────────────────────────────────────────────────────────
def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    strategy_name: str,
    strategy_params: dict,
    initial_capital: float = 1_000_000,
    fee_rate: float = 0.0005,          # 편도 수수료 0.05%
    max_loss_pct: float = 3.0,         # 손절 %
    take_profit_pct: float = 5.0,      # 익절 %
    position_size_pct: float = 100.0,  # 한 번에 사용할 자본 비율 (%)
) -> dict:
    """
    df: OHLCV DataFrame (columns: date, open, high, low, close, volume)
        — 과거순 정렬 (오래된 것 먼저)
    Returns: dict with trades, equity_curve, stats
    """
    required_cols = {"date", "open", "high", "low", "close", "volume"}
    if not required_cols.issubset(df.columns):
        return _empty_result(symbol, strategy_name, f"필수 컬럼 없음: {required_cols - set(df.columns)}")

    df = df.reset_index(drop=True)
    if len(df) < 30:
        return _empty_result(symbol, strategy_name, "데이터 부족 (최소 30행)")

    # 전략 인스턴스 생성
    try:
        strategy = get_strategy(strategy_name, symbol, strategy_params)
    except ValueError as e:
        return _empty_result(symbol, strategy_name, str(e))

    capital     = initial_capital
    position    = 0.0    # 보유 수량
    avg_price   = 0.0    # 평균 매수가
    trades      = []
    equity      = []

    for i in range(1, len(df)):
        window = df.iloc[: i + 1].copy()
        current_price = float(window["close"].iloc[-1])
        current_date  = str(window["date"].iloc[-1])

        # ── 포지션 있을 때 손절/익절 먼저 확인 ──────────────
        if position > 0 and avg_price > 0:
            change_pct = (current_price - avg_price) / avg_price * 100
            forced_exit = None
            if change_pct <= -max_loss_pct:
                forced_exit = f"손절 ({change_pct:+.2f}%)"
            elif change_pct >= take_profit_pct:
                forced_exit = f"익절 ({change_pct:+.2f}%)"

            if forced_exit:
                proceeds  = position * current_price * (1 - fee_rate)
                cost_base = position * avg_price * (1 + fee_rate)
                pnl       = proceeds - cost_base
                capital  += proceeds
                trades.append({
                    "date":   current_date,
                    "action": "SELL",
                    "price":  current_price,
                    "qty":    round(position, 6),
                    "pnl":    round(pnl, 2),
                    "reason": forced_exit,
                })
                position  = 0.0
                avg_price = 0.0

        # ── 전략 분석 ─────────────────────────────────────
        try:
            signal = strategy.analyze(window)
        except Exception as e:
            logger.debug(f"[Backtest] {symbol} i={i} 신호 오류: {e}")
            equity.append({"date": current_date,
                           "equity": round(capital + position * current_price, 2)})
            continue

        # ── 매수 ──────────────────────────────────────────
        if signal.action == "BUY" and position == 0 and capital > 0:
            invest    = capital * (position_size_pct / 100)
            fee       = invest * fee_rate
            qty       = (invest - fee) / current_price
            capital  -= invest
            position  = qty
            avg_price = current_price
            trades.append({
                "date":   current_date,
                "action": "BUY",
                "price":  current_price,
                "qty":    round(qty, 6),
                "pnl":    0.0,
                "reason": signal.reason,
            })

        # ── 매도 ──────────────────────────────────────────
        elif signal.action == "SELL" and position > 0:
            proceeds  = position * current_price * (1 - fee_rate)
            cost_base = position * avg_price * (1 + fee_rate)
            pnl       = proceeds - cost_base
            capital  += proceeds
            trades.append({
                "date":   current_date,
                "action": "SELL",
                "price":  current_price,
                "qty":    round(position, 6),
                "pnl":    round(pnl, 2),
                "reason": signal.reason,
            })
            position  = 0.0
            avg_price = 0.0

        equity.append({
            "date":   current_date,
            "equity": round(capital + position * current_price, 2),
        })

    # ── 미청산 포지션 강제 청산 ───────────────────────────
    if position > 0:
        last_price = float(df["close"].iloc[-1])
        proceeds   = position * last_price * (1 - fee_rate)
        cost_base  = position * avg_price * (1 + fee_rate)
        pnl        = proceeds - cost_base
        capital   += proceeds
        trades.append({
            "date":   str(df["date"].iloc[-1]),
            "action": "SELL",
            "price":  last_price,
            "qty":    round(position, 6),
            "pnl":    round(pnl, 2),
            "reason": "백테스트 종료 청산",
        })

    # ── 통계 계산 ─────────────────────────────────────────
    stats = _calc_stats(trades, initial_capital, equity)

    return {
        "symbol":       symbol,
        "strategy":     strategy_name,
        "trades":       trades,
        "equity_curve": equity,
        "stats":        stats,
    }


def _calc_stats(trades: list, initial_capital: float, equity: list) -> dict:
    sell_trades = [t for t in trades if t["action"] == "SELL"]
    if not sell_trades:
        return {
            "total_trades": 0, "win_trades": 0, "loss_trades": 0,
            "win_rate": 0, "total_pnl": 0, "total_return_pct": 0,
            "avg_win": 0, "avg_loss": 0, "profit_factor": 0,
            "max_drawdown_pct": 0,
        }

    total    = len(sell_trades)
    wins     = [t["pnl"] for t in sell_trades if t["pnl"] > 0]
    losses   = [t["pnl"] for t in sell_trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in sell_trades)

    win_rate = len(wins) / total * 100 if total else 0
    avg_win  = np.mean(wins)   if wins   else 0.0
    avg_loss = np.mean(losses) if losses else 0.0
    profit_factor = (
        abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0.0
    )

    # 최대 낙폭
    eq_values   = [e["equity"] for e in equity]
    peak        = initial_capital
    max_dd      = 0.0
    for v in eq_values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    final_equity   = eq_values[-1] if eq_values else initial_capital
    total_return   = (final_equity - initial_capital) / initial_capital * 100

    return {
        "total_trades":      total,
        "win_trades":        len(wins),
        "loss_trades":       len(losses),
        "win_rate":          round(win_rate, 1),
        "total_pnl":         round(total_pnl, 2),
        "total_return_pct":  round(total_return, 2),
        "avg_win":           round(float(avg_win), 2),
        "avg_loss":          round(float(avg_loss), 2),
        "profit_factor":     round(float(profit_factor), 2),
        "max_drawdown_pct":  round(max_dd, 2),
        "initial_capital":   initial_capital,
        "final_equity":      round(final_equity, 2),
    }
