"""
Fábrica da aplicação FastAPI - Organiza todas as rotas
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

from ...managers.log_manager import get_manager_logger

logger = get_manager_logger("api")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adiciona headers de segurança HTTP em todas as respostas."""

    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # HSTS — ativar apenas se HTTPS estiver configurado
        # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


def create_app(engine) -> FastAPI:
    """
    Cria aplicação FastAPI com todas as rotas organizadas
    
    Args:
        engine: TradingEngine com managers configurados
    
    Returns:
        FastAPI: Aplicação configurada
    """
    app = FastAPI(
        title="PocketOption Trading API",
        description="API para trading automatizado com análise técnica",
        version="1.0.0"
    )
    
    # CORS — restringir origens em produção via env
    import os
    cors_origins_env = os.getenv("CORS_ORIGINS", "")
    cors_origins = (
        [o.strip() for o in cors_origins_env.split(",") if o.strip()]
        if cors_origins_env
        else ["*"]
    )
    if cors_origins == ["*"]:
        logger.warning("[SECURITY] CORS allow_origins=['*'] — defina CORS_ORIGINS no .env para produção")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Headers de segurança HTTP
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Middleware para logar requisições
    @app.middleware("http")
    async def log_requests(request, call_next):
        logger.info(f"[REQUEST] {request.method} {request.url.path}")
        response = await call_next(request)
        logger.info(f"[RESPONSE] {response.status_code}")
        return response
    
    # Endpoint raiz
    @app.get("/")
    async def root():
        return {"message": "PocketOption Trading API", "version": "1.0.0"}
    
    # Importar e registrar rotas
    _register_routes(app, engine)
    
    logger.info("=== API INICIALIZADA ===")
    return app


def _register_routes(app: FastAPI, engine):
    """Registra todas as rotas na aplicação"""
    
    # 1. Autenticação (nova estrutura)
    try:
        from .auth import router as auth_router
        from ..services.auth_service import set_user_manager
        if engine.user_manager:
            set_user_manager(engine.user_manager)
        app.include_router(auth_router)
        logger.info("[OK] Rotas de autenticação (nova)")
    except Exception as e:
        logger.error(f"[ERRO] Auth nova: {e}")
    
    # 2. Autotrade (nova estrutura)
    try:
        from .autotrade import router as autotrade_router
        from ..services.autotrade_service import autotrade_service
        from ...database.autotrade_dao import autotrade_dao
        
        if engine.autotrade_manager:
            autotrade_service.set_managers(
                autotrade_manager=engine.autotrade_manager,
                user_manager=engine.user_manager,
                autotrade_dao=autotrade_dao,
                trade_executor=engine.trade_executor
            )
        app.include_router(autotrade_router)
        logger.info("[OK] Rotas de autotrade (nova)")
    except Exception as e:
        logger.warning(f"[WARN] Autotrade nova: {e}")
    
    # 3. Sistema
    try:
        from .system import router as system_router, set_engine
        set_engine(engine)
        app.include_router(system_router)
        logger.info("[OK] Rotas de sistema")
    except Exception as e:
        logger.warning(f"[WARN] Sistema: {e}")
    
    # 4. Estratégias
    try:
        from .strategies import router as strategies_router
        app.include_router(strategies_router)
        logger.info("[OK] Rotas de estratégias")
    except Exception as e:
        logger.warning(f"[WARN] Estratégias: {e}")

    # 4b. Estratégias pessoais dos usuários
    try:
        from .user_strategies import router as user_strategies_router, set_strategy_manager
        if engine.strategy_manager:
            set_strategy_manager(engine.strategy_manager)
        app.include_router(user_strategies_router)
        logger.info("[OK] Rotas de estratégias pessoais")
    except Exception as e:
        logger.warning(f"[WARN] Estratégias pessoais: {e}")
    
    # 5. Webhook legado
    try:
        from ..autotrade_webhook import router as webhook_router, set_autotrade_monitor, set_autotrade_dao
        if engine.autotrade_manager:
            set_autotrade_monitor(engine.autotrade_manager)
            from ...database.autotrade_dao import autotrade_dao
            if autotrade_dao:
                set_autotrade_dao(autotrade_dao)
            app.include_router(webhook_router)
            logger.info("[OK] Rotas de webhook")
    except Exception as e:
        logger.warning(f"[WARN] Webhook: {e}")
    
    # 6. Indicadores (rota direta /indicators para compatibilidade com app)
    try:
        from .strategies import available_indicators
        @app.get("/indicators")
        async def indicators_endpoint():
            """Rota /indicators para compatibilidade com app mobile"""
            result = await available_indicators()
            return result
        logger.info("[OK] Rota /indicators adicionada")
    except Exception as e:
        logger.warning(f"[WARN] Indicadores: {e}")
