"""
변동성 돌파 전략 (Volatility Breakout)
- 코인 단타에서 가장 검증된 전략 중 하나
- 매수 목표가 = 오늘 시가 + (전날 고가 - 전날 저가) × k
- 현재가가 목표가 돌파 → 매수
- 다음날 시가에 무조건 청산
- MA 필터로 하락장 진입 방지
"""
from typing import Optional
import pandas as pd
from .base import BaseStrategy, Signal


class VolatilityBreakoutStrategy(BaseStrategy):
    def __init__(self, symbol: str, params: dict):
        super().__init__(symbol, params)
        self._bought_date: Optional[str] = None   # 매수한 날짜 기록

    def _get_date_str(self, ts) -> str:
        """날짜를 'YYYY-MM-DD' 문자열로 통일"""
        try:
            return str(pd.Timestamp(ts).date())
        except Exception:
            return str(ts)[:10]

    def analyze(self, df: pd.DataFrame) -> Signal:
        k             = self.params.get("k", 0.5)           # 변동성 배수 (낮을수록 신호 많음)
        use_ma_filter = self.params.get("use_ma_filter", True)
        ma_period     = self.params.get("ma_period", 20)    # MA 필터 기간

        min_rows = max(ma_period, 3) + 1
        if len(df) < min_rows:
            return Signal("HOLD", self.symbol, float(df["close"].iloc[-1]), "데이터 부족", 0.0)

        df    = df.copy()
        today = df.iloc[-1]
        prev  = df.iloc[-2]

        price      = float(today["close"])
        today_open = float(today["open"])
        today_date = self._get_date_str(today["date"])

        # ── 익일 청산 ────────────────────────────────────────
        # 어제 매수했고, 오늘로 날짜가 바뀐 경우 → 시가에 청산
        if self._bought_date and self._bought_date != today_date:
            self._bought_date = None
            return Signal(
                "SELL", self.symbol, today_open,
                f"변동성 돌파 익일 청산 (시가 {today_open:,.0f})", 1.0,
            )

        # 오늘 이미 매수한 경우 → 홀드
        if self._bought_date == today_date:
            return Signal("HOLD", self.symbol, price, "포지션 유지 중 (당일 청산 대기)", 0.5)

        # ── MA 필터: 하락장이면 진입하지 않음 ────────────────
        if use_ma_filter:
            df["ma"] = df["close"].rolling(ma_period).mean()
            ma_val   = df["ma"].iloc[-1]
            if not pd.isna(ma_val) and price < ma_val:
                return Signal(
                    "HOLD", self.symbol, price,
                    f"MA 필터 (현재가 {price:,.0f} < MA{ma_period} {ma_val:,.0f})", 0.1,
                )

        # ── 변동성 돌파 계산 ─────────────────────────────────
        prev_range = float(prev["high"]) - float(prev["low"])
        if prev_range <= 0:
            return Signal("HOLD", self.symbol, price, "전일 변동폭 없음", 0.0)

        target    = today_open + k * prev_range
        gap_to_tg = (target - price) / price * 100

        if price > target:
            confidence        = min((price - target) / prev_range, 1.0)
            self._bought_date = today_date
            return Signal(
                "BUY", self.symbol, price,
                f"변동성 돌파 (목표 {target:,.0f} 돌파, k={k}, 전일범위 {prev_range:,.0f})",
                confidence,
            )

        return Signal(
            "HOLD", self.symbol, price,
            f"목표가 미달 ({price:,.0f} / 목표 {target:,.0f}, -{gap_to_tg:.1f}%)", 0.1,
        )
