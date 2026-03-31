"""
변동성 돌파 전략 (Larry Williams의 변동성 돌파)
- 매수 목표가 = 당일 시가 + (전일 고가 - 전일 저가) × k
- 당일 가격이 목표가 돌파 시 매수
- 다음날 시가에 무조건 매도
- 5일 이동평균 필터: 현재가 > 5일 MA일 때만 매수 (하락 추세 진입 방지)

참고: 코인 자동매매에서 가장 검증된 전략 중 하나
     하락장에서 존버 대비 손실 대폭 축소 효과
"""
import pandas as pd
from .base import BaseStrategy, Signal


class VolatilityBreakoutStrategy(BaseStrategy):

    def analyze(self, df: pd.DataFrame) -> Signal:
        k = self.params.get("k", 0.5)                    # 변동성 비율 (0.3~0.7)
        ma_period = self.params.get("ma_period", 5)      # 이동평균 필터 기간
        use_ma_filter = self.params.get("use_ma_filter", True)

        if len(df) < ma_period + 2:
            return Signal("HOLD", self.symbol, df["close"].iloc[-1], "데이터 부족", 0.0)

        df = df.copy()
        df["ma"] = df["close"].rolling(ma_period).mean()

        # 전일 데이터
        prev = df.iloc[-2]
        today = df.iloc[-1]

        prev_range = prev["high"] - prev["low"]          # 전일 고저 범위
        target = today["open"] + prev_range * k          # 당일 매수 목표가
        current_price = today["close"]
        ma_now = today["ma"]

        # ── 매수 조건 ─────────────────────────────────────
        # 1. 현재가가 목표가를 돌파했는가
        price_breakout = current_price >= target

        # 2. MA 필터: 현재가 > 이동평균 (상승 추세 확인)
        ma_filter = (current_price >= ma_now) if use_ma_filter else True

        # ── 매도 조건 (BUY보다 먼저 체크) ────────────────
        # 전날에 변동성 돌파 BUY가 발생했으면 오늘 시가에 매도 (익일 시가 청산 원칙)
        if len(df) >= 3:
            prev_target = prev["open"] + (df.iloc[-3]["high"] - df.iloc[-3]["low"]) * k
            if prev["close"] >= prev_target:
                return Signal(
                    "SELL", self.symbol, current_price,
                    f"변동성 돌파 익일 청산 (전일 돌파={prev['close']:,.0f} ≥ 목표={prev_target:,.0f})",
                    0.9,
                )

        # ── 매수 조건 ─────────────────────────────────────
        if price_breakout and ma_filter:
            range_pct = prev_range / prev["close"] * 100
            confidence = min(range_pct / 5, 1.0)
            return Signal(
                "BUY", self.symbol, current_price,
                f"변동성 돌파 (목표가={target:,.0f}, k={k}, MA{ma_period} 통과)",
                confidence,
            )

        reason_parts = []
        if not price_breakout:
            reason_parts.append(f"목표가 미달 (현재={current_price:,.0f} < 목표={target:,.0f})")
        if use_ma_filter and not ma_filter:
            reason_parts.append(f"MA{ma_period} 필터 미통과")

        return Signal("HOLD", self.symbol, current_price,
                      " | ".join(reason_parts) or "대기", 0.1)
