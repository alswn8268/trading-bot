import pandas as pd
import numpy as np
from .base import BaseStrategy, Signal


class RSIStrategy(BaseStrategy):
    """
    RSI 과매수/과매도 전략
    - RSI < oversold(30) → 과매도 → 매수
    - RSI > overbought(70) → 과매수 → 매도
    """

    def _calc_rsi(self, series: pd.Series, period: int) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def analyze(self, df: pd.DataFrame) -> Signal:
        period = self.params.get("period", 14)
        oversold = self.params.get("oversold", 30)
        overbought = self.params.get("overbought", 70)

        if len(df) < period + 2:
            return Signal("HOLD", self.symbol, df["close"].iloc[-1], "데이터 부족", 0.0)

        df = df.copy()
        df["rsi"] = self._calc_rsi(df["close"], period)

        rsi_now = df["rsi"].iloc[-1]
        rsi_prev = df["rsi"].iloc[-2]
        price = df["close"].iloc[-1]

        # 과매도 탈출 (반등 신호)
        if rsi_prev < oversold and rsi_now >= oversold:
            confidence = (oversold - min(rsi_prev, 20)) / oversold
            return Signal("BUY", self.symbol, price,
                          f"RSI 과매도 탈출 ({rsi_prev:.1f}→{rsi_now:.1f})", min(confidence, 1.0))

        # 과매수 탈출 (하락 신호)
        if rsi_prev > overbought and rsi_now <= overbought:
            confidence = (max(rsi_prev, 80) - overbought) / (100 - overbought)
            return Signal("SELL", self.symbol, price,
                          f"RSI 과매수 탈출 ({rsi_prev:.1f}→{rsi_now:.1f})", min(confidence, 1.0))

        # 극단적 과매도 (강한 매수)
        if rsi_now < 20:
            return Signal("BUY", self.symbol, price,
                          f"RSI 극단 과매도 ({rsi_now:.1f})", 0.9)

        # 극단적 과매수 (강한 매도)
        if rsi_now > 80:
            return Signal("SELL", self.symbol, price,
                          f"RSI 극단 과매수 ({rsi_now:.1f})", 0.9)

        return Signal("HOLD", self.symbol, price, f"RSI 중립 ({rsi_now:.1f})", 0.2)
