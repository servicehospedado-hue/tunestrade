"""
Rotas de webhook para notificações de autotrade
Permite que o frontend notifique mudanças em tempo real
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger("autotrade_webhook")

router = APIRouter(prefix="/webhook/autotrade", tags=["autotrade"])

# Referência global ao monitor (será injetada)
_autotrade_monitor = None
_autotrade_dao_instance = None


def set_autotrade_monitor(monitor):
    """Define o monitor de autotrade (chamado na inicialização)"""
    global _autotrade_monitor
    _autotrade_monitor = monitor
    logger.info("AutotradeMonitor injetado nas rotas de webhook")


def set_autotrade_dao(dao):
    """Define o DAO de autotrade (chamado na inicialização)"""
    global _autotrade_dao_instance
    _autotrade_dao_instance = dao
    logger.info("AutotradeDAO injetado nas rotas de webhook")


def _get_autotrade_dao():
    """Obtém a instância do DAO (lazy loading)"""
    global _autotrade_dao_instance
    if _autotrade_dao_instance:
        return _autotrade_dao_instance
    
    # Tentar importar do módulo global
    try:
        from ...database.autotrade_dao import autotrade_dao
        return autotrade_dao
    except:
        return None


class UpdateConfigRequest(BaseModel):
    """Schema para atualização de configuração"""
    autotrade: Optional[int] = None  # 1 = ligado, 0 = desligado
    amount: Optional[float] = None  # Valor da operação
    strategy_name: Optional[str] = None  # Nome da estratégia
    cooldown: Optional[str] = None  # Cooldown: '60' ou '60-120'


@router.put("/config/{user_id}")
async def update_autotrade_config(user_id: str, request: UpdateConfigRequest):
    """
    Atualiza configuração de autotrade do usuário.
    
    Invalida o cache imediatamente para refletir mudanças em tempo real.
    
    Exemplo de payload:
    {
        "autotrade": 1,
        "amount": 5.0,
        "strategy_name": "Scalping5s",
        "cooldown": "60-120"
    }
    """
    autotrade_dao = _get_autotrade_dao()
    if not autotrade_dao:
        raise HTTPException(status_code=503, detail="AutotradeDAO não disponível")
    
    if not _autotrade_monitor:
        raise HTTPException(status_code=503, detail="AutotradeMonitor não disponível")
    
    try:
        # Atualizar no banco
        success = await autotrade_dao.update_config(
            user_id=user_id,
            autotrade=request.autotrade,
            amount=request.amount,
            strategy_name=request.strategy_name,
            cooldown=request.cooldown
        )
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Configuração não encontrada para usuário {user_id}")
        
        # Invalidar cache para forçar recarregamento
        await _autotrade_monitor.invalidate_cache(user_id)
        
        # Recarregar status atualizado
        status = await _autotrade_monitor.get_status(user_id)
        
        logger.info(f"[CONFIG UPDATE] Usuário {user_id} atualizado: autotrade={request.autotrade}, amount={request.amount}, cooldown={request.cooldown}")
        
        return {
            "status": "ok",
            "user_id": user_id,
            "config": {
                "autotrade": status.enabled if status else None,
                "amount": status.amount if status else None,
                "strategy_name": status.strategy_name if status else None,
                "cooldown": status.cooldown if status else None
            },
            "cache_invalidated": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar configuração: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.post("/event")
async def autotrade_event(request: Request):
    """
    Recebe eventos de mudança de autotrade do frontend ou outros serviços.
    
    Eventos suportados:
    - autotrade_enabled: Usuário ativou o autotrade
    - autotrade_disabled: Usuário desativou o autotrade
    - config_updated: Configuração foi atualizada (valor, estratégia)
    - full_refresh: Solicita refresh completo do cache
    
    Payload:
    {
        "user_id": "uuid",
        "event_type": "autotrade_enabled|autotrade_disabled|config_updated|full_refresh",
        "data": {...}  # Opcional, dados adicionais
    }
    """
    if not _autotrade_monitor:
        raise HTTPException(status_code=503, detail="AutotradeMonitor não disponível")
    
    try:
        payload = await request.json()
        user_id = payload.get("user_id")
        event_type = payload.get("event_type")
        data = payload.get("data", {})
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id é obrigatório")
        
        if not event_type:
            raise HTTPException(status_code=400, detail="event_type é obrigatório")
        
        # Processar evento
        await _autotrade_monitor.handle_webhook(user_id, event_type, data)
        
        return {
            "status": "ok",
            "event_type": event_type,
            "user_id": user_id,
            "processed": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.post("/batch")
async def autotrade_batch(request: Request):
    """
    Recebe múltiplos eventos em batch (mais eficiente para atualizações em massa).
    
    Payload:
    {
        "events": [
            {"user_id": "uuid", "event_type": "...", "data": {...}},
            ...
        ]
    }
    """
    if not _autotrade_monitor:
        raise HTTPException(status_code=503, detail="AutotradeMonitor não disponível")
    
    try:
        payload = await request.json()
        events = payload.get("events", [])
        
        if not events:
            return {"status": "ok", "processed": 0}
        
        processed = 0
        errors = []
        
        for event in events:
            try:
                user_id = event.get("user_id")
                event_type = event.get("event_type")
                data = event.get("data", {})
                
                if user_id and event_type:
                    await _autotrade_monitor.handle_webhook(user_id, event_type, data)
                    processed += 1
            except Exception as e:
                errors.append({"user_id": user_id, "error": str(e)})
        
        return {
            "status": "ok",
            "processed": processed,
            "total": len(events),
            "errors": errors if errors else None
        }
        
    except Exception as e:
        logger.error(f"Erro ao processar batch: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/status")
async def get_autotrade_status():
    """Retorna estatísticas do monitor de autotrade"""
    if not _autotrade_monitor:
        raise HTTPException(status_code=503, detail="AutotradeMonitor não disponível")
    
    return {
        "status": "ok",
        "stats": _autotrade_monitor.get_stats()
    }


@router.get("/active-users")
async def get_active_users():
    """Retorna lista de usuários com autotrade ativo (do cache)"""
    if not _autotrade_monitor:
        raise HTTPException(status_code=503, detail="AutotradeMonitor não disponível")
    
    active = await _autotrade_monitor.get_all_active()
    
    return {
        "status": "ok",
        "count": len(active),
        "users": [
            {
                "user_id": status.user_id,
                "enabled": status.enabled,
                "strategy": status.strategy_name,
                "amount": status.amount,
                "operator": status.operator,
                "can_connect": status.can_connect
            }
            for status in active.values()
        ]
    }


@router.post("/refresh/{user_id}")
async def refresh_user(user_id: str):
    """Força refresh do cache de um usuário específico"""
    if not _autotrade_monitor:
        raise HTTPException(status_code=503, detail="AutotradeMonitor não disponível")
    
    await _autotrade_monitor.invalidate_cache(user_id)
    status = await _autotrade_monitor.get_status(user_id)
    
    if not status:
        raise HTTPException(status_code=404, detail=f"Usuário {user_id} não encontrado")
    
    return {
        "status": "ok",
        "user_id": user_id,
        "autotrade_enabled": status.enabled,
        "cache_refreshed": True
    }


@router.post("/full-refresh")
async def full_refresh():
    """Força refresh completo de todos os usuários"""
    if not _autotrade_monitor:
        raise HTTPException(status_code=503, detail="AutotradeMonitor não disponível")
    
    # Disparar refresh completo
    import asyncio
    asyncio.create_task(_autotrade_monitor._do_full_refresh())
    
    return {
        "status": "ok",
        "message": "Full refresh iniciado em background"
    }
