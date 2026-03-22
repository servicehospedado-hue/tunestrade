"""
Rotas de Estratégias Pessoais dos Usuários
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from ..auth import APIAuthMiddleware
from ...managers.log_manager import get_manager_logger

logger = get_manager_logger("user_strategies_routes")
router = APIRouter(prefix="/user-strategies", tags=["user-strategies"])
auth_middleware = APIAuthMiddleware()

_strategy_manager = None

def set_strategy_manager(sm):
    global _strategy_manager
    _strategy_manager = sm


# ── Schemas ────────────────────────────────────────────────────────────────

class StrategyCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    indicators: list  # lista de dicts com id, name, parameters, sliderParams


class StrategyUpdateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    indicators: list


class StrategyResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str
    indicators: list
    is_active: bool
    created_at: str
    updated_at: str


class StrategyToggleRequest(BaseModel):
    is_active: bool


# ── Helpers ────────────────────────────────────────────────────────────────

def _dao():
    from ...database.user_strategy_dao import get_user_strategy_dao
    dao = get_user_strategy_dao()
    if not dao:
        raise HTTPException(status_code=503, detail="Banco de dados não disponível")
    return dao


def _to_response(s) -> StrategyResponse:
    return StrategyResponse(
        id=str(s.id),
        user_id=str(s.user_id),
        name=s.name,
        description=s.description or "",
        indicators=s.indicators or [],
        is_active=s.is_active,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
    )


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("", response_model=List[StrategyResponse])
async def list_strategies(auth: dict = Depends(auth_middleware)):
    """Lista todas as estratégias do usuário logado"""
    user_id = auth["user_id"]
    strategies = await _dao().get_by_user(user_id)
    return [_to_response(s) for s in strategies]


@router.post("", response_model=StrategyResponse, status_code=201)
async def create_strategy(request: StrategyCreateRequest, auth: dict = Depends(auth_middleware)):
    """Cria uma nova estratégia pessoal"""
    user_id = auth["user_id"]
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="Nome da estratégia é obrigatório")
    if not request.indicators:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um indicador")

    strategy = await _dao().create(
        user_id=user_id,
        name=request.name.strip(),
        description=request.description or "",
        indicators=request.indicators,
    )
    if not strategy:
        raise HTTPException(status_code=500, detail="Erro ao criar estratégia")
    return _to_response(strategy)


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(strategy_id: str, request: StrategyUpdateRequest, auth: dict = Depends(auth_middleware)):
    """Atualiza uma estratégia pessoal"""
    user_id = auth["user_id"]
    updated = await _dao().update(
        strategy_id=strategy_id,
        user_id=user_id,
        name=request.name.strip(),
        description=request.description or "",
        indicators=request.indicators,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Estratégia não encontrada")

    if _strategy_manager:
        _strategy_manager.invalidate_user_strategy_cache(user_id)

    strategy = await _dao().get_by_id(strategy_id, user_id)
    return _to_response(strategy)


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(strategy_id: str, auth: dict = Depends(auth_middleware)):
    """Remove uma estratégia pessoal"""
    user_id = auth["user_id"]
    deleted = await _dao().delete(strategy_id=strategy_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Estratégia não encontrada")
    if _strategy_manager:
        _strategy_manager.invalidate_user_strategy_cache(user_id)


@router.patch("/{strategy_id}/toggle", response_model=StrategyResponse)
async def toggle_strategy(strategy_id: str, request: StrategyToggleRequest, auth: dict = Depends(auth_middleware)):
    """Ativa ou desativa uma estratégia pessoal"""
    user_id = auth["user_id"]
    ok = await _dao().set_active(
        strategy_id=strategy_id,
        user_id=user_id,
        is_active=request.is_active,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Estratégia não encontrada")

    if _strategy_manager:
        _strategy_manager.invalidate_user_strategy_cache(user_id)

    strategy = await _dao().get_by_id(strategy_id, user_id)
    return _to_response(strategy)
