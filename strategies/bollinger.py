import pandas as pd
from .base import BaseStrategy, Signal


class BollingerStrategy(BaseStrategy):
    """
    볼린저 밴드 전략
    - 가격이 하단 밴드 터치 → 매수
    - 중간 밴드(MA) 회복 시 청산 (단타 모드: scalp_exit=true)
    - 상단 밴드 터치 → 매도 (스윙 모드)
    - %B 지표 활용
    """

    def analyze(self, df: pd.DataFrame) -> Signal:
        period    = self.params.get("period", 20)
        std_dev   = self.params.get("std_dev", 2.0)
        # scalp_exit=true: 중간 밴드 회복 시 청산 (단타용)
        scalp_exit = self.params.get("scalp_exit", True)

        if len(df) < period + 2:
            return Signal("HOLD", self.symbol, df["close"].iloc[-1], "데이터 부족", 0.0)

        df = df.copy()
        df["ma"]    = df["close"].rolling(period).mean()
        df["std"]   = df["close"].rolling(period).std()
        df["upper"] = df["ma"] + std_dev * df["std"]
        df["lower"] = df["ma"] - std_dev * df["std"]
        df["pct_b"] = (df["close"] - df["lower"]) / (df["upper"] - df["lower"])

        price      = df["close"].iloc[-1]
        pct_b      = df["pct_b"].iloc[-1]
        prev_pct_b = df["pct_b"].iloc[-2]
        upper      = df["upper"].iloc[-1]
        lower      = df["lower"].iloc[-1]
        ma         = df["ma"].iloc[-1]

        # ── 매도 조건 (BUY보다 먼저) ──────────────────────
        # 1) 단타: 이전 봉이 중간 밴드 아래였다가 현재 봉에서 중간 밴드 위로 회복
        if scalp_exit and prev_pct_b < 0.5 and pct_b >= 0.5:
            return Signal("SELL", self.symbol, price,
                          f"볼린저 중간 밴드 회복 (%B={pct_b:.2f}, MA={ma:,.0f})",
                          0.8)

        # 2) 상단 밴드 터치 → 강한 매도
        if pct_b >= 0.95:
            confidence = max(0.0, (pct_b - 0.9) * 5)
            return Signal("SELL", self.symbol, price,
                          f"볼린저 상단 터치 (%B={pct_b:.2f}, 상단={upper:,.0f})",
                          min(confidence, 1.0))

        # ── 매수 조건 ──────────────────────────────────────
        # 하단 밴드 터치
        if pct_b <= 0.05:
            confidence = max(0.0, (0.1 - pct_b) * 5)
            return Signal("BUY", self.symbol, price,
                          f"볼린저 하단 터치 (%B={pct_b:.2f}, 하단={lower:,.0f})",
                          min(confidence, 1.0))

        return Signal("HOLD", self.symbol, price,
                      f"밴드 중립 (%B={pct_b:.2f})", 0.2)
