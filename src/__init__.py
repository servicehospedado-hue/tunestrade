"""
Backend profissional para trading automatizado com PocketOption
Suporte a múltiplos usuários, indicadores simultâneos e emissão de sinais
"""

from .managers.signal_manager import SignalManager
from .managers.user_manager import UserManager
from .managers.indicator_manager import IndicatorManager
from .core.engine import TradingEngine
from .config.settings import Settings

__version__ = "1.0.0"
__all__ = [
    "SignalManager",
    "UserManager",
    "IndicatorManager",
    "TradingEngine",
    "Settings",
]
