"""
Schemas Pydantic para API
"""
from .auth import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    UserResponse,
    SaveSSIDRequest,
    SaveSSIDResponse,
    SSIDResponse,
)

from .autotrade import (
    AutotradeToggleRequest,
    AutotradeToggleResponse,
    AutotradeStatusResponse,
    AutotradeConfig,
)

from .strategies import (
    IndicatorConfigRequest,
    SignalConfigRequest,
    AnalyzeRequest,
    StrategyInfo,
    StrategiesListResponse,
    IndicatorInfo,
)

__all__ = [
    # Auth
    "RegisterRequest",
    "LoginRequest",
    "AuthResponse",
    "UserResponse",
    "SaveSSIDRequest",
    "SaveSSIDResponse",
    "SSIDResponse",
    # Autotrade
    "AutotradeToggleRequest",
    "AutotradeToggleResponse",
    "AutotradeStatusResponse",
    "AutotradeConfig",
    # Strategies
    "IndicatorConfigRequest",
    "SignalConfigRequest",
    "AnalyzeRequest",
    "StrategyInfo",
    "StrategiesListResponse",
    "IndicatorInfo",
]
