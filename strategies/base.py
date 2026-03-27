from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class Signal:
    action: str          # "BUY" | "SELL" | "HOLD"
    symbol: str
    price: float
    reason: str
    confidence: float    # 0.0 ~ 1.0


class BaseStrategy(ABC):
    def __init__(self, symbol: str, params: dict):
        self.symbol = symbol
        self.params = params

    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> Signal:
        """캔들 데이터를 분석하여 매매 신호 반환"""
        pass

    def get_name(self) -> str:
        return self.__class__.__name__
