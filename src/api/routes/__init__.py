"""
Rotas organizadas da API
"""
from .auth import router as auth_router
from .autotrade import router as autotrade_router
from .system import router as system_router, set_engine
from .strategies import router as strategies_router
from .factory import create_app

__all__ = [
    "auth_router",
    "autotrade_router",
    "system_router",
    "strategies_router",
    "set_engine",
    "create_app",
]
