"""
Modelos de dados do sistema
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class TradeDirection(Enum):
    """Direção do trade"""
    CALL = "call"
    PUT = "put"


class TradeStatus(Enum):
    """Status do trade"""
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    WON = "won"
    LOST = "lost"
    DRAW = "draw"
    CANCELLED = "cancelled"


@dataclass
class Candle:
    """Representa um candle de preço"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    asset: str
    timeframe: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'asset': self.asset,
            'timeframe': self.timeframe
        }


@dataclass
class IndicatorValue:
    """Valor de um indicador em um momento específico"""
    timestamp: datetime
    value: float
    signal: Optional[str] = None
    

@dataclass
class IndicatorData:
    """Dados completos de um indicador"""
    name: str
    type: str
    params: Dict[str, Any]
    asset: str
    timeframe: int
    values: List[IndicatorValue] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class Trade:
    """Representa uma operação de trading"""
    id: str
    user_id: str
    asset: str
    direction: TradeDirection
    amount: float
    entry_price: float
    exit_price: Optional[float] = None
    entry_time: datetime = field(default_factory=datetime.now)
    exit_time: Optional[datetime] = None
    duration: int = 60  # segundos
    status: TradeStatus = TradeStatus.PENDING
    profit_loss: Optional[float] = None
    signal_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserBalance:
    """Saldo do usuário"""
    user_id: str
    balance: float
    currency: str = "USD"
    demo: bool = True
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class Strategy:
    """Configuração de estratégia"""
    id: str
    user_id: str
    name: str
    asset: str
    timeframe: int
    indicators: List[Dict[str, Any]] = field(default_factory=list)
    entry_conditions: List[Dict[str, Any]] = field(default_factory=list)
    exit_conditions: List[Dict[str, Any]] = field(default_factory=list)
    enabled: bool = True
    risk_per_trade: float = 1.0  # % do saldo
    max_trades_per_day: int = 10
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Alert:
    """Alerta do sistema"""
    id: str
    user_id: str
    type: str
    message: str
    severity: str  # info, warning, error, critical
    created_at: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
