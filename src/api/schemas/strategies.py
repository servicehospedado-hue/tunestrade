"""
Schemas para estratégias
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class IndicatorConfigRequest(BaseModel):
    """Configuração de indicador"""
    type: str
    params: Dict[str, Any]


class SignalConfigRequest(BaseModel):
    """Configuração de sinais"""
    asset: str
    timeframe: int
    indicators: List[IndicatorConfigRequest]
    min_confidence: float = 0.7
    signal_types: List[str] = ["buy", "sell"]
    max_concurrent_signals: int = 3
    cooldown_seconds: int = 60


class AnalyzeRequest(BaseModel):
    """Request de análise"""
    user_id: str
    asset: str
    timeframe: int


class StrategyInfo(BaseModel):
    """Informações de uma estratégia"""
    id: str
    name: str
    description: str
    timeframe: int
    min_confidence: float
    indicators: List[str]
    indicator_weights: Dict[str, float]
    params: Dict[str, Any]
    category: str


class StrategiesListResponse(BaseModel):
    """Lista de estratégias"""
    strategies: List[StrategyInfo]
    total: int


class IndicatorInfo(BaseModel):
    """Informações de indicador disponível"""
    type: str
    name: str
    params: List[str]
