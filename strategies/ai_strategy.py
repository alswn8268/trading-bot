"""
AI 분석 전략 — Claude API를 사용해 기술적 지표를 종합 분석
"""
import json
import logging
import numpy as np
import pandas as pd

from .base import BaseStrategy, Signal

logger = logging.getLogger("ai_strategy")


def _calc_rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def _calc_macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return (
        round(float(macd_line.iloc[-1]), 4),
        round(float(signal_line.iloc[-1]), 4),
        round(float(histogram.iloc[-1]), 4),
    )


def _calc_bollinger(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    ma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = ma + std_dev * std
    lower = ma - std_dev * std
    price = series.iloc[-1]
    ma_val = ma.iloc[-1]
    upper_val = upper.iloc[-1]
    lower_val = lower.iloc[-1]
    bandwidth = (upper_val - lower_val) / ma_val * 100 if ma_val else 0
    pct_b = (price - lower_val) / (upper_val - lower_val) if (upper_val - lower_val) else 0.5
    return {
        "upper": round(float(upper_val), 2),
        "middle": round(float(ma_val), 2),
        "lower": round(float(lower_val), 2),
        "bandwidth_pct": round(float(bandwidth), 2),
        "pct_b": round(float(pct_b), 3),
    }


def _calc_ma(series: pd.Series, periods=(5, 20, 60)):
    result = {}
    for p in periods:
        if len(series) >= p:
            result[f"ma{p}"] = round(float(series.rolling(p).mean().iloc[-1]), 2)
    return result


def _build_indicators(df: pd.DataFrame) -> dict:
    close = df["close"]
    price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2]) if len(close) >= 2 else price
    change_pct = (price - prev_price) / prev_price * 100 if prev_price else 0

    indicators: dict = {
        "current_price": round(price, 2),
        "change_pct": round(change_pct, 3),
        "volume": round(float(df["volume"].iloc[-1]), 2),
        "volume_avg20": round(float(df["volume"].rolling(20).mean().iloc[-1]), 2) if len(df) >= 20 else None,
    }

    if len(close) >= 15:
        indicators["rsi14"] = _calc_rsi(close, 14)

    if len(close) >= 30:
        macd, sig, hist = _calc_macd(close)
        indicators["macd"] = {"macd": macd, "signal": sig, "histogram": hist}

    if len(close) >= 20:
        indicators["bollinger"] = _calc_bollinger(close)

    indicators.update(_calc_ma(close))

    # 최근 5개 봉 요약 (고/저/종가)
    recent = df.tail(5)[["open", "high", "low", "close"]].round(2).to_dict("records")
    indicators["recent_candles_5"] = recent

    return indicators


_SYSTEM_PROMPT = """당신은 전문 퀀트 트레이더입니다.
제공된 기술적 지표 데이터를 분석하여 매매 신호를 결정합니다.

반드시 다음 JSON 형식으로만 응답하세요:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0~1.0,
  "reason": "한 문장 근거 (한국어, 50자 이내)"
}

판단 기준:
- RSI < 30 과매도, RSI > 70 과매수
- MACD 히스토그램 부호 전환: 양전환 → 매수, 음전환 → 매도
- 볼린저 %B < 0.1 → 과매도권, %B > 0.9 → 과매수권
- 단기 MA가 장기 MA를 상향 돌파 → 매수, 하향 돌파 → 매도
- 여러 지표가 동일 방향을 가리킬수록 confidence 높게
- 불확실할 때는 HOLD 선택"""


class AIStrategy(BaseStrategy):
    """
    Claude AI 기반 전략
    - RSI, MACD, 볼린저 밴드, 이동평균 계산 후 Claude API로 종합 분석
    - params: api_key, model, interval
    """

    def __init__(self, symbol: str, params: dict):
        super().__init__(symbol, params)
        try:
            import anthropic as _anthropic
        except ImportError:
            raise ImportError("AI 전략을 사용하려면 'pip install anthropic' 를 실행하세요.")
        api_key = params.get("api_key", "")
        if not api_key or api_key.startswith("YOUR_"):
            raise ValueError(
                "AI 전략에는 Anthropic API 키가 필요합니다. "
                "config.yaml의 strategies.ai.api_key를 설정하세요."
            )
        self._anthropic = _anthropic
        self._client = _anthropic.Anthropic(api_key=api_key)
        self._model = params.get("model", "claude-haiku-4-5-20251001")

    def analyze(self, df: pd.DataFrame) -> Signal:
        price = float(df["close"].iloc[-1])

        if len(df) < 30:
            return Signal("HOLD", self.symbol, price, "AI 분석: 데이터 부족", 0.0)

        try:
            indicators = _build_indicators(df)
        except Exception as e:
            logger.warning(f"지표 계산 실패: {e}")
            return Signal("HOLD", self.symbol, price, f"AI 분석: 지표 계산 오류", 0.0)

        user_content = (
            f"종목: {self.symbol}\n"
            f"지표 데이터:\n{json.dumps(indicators, ensure_ascii=False, indent=2)}"
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = response.content[0].text.strip()
            # JSON 파싱
            result = json.loads(raw)
            action = result.get("action", "HOLD").upper()
            if action not in ("BUY", "SELL", "HOLD"):
                action = "HOLD"
            confidence = float(result.get("confidence", 0.5))
            reason = f"AI분석: {result.get('reason', '')}"
            logger.info(f"[AI] {self.symbol} → {action} ({confidence:.0%}) | {reason}")
            return Signal(action, self.symbol, price, reason, confidence)

        except json.JSONDecodeError as e:
            logger.error(f"AI 응답 파싱 실패: {e} | raw={raw!r}")
            return Signal("HOLD", self.symbol, price, "AI 분석: 응답 파싱 오류", 0.0)
        except self._anthropic.APIError as e:
            logger.error(f"Claude API 오류: {e}")
            return Signal("HOLD", self.symbol, price, f"AI 분석: API 오류", 0.0)
