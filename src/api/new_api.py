"""
API - Nova estrutura modularizada

Esta é a fachada principal da API que expõe:
- Schemas Pydantic organizados por domínio
- Serviços de negócio desacoplados
- Rotas organizadas por feature
- Fábrica de aplicação FastAPI

Uso:
    from src.api import create_app
    app = create_app(engine)
"""

# Schemas
from .schemas import (
    # Auth
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    UserResponse,
    SaveSSIDRequest,
    SaveSSIDResponse,
    SSIDResponse,
    # Autotrade
    AutotradeToggleRequest,
    AutotradeToggleResponse,
    AutotradeStatusResponse,
    # Strategies
    IndicatorConfigRequest,
    SignalConfigRequest,
    AnalyzeRequest,
)

# Serviços
from .services import (
    auth_service,
    autotrade_service,
    set_user_manager,
)

# Rotas e fábrica
from .routes import (
    create_app,
    auth_router,
    autotrade_router,
    system_router,
    strategies_router,
)

# Manter compatibilidade com código legado
from .routes import create_app as create_app_new

__all__ = [
    # Schemas
    "RegisterRequest",
    "LoginRequest", 
    "AuthResponse",
    "UserResponse",
    "SaveSSIDRequest",
    "SaveSSIDResponse",
    "SSIDResponse",
    "AutotradeToggleRequest",
    "AutotradeToggleResponse",
    "AutotradeStatusResponse",
    "IndicatorConfigRequest",
    "SignalConfigRequest",
    "AnalyzeRequest",
    # Serviços
    "auth_service",
    "autotrade_service",
    "set_user_manager",
    # Rotas
    "create_app",
    "create_app_new",
    "auth_router",
    "autotrade_router",
    "system_router",
    "strategies_router",
]
