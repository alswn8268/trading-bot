from .ma_crossover import MACrossoverStrategy
from .rsi_strategy import RSIStrategy
from .bollinger import BollingerStrategy
from .volatility_breakout import VolatilityBreakoutStrategy
from .macd_strategy import MACDStrategy

STRATEGY_MAP = {
    "ma_crossover":        MACrossoverStrategy,
    "rsi":                 RSIStrategy,
    "bollinger":           BollingerStrategy,
    "volatility_breakout": VolatilityBreakoutStrategy,
    "macd":                MACDStrategy,
}

def get_strategy(name: str, symbol: str, params: dict):
    cls = STRATEGY_MAP.get(name)
    if not cls:
        raise ValueError(f"알 수 없는 전략: {name}. 사용 가능: {list(STRATEGY_MAP.keys())}")
    return cls(symbol, params)
