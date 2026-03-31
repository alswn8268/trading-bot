"""
자동 매매봇 핵심 엔진
- 전략 신호 수신 → 리스크 체크 → 주문 실행 → 포지션 관리 → 상태 기록
"""
import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional
import yaml

from exchanges import KISExchange, UpbitExchange, BinanceExchange
from strategies import get_strategy
from strategies.base import Signal
from notifier import create_notifier
import database as db

logger = logging.getLogger("bot")


class TradingBot:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)

        self.mode = self.cfg["mode"]          # paper | live
        self.risk = self.cfg["risk"]
        self.running = False

        # 로그 / 신호 (웹소켓 전송용)
        self.logs: list[dict] = []
        self.signals: list[dict] = []

        # 포지션 추적: "exchange:symbol" → {symbol, exchange, qty, avg_price, ...}
        self.positions: dict[str, dict] = {}

        # 손익 / 거래 통계
        self.daily_pnl: float = 0.0
        self.realized_pnl: float = 0.0
        self.trade_count: int = 0

        self._ws_callback: Optional[Callable] = None

        self._init_exchanges()
        self._init_strategies()
        self.notifier = create_notifier(self.cfg)
        db.init_db()
        logger.info(f"봇 초기화 완료 | 모드: {self.mode.upper()}")

    # ── 초기화 ───────────────────────────────────────
    def _init_exchanges(self):
        self.kis: Optional[KISExchange] = None
        self.upbit: Optional[UpbitExchange] = None
        self.binance: Optional[BinanceExchange] = None

        kc = self.cfg.get("kis", {})
        if kc.get("app_key") and kc["app_key"] != "YOUR_KIS_APP_KEY":
            self.kis = KISExchange(kc["app_key"], kc["app_secret"],
                                   kc["account_no"], kc.get("is_paper", True))
            logger.info("KIS 연결됨")

        uc = self.cfg.get("upbit", {})
        if uc.get("access_key") and uc["access_key"] != "YOUR_UPBIT_ACCESS_KEY":
            self.upbit = UpbitExchange(uc["access_key"], uc["secret_key"])
            logger.info("Upbit 연결됨")

        bc = self.cfg.get("binance", {})
        if bc.get("api_key") and bc["api_key"] != "YOUR_BINANCE_API_KEY":
            self.binance = BinanceExchange(bc["api_key"], bc["api_secret"],
                                           bc.get("testnet", True))
            logger.info("Binance 연결됨")

    def _init_strategies(self):
        self.tasks: list[dict] = []
        strat_params = self.cfg.get("strategies", {})

        for item in self.cfg["trading"].get("stocks", []):
            s_name = item["strategy"]
            params = strat_params.get(s_name, {})
            self.tasks.append({
                "exchange": "kis", "symbol": item["symbol"],
                "amount": item["amount"],
                "strategy": get_strategy(s_name, item["symbol"], params),
                "interval": params.get("interval", "1d"),
            })

        for item in self.cfg["trading"].get("upbit_coins", []):
            s_name = item["strategy"]
            params = strat_params.get(s_name, {})
            self.tasks.append({
                "exchange": "upbit", "symbol": item["symbol"],
                "amount": item["amount"],
                "strategy": get_strategy(s_name, item["symbol"], params),
                "interval": params.get("interval", "1h"),
            })

        for item in self.cfg["trading"].get("binance_coins", []):
            s_name = item["strategy"]
            params = strat_params.get(s_name, {})
            self.tasks.append({
                "exchange": "binance", "symbol": item["symbol"],
                "amount": item["amount"],
                "strategy": get_strategy(s_name, item["symbol"], params),
                "interval": params.get("interval", "1d"),
            })

        logger.info(f"전략 {len(self.tasks)}개 로드됨")

    # ── OHLCV 조회 ───────────────────────────────────
    async def _fetch_ohlcv(self, task: dict):
        import pandas as pd
        exchange = task["exchange"]
        symbol   = task["symbol"]
        interval = task["interval"]
        loop = asyncio.get_running_loop()

        if exchange == "kis" and self.kis:
            period = {"1d": "D", "1w": "W", "1m": "M"}.get(interval, "D")
            return await loop.run_in_executor(None, self.kis.get_ohlcv, symbol, period, 100)

        if exchange == "upbit" and self.upbit:
            iv = {"1d": "days", "1h": "minutes/60", "15m": "minutes/15"}.get(interval, "days")
            return await loop.run_in_executor(None, self.upbit.get_ohlcv, symbol, iv, 200)

        if exchange == "binance" and self.binance:
            return await loop.run_in_executor(None, self.binance.get_ohlcv, symbol, interval, 200)

        # 거래소 미연결: 더미 데이터 (대시보드 테스트용)
        import numpy as np
        dates = pd.date_range(end=datetime.now(), periods=50)
        close = pd.Series(np.random.randn(50).cumsum() + 100)
        return pd.DataFrame({
            "date": dates, "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": 1000,
        })

    # ── 포지션 관리 ──────────────────────────────────
    def _enter_position(self, signal: Signal, task: dict):
        key    = f"{task['exchange']}:{signal.symbol}"
        amount = task["amount"]
        qty    = amount / signal.price if signal.price > 0 else 0

        if key in self.positions:
            pos = self.positions[key]
            total_qty = pos["qty"] + qty
            pos["avg_price"] = (pos["avg_price"] * pos["qty"] + signal.price * qty) / total_qty
            pos["qty"]       = total_qty
            pos["invested"] += amount
        else:
            self.positions[key] = {
                "symbol":         signal.symbol,
                "exchange":       task["exchange"].upper(),
                "qty":            qty,
                "avg_price":      signal.price,
                "current_price":  signal.price,
                "invested":       amount,
                "unrealized_pnl": 0.0,
                "entry_time":     datetime.now().strftime("%H:%M:%S"),
            }
        self.trade_count += 1

    def _exit_position(self, signal: Signal, task: dict) -> float:
        key = f"{task['exchange']}:{signal.symbol}"
        if key not in self.positions:
            return 0.0

        pos     = self.positions[key]
        avg     = pos["avg_price"]
        pnl_pct = (signal.price - avg) / avg * 100 if avg > 0 else 0.0

        self.realized_pnl += pnl_pct
        self.daily_pnl     = self.realized_pnl
        self.trade_count  += 1
        del self.positions[key]

        self._log("INFO", signal.symbol,
                  f"청산 완료 | 진입 {avg:,.0f} → 현재 {signal.price:,.0f} | 손익 {pnl_pct:+.2f}%")
        return pnl_pct

    def _update_position_price(self, task: dict, current_price: float):
        key = f"{task['exchange']}:{task['symbol']}"
        if key not in self.positions:
            return
        pos = self.positions[key]
        pos["current_price"] = current_price
        avg = pos["avg_price"]
        pos["unrealized_pnl"] = (current_price - avg) / avg * 100 if avg > 0 else 0.0

    def _check_risk_exit(self, task: dict, current_price: float) -> Optional[Signal]:
        key = f"{task['exchange']}:{task['symbol']}"
        if key not in self.positions:
            return None

        avg        = self.positions[key]["avg_price"]
        change_pct = (current_price - avg) / avg * 100 if avg > 0 else 0.0

        if change_pct <= -self.risk["max_loss_pct"]:
            return Signal(
                "SELL", task["symbol"], current_price,
                f"손절 발동 ({change_pct:+.2f}%, 한도 -{self.risk['max_loss_pct']}%)", 1.0,
            )
        if change_pct >= self.risk["take_profit_pct"]:
            return Signal(
                "SELL", task["symbol"], current_price,
                f"익절 발동 ({change_pct:+.2f}%, 목표 +{self.risk['take_profit_pct']}%)", 1.0,
            )
        return None

    # ── 메인 사이클 ──────────────────────────────────
    async def run_cycle(self):
        for task in self.tasks:
            try:
                df = await self._fetch_ohlcv(task)
                if df.empty or len(df) < 2:
                    self._log("WARN", task["symbol"], "데이터 부족 — 스킵")
                    continue

                current_price = float(df["close"].iloc[-1])

                self._update_position_price(task, current_price)

                forced = self._check_risk_exit(task, current_price)
                if forced:
                    await self._process_signal(forced, task)
                    continue

                signal = task["strategy"].analyze(df)
                await self._process_signal(signal, task)

            except Exception as e:
                self._log("ERROR", task["symbol"], f"오류: {e}")

    async def _process_signal(self, signal: Signal, task: dict):
        self.signals.insert(0, {
            "time":       datetime.now().strftime("%H:%M:%S"),
            "exchange":   task["exchange"].upper(),
            "symbol":     signal.symbol,
            "action":     signal.action,
            "price":      signal.price,
            "reason":     signal.reason,
            "confidence": f"{signal.confidence * 100:.0f}%",
        })
        self.signals = self.signals[:50]

        if signal.action == "HOLD":
            return

        if self.daily_pnl < -self.risk["daily_loss_limit"]:
            self._log("WARN", signal.symbol,
                      f"일일 손실 한도 초과 ({self.daily_pnl:.2f}%) — 주문 차단")
            return

        self._log(signal.action, signal.symbol,
                  f"{signal.action} @ {signal.price:,.0f} | {signal.reason} | "
                  f"신뢰도 {signal.confidence:.0%}")

        pos_key = f"{task['exchange']}:{signal.symbol}"

        if signal.action == "BUY":
            # 이미 포지션이 있으면 중복 매수 방지
            if pos_key in self.positions:
                self._log("INFO", signal.symbol, f"BUY 신호 무시 — 포지션 이미 보유 중")
                return
            self._enter_position(signal, task)
            db.record_trade(
                exchange=task["exchange"], symbol=signal.symbol,
                action="BUY", price=signal.price, amount=task["amount"],
                reason=signal.reason, confidence=signal.confidence, mode=self.mode,
            )
            self.notifier.on_signal(
                signal.action, signal.symbol, signal.price,
                signal.reason, signal.confidence, task["exchange"].upper()
            )
        elif signal.action == "SELL":
            # 포지션이 없으면 SELL 무시 (허공 매도 방지)
            if pos_key not in self.positions:
                self._log("INFO", signal.symbol, f"SELL 신호 무시 — 보유 포지션 없음")
                return
            pnl = self._exit_position(signal, task)
            db.record_trade(
                exchange=task["exchange"], symbol=signal.symbol,
                action="SELL", price=signal.price, amount=task["amount"],
                pnl=pnl, reason=signal.reason, confidence=signal.confidence, mode=self.mode,
            )
            if "손절" in signal.reason or "익절" in signal.reason:
                self.notifier.on_risk_exit(
                    signal.symbol, signal.price, signal.reason, task["exchange"].upper()
                )
            else:
                self.notifier.on_signal(
                    signal.action, signal.symbol, signal.price,
                    signal.reason, signal.confidence, task["exchange"].upper()
                )

        if self.mode == "paper":
            self._log("PAPER", signal.symbol,
                      f"[모의] {signal.action} @ {signal.price:,.0f} (실제 주문 없음)")
            await self._notify_ws()
            return

        try:
            await self._execute_order(signal, task)
        except Exception as e:
            self._log("ERROR", signal.symbol, f"주문 실패: {e}")

        await self._notify_ws()

    async def _execute_order(self, signal: Signal, task: dict):
        exchange = task["exchange"]
        amount   = task["amount"]
        loop     = asyncio.get_running_loop()

        if exchange == "kis" and self.kis:
            qty = max(1, int(amount / signal.price))
            if signal.action == "BUY":
                await loop.run_in_executor(None, self.kis.buy, signal.symbol, qty)
            else:
                await loop.run_in_executor(None, self.kis.sell, signal.symbol, qty)

        elif exchange == "upbit" and self.upbit:
            if signal.action == "BUY":
                await loop.run_in_executor(None, self.upbit.buy_market, signal.symbol, amount)
            else:
                qty = amount / signal.price
                await loop.run_in_executor(None, self.upbit.sell_market, signal.symbol, qty)

        elif exchange == "binance" and self.binance:
            if signal.action == "BUY":
                await loop.run_in_executor(None, self.binance.buy_market, signal.symbol, amount)
            else:
                qty = amount / signal.price
                await loop.run_in_executor(None, self.binance.sell_market, signal.symbol, qty)

    # ── 메인 루프 ────────────────────────────────────
    async def start(self):
        self.running = True
        self._log("INFO", "시스템",
                  f"봇 시작 | 모드: {self.mode.upper()} | 전략 {len(self.tasks)}개")
        self.notifier.on_bot_start(self.mode.upper(), len(self.tasks))
        while self.running:
            await self.run_cycle()
            await self._notify_ws()
            await asyncio.sleep(60)   # 1분 사이클

    def stop(self):
        self.running = False
        self._log("INFO", "시스템", "봇 중지됨")
        self.notifier.on_bot_stop()

    # ── 유틸 ─────────────────────────────────────────
    def _log(self, level: str, symbol: str, msg: str):
        entry = {
            "time":    datetime.now().strftime("%H:%M:%S"),
            "level":   level,
            "symbol":  symbol,
            "message": msg,
        }
        self.logs.insert(0, entry)
        self.logs = self.logs[:200]
        logger.info(f"[{level}] {symbol}: {msg}")

    async def _notify_ws(self):
        if self._ws_callback:
            await self._ws_callback()

    def get_status(self) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        today_stats = db.get_stats(since_date=today)
        return {
            "running":        self.running,
            "mode":           self.mode,
            "task_count":     len(self.tasks),
            "daily_pnl":      today_stats.get("total_pnl", self.daily_pnl),
            "realized_pnl":   today_stats.get("total_pnl", self.realized_pnl),
            "trade_count":    today_stats.get("total_trades", self.trade_count),
            "position_count": len(self.positions),
            "logs":           self.logs[:30],
            "signals":        self.signals[:20],
            "positions":      list(self.positions.values()),
            "exchanges": {
                "kis":     self.kis     is not None,
                "upbit":   self.upbit   is not None,
                "binance": self.binance is not None,
            },
            "risk_config": self.risk,
            "tasks": [
                {
                    "exchange": t["exchange"],
                    "symbol":   t["symbol"],
                    "strategy": t["strategy"].__class__.__name__,
                    "interval": t["interval"],
                    "amount":   t["amount"],
                }
                for t in self.tasks
            ],
        }
