"""
Schemas Pydantic para autotrade
"""
from pydantic import BaseModel
from typing import Optional


class AutotradeToggleRequest(BaseModel):
    """Request para toggle de autotrade"""
    enabled: bool
    strategy_id: str = "scalping_5s"
    execute: str = "signal"  # 'signal' ou 'oncandle'


class AutotradeToggleResponse(BaseModel):
    """Response de toggle de autotrade"""
    success: bool
    enabled: bool
    user_id: str
    message: str


class AutotradeStatusResponse(BaseModel):
    """Response com status do autotrade"""
    enabled: bool
    amount: float
    strategy_name: str
    cooldown: str
    execute: str = "signal"
    user_id: str
    # Stops
    stop_loss_enabled: bool = False
    stop_loss_value: float = 0.0
    stop_gain_enabled: bool = False
    stop_gain_value: float = 0.0
    stop_soft_mode: bool = False
    stop_win_seq_enabled: bool = False
    stop_win_seq: int = 3
    stop_loss_seq_enabled: bool = False
    stop_loss_seq: int = 3
    stop_seq_soft_mode: bool = False
    stop_medium_enabled: bool = False
    stop_medium_pct: float = 50.0
    stop_medium_soft_mode: bool = False
    # Redução
    reduce_enabled: bool = False
    reduce_loss_trigger: int = 3
    reduce_win_exit: int = 2
    reduce_pct: float = 50.0
    # Martingale
    martingale_enabled: bool = False
    martingale_levels: int = 3
    martingale_multiplier: float = 2.0
    # Soros
    soros_enabled: bool = False
    soros_levels: int = 3
    soros_pct: float = 100.0
    # Estado de sessão
    stop_triggered: bool = False
    stop_type: Optional[str] = None


class AutotradeConfig(BaseModel):
    """Configuração de autotrade"""
    user_id: str
    autotrade: int = 0
    amount: float = 1.0
    strategy_name: str = "Scalping5s"
    cooldown: str = "60"
    execute: str = "signal"
