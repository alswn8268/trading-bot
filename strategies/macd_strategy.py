"""
MACD 전략 (Moving Average Convergence Divergence)
- 추세 추종 전략의 대표 지표, MA 교차보다 신호가 빠름
- MACD선 = 단기 EMA(12) - 장기 EMA(26)
- 시그널선 = MACD의 EMA(9)
- 히스토그램 = MACD - 시그널
- MACD가 시그널 위로 교차 → 골든크로스 → 매수
- MACD가 시그널 아래로 교차 → 데드크로스 → 매도
- 제로선 필터로 추세 방향 확인 옵션
"""
import pandas as pd
from .base import BaseStrategy, Signal


class MACDStrategy(BaseStrategy):

    def analyze(self, df: pd.DataFrame) -> Signal:
        fast          = self.params.get("fast", 12)
        slow          = self.params.get("slow", 26)
        signal_period = self.params.get("signal", 9)
        use_zero_filter = self.params.get("use_zero_filter", False)  # 제로선 방향 필터

        min_rows = slow + signal_period + 2
        if len(df) < min_rows:
            return Signal("HOLD", self.symbol, float(df["close"].iloc[-1]), "데이터 부족", 0.0)

        df = df.copy()
        df["ema_fast"] = df["close"].ewm(span=fast,          adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=slow,          adjust=False).mean()
        df["macd"]     = df["ema_fast"] - df["ema_slow"]
        df["sig"]      = df["macd"].ewm(span=signal_period,  adjust=False).mean()
        df["hist"]     = df["macd"] - df["sig"]

        prev_hist = float(df["hist"].iloc[-2])
        curr_hist = float(df["hist"].iloc[-1])
        macd_now  = float(df["macd"].iloc[-1])
        sig_now   = float(df["sig"].iloc[-1])
        price     = float(df["close"].iloc[-1])

        # ── 골든크로스: 히스토그램이 음→양 교차 ─────────────
        if prev_hist <= 0 and curr_hist > 0:
            # 제로선 필터: MACD가 0 아래에서 교차하면 약한 신호로 무시
            if use_zero_filter and macd_now < 0:
                return Signal("HOLD", self.symbol, price,
                              f"MACD 골든크로스 (제로선 아래, 무시)", 0.2)
            confidence = min(abs(curr_hist) / (abs(macd_now) + 1e-9), 1.0)
            return Signal(
                "BUY", self.symbol, price,
                f"MACD 골든크로스 (MACD {macd_now:.4f} > 시그널 {sig_now:.4f})",
                round(confidence, 2),
            )

        # ── 데드크로스: 히스토그램이 양→음 교차 ─────────────
        if prev_hist >= 0 and curr_hist < 0:
            if use_zero_filter and macd_now > 0:
                return Signal("HOLD", self.symbol, price,
                              f"MACD 데드크로스 (제로선 위, 무시)", 0.2)
            confidence = min(abs(curr_hist) / (abs(macd_now) + 1e-9), 1.0)
            return Signal(
                "SELL", self.symbol, price,
                f"MACD 데드크로스 (MACD {macd_now:.4f} < 시그널 {sig_now:.4f})",
                round(confidence, 2),
            )

        # ── 홀드: 추세 방향 표시 ─────────────────────────────
        trend     = "상승" if curr_hist > 0 else "하락"
        momentum  = "강화" if abs(curr_hist) > abs(prev_hist) else "약화"
        return Signal(
            "HOLD", self.symbol, price,
            f"MACD {trend} 추세 {momentum} (hist={curr_hist:.4f})", 0.2,
        )
