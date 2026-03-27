import pandas as pd
from .base import BaseStrategy, Signal


class MACrossoverStrategy(BaseStrategy):
    """
    골든크로스 / 데드크로스 전략
    - 단기 MA가 장기 MA를 상향 돌파 → 매수 (골든크로스)
    - 단기 MA가 장기 MA를 하향 돌파 → 매도 (데드크로스)
    """

    def analyze(self, df: pd.DataFrame) -> Signal:
        short = self.params.get("short_period", 5)
        long_ = self.params.get("long_period", 20)

        if len(df) < long_ + 2:
            return Signal("HOLD", self.symbol, df["close"].iloc[-1], "데이터 부족", 0.0)

        df = df.copy()
        df["ma_short"] = df["close"].rolling(short).mean()
        df["ma_long"] = df["close"].rolling(long_).mean()

        prev_short = df["ma_short"].iloc[-2]
        prev_long = df["ma_long"].iloc[-2]
        curr_short = df["ma_short"].iloc[-1]
        curr_long = df["ma_long"].iloc[-1]
        price = df["close"].iloc[-1]

        # 골든크로스: 이전엔 단기 < 장기, 현재 단기 > 장기
        if prev_short <= prev_long and curr_short > curr_long:
            gap_pct = abs(curr_short - curr_long) / curr_long * 100
            confidence = min(gap_pct / 2, 1.0)
            return Signal("BUY", self.symbol, price,
                          f"골든크로스 (MA{short}>MA{long_}), gap={gap_pct:.2f}%", confidence)

        # 데드크로스: 이전엔 단기 > 장기, 현재 단기 < 장기
        if prev_short >= prev_long and curr_short < curr_long:
            gap_pct = abs(curr_short - curr_long) / curr_long * 100
            confidence = min(gap_pct / 2, 1.0)
            return Signal("SELL", self.symbol, price,
                          f"데드크로스 (MA{short}<MA{long_}), gap={gap_pct:.2f}%", confidence)

        trend = "상승" if curr_short > curr_long else "하락"
        return Signal("HOLD", self.symbol, price, f"{trend} 추세 유지", 0.3)
