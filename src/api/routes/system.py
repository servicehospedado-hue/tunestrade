"""
Rotas de Sistema - Health checks, estatísticas e info
"""
from fastapi import APIRouter
from datetime import datetime

from ...managers.log_manager import get_manager_logger

logger = get_manager_logger("system_routes")
router = APIRouter(prefix="/system", tags=["system"])

# Referência ao engine (será injetada)
_engine = None


def set_engine(engine):
    """Injeta o engine para acesso aos managers"""
    global _engine
    _engine = engine


@router.get("/health")
async def health():
    """Health check do sistema"""
    if _engine:
        status = await _engine.get_system_status()
        return {
            "status": "healthy" if status.running else "unhealthy",
            "running": status.running,
            "users_connected": status.users_connected,
            "active_tasks": status.active_tasks,
            "pending_signals": status.pending_signals
        }
    return {"status": "unknown", "engine": "not_set"}


@router.get("/stats")
async def system_stats():
    """Retorna estatísticas completas do sistema"""
    if _engine:
        stats = await _engine.get_full_stats()
        return stats
    return {"error": "Engine não configurado"}


@router.get("/ping")
async def ping():
    """Endpoint simples para verificar se servidor está online"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
