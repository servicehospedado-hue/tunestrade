"""
Módulo de banco de dados
"""
from .database_manager import DatabaseManager, DatabaseError, ConnectionError, RetryExhaustedError, BatchOperation, init_database_manager, db_manager
from .models import Base, User, AutotradeConfig, AccountMonitoring, UserStrategy
from .autotrade_dao import AutotradeDAO, init_autotrade_dao, autotrade_dao
from .user_strategy_dao import UserStrategyDAO, init_user_strategy_dao, get_user_strategy_dao

__all__ = [
    "DatabaseManager",
    "DatabaseError",
    "ConnectionError",
    "RetryExhaustedError",
    "BatchOperation",
    "init_database_manager",
    "db_manager",
    "Base",
    "User",
    "AutotradeConfig",
    "AccountMonitoring",
    "UserStrategy",
    "AutotradeDAO",
    "init_autotrade_dao",
    "autotrade_dao",
    "UserStrategyDAO",
    "init_user_strategy_dao",
    "get_user_strategy_dao",
]
