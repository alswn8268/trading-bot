from .ma_crossover import MACrossoverStrategy
from .rsi_strategy import RSIStrategy
from .bollinger import BollingerStrategy
from .volatility_breakout import VolatilityBreakoutStrategy
from .macd_strategy import MACDStrategy
from .ai_strategy import AIStrategy

STRATEGY_MAP = {
    "ma_crossover":       MACrossoverStrategy,
    "ma_crossover_short": MACrossoverStrategy,   # 동일 전략, 파라미터만 다름
    "rsi":                RSIStrategy,
    "rsi_short":          RSIStrategy,           # 동일 전략, 파라미터만 다름
    "bollinger":          BollingerStrategy,
    "bollinger_short":    BollingerStrategy,     # 동일 전략, 파라미터만 다름
    "volatility_breakout": VolatilityBreakoutStrategy,
    "macd":               MACDStrategy,
    "ai":                 AIStrategy,
}

def get_strategy(name: str, symbol: str, params: dict):
    cls = STRATEGY_MAP.get(name)
    if not cls:
        raise ValueError(f"알 수 없는 전략: {name}. 사용 가능: {list(STRATEGY_MAP.keys())}")
    return cls(symbol, params)
