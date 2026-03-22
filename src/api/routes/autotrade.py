"""
Rotas de Autotrade - Endpoints para gerenciamento de autotrade
"""
from fastapi import APIRouter, HTTPException, Depends

from ..auth import APIAuthMiddleware
from ..schemas.autotrade import (
    AutotradeToggleRequest,
    AutotradeToggleResponse,
    AutotradeStatusResponse
)
from ..services.autotrade_service import autotrade_service
from ...managers.log_manager import get_manager_logger

logger = get_manager_logger("autotrade_routes")
router = APIRouter(prefix="/autotrade", tags=["autotrade"])

auth_middleware = APIAuthMiddleware()


@router.post("/toggle", response_model=AutotradeToggleResponse)
async def toggle_autotrade(
    request: AutotradeToggleRequest,
    auth: dict = Depends(auth_middleware)
):
    """
    Liga/desliga autotrade para o usuário logado.
    Sincroniza com autotrade_config e invalida cache.
    """
    user_id = auth.get("user_id")
    
    success, data, error = await autotrade_service.toggle_autotrade(
        user_id=user_id,
        enabled=request.enabled,
        strategy_id=request.strategy_id,
        execute=request.execute
    )
    
    if not success:
        raise HTTPException(status_code=500, detail=error or "Erro ao atualizar autotrade")
    
    return AutotradeToggleResponse(
        success=True,
        enabled=data["enabled"],
        user_id=user_id,
        message=f"Autotrade {'ativado' if request.enabled else 'desativado'} com sucesso"
    )


@router.get("/status", response_model=AutotradeStatusResponse)
async def get_autotrade_status(
    auth: dict = Depends(auth_middleware)
):
    """
    Retorna status atual do autotrade do usuário logado.
    """
    user_id = auth.get("user_id")
    
    success, data, error = await autotrade_service.get_status(user_id)
    
    if not success:
        raise HTTPException(status_code=500, detail=error or "Erro ao buscar status")
    
    return AutotradeStatusResponse(**data)


@router.put("/config")
async def update_autotrade_config(
    request: dict,
    auth: dict = Depends(auth_middleware)
):
    """Atualiza configurações de autotrade (todos os campos)."""
    user_id = auth.get("user_id")

    def _bool(v):
        if v is None: return None
        return bool(v)
    def _int(v):
        if v is None: return None
        return int(v)
    def _float(v):
        if v is None: return None
        return float(v)

    success, data, error = await autotrade_service.update_config(
        user_id=user_id,
        amount=_float(request.get("amount")),
        strategy_name=request.get("strategy_name"),
        cooldown=request.get("cooldown"),
        execute=request.get("execute"),
        # Stops
        stop_loss_enabled=_bool(request.get("stop_loss_enabled")),
        stop_loss_value=_float(request.get("stop_loss_value")),
        stop_gain_enabled=_bool(request.get("stop_gain_enabled")),
        stop_gain_value=_float(request.get("stop_gain_value")),
        stop_soft_mode=_bool(request.get("stop_soft_mode")),
        stop_win_seq_enabled=_bool(request.get("stop_win_seq_enabled")),
        stop_win_seq=_int(request.get("stop_win_seq")),
        stop_loss_seq_enabled=_bool(request.get("stop_loss_seq_enabled")),
        stop_loss_seq=_int(request.get("stop_loss_seq")),
        stop_seq_soft_mode=_bool(request.get("stop_seq_soft_mode")),
        stop_medium_enabled=_bool(request.get("stop_medium_enabled")),
        stop_medium_pct=_float(request.get("stop_medium_pct")),
        stop_medium_soft_mode=_bool(request.get("stop_medium_soft_mode")),
        # Redução
        reduce_enabled=_bool(request.get("reduce_enabled")),
        reduce_loss_trigger=_int(request.get("reduce_loss_trigger")),
        reduce_win_exit=_int(request.get("reduce_win_exit")),
        reduce_pct=_float(request.get("reduce_pct")),
        # Martingale
        martingale_enabled=_bool(request.get("martingale_enabled")),
        martingale_levels=_int(request.get("martingale_levels")),
        martingale_multiplier=_float(request.get("martingale_multiplier")),
        # Soros
        soros_enabled=_bool(request.get("soros_enabled")),
        soros_levels=_int(request.get("soros_levels")),
        soros_pct=_float(request.get("soros_pct")),
    )

    if not success:
        raise HTTPException(status_code=500, detail=error or "Erro ao atualizar configuração")

    return {"success": True, "message": "Configuração atualizada com sucesso", "user_id": user_id}


@router.post("/reset-session")
async def reset_session_state(
    auth: dict = Depends(auth_middleware)
):
    """Reseta o estado de sessão do usuário (zera Soros/Martingale/Reduce)."""
    user_id = auth.get("user_id")
    
    # Obter trade_executor do engine
    from ...core.engine import engine
    if not engine or not engine.trade_executor:
        raise HTTPException(status_code=500, detail="TradeExecutor não disponível")
    
    await engine.trade_executor.reset_session_state(user_id)
    
    return {"success": True, "message": "Estado de sessão resetado", "user_id": user_id}
