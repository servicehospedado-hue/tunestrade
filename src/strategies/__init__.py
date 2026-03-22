"""
Módulo de Estratégias de Trading
"""
from .base import BaseStrategy, StrategyResult
from .scalping import ScalpingStrategy
from .trend_m1 import TrendM1Strategy
from .dynamic import DynamicStrategy

__all__ = [
    "BaseStrategy",
    "StrategyResult",
    "ScalpingStrategy",
    "TrendM1Strategy",
    "DynamicStrategy",
]
