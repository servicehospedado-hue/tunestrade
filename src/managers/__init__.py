"""
Módulo de gerenciadores
"""
from .signal_manager import SignalManager, Signal, SignalType, SignalStatus, SignalConfig
from .user_manager import UserManager, UserSession, UserLimits, UserStats, UserStatus
from .indicator_manager import IndicatorManager, IndicatorRequest
from .connection_manager import ConnectionManager, Connection, ConnectionState, ConnectionError
from .notification_manager import NotificationManager, NotificationPayload, DeviceToken, NotificationProvider
from .strategy_manager import StrategyManager, StrategyConfig
from .tradeexecutor_manager import TradeExecutor, UserTradeState
from .autotrade_manager import AutotradeManager, AutotradeStatus
from .datacollector_manager import DataCollectorManager
from .system_health_manager import SystemHealthManager
from .log_manager import LogManager, log_manager, get_logger, get_manager_logger, get_ws_logger, get_app_logger, WSConnectionLogger

__all__ = [
    "SignalManager",
    "Signal",
    "SignalType",
    "SignalStatus",
    "SignalConfig",
    "UserManager",
    "UserSession",
    "UserLimits",
    "UserStats",
    "UserStatus",
    "IndicatorManager",
    "IndicatorRequest",
    "ConnectionManager",
    "Connection",
    "ConnectionState",
    "ConnectionError",
    "NotificationManager",
    "NotificationPayload",
    "DeviceToken",
    "NotificationProvider",
    "StrategyManager",
    "StrategyConfig",
    "TradeExecutor",
    "UserTradeState",
    "AutotradeManager",
    "AutotradeStatus",
    "DataCollectorManager",
    "SystemHealthManager",
    "LogManager",
    "log_manager",
    "get_logger",
    "get_manager_logger",
    "get_ws_logger",
    "get_app_logger",
    "WSConnectionLogger",
]
