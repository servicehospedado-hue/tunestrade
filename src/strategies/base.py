"""
Classe base para estratégias de trading
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
import pandas as pd


@dataclass
class StrategyResult:
    """Resultado da análise de uma estratégia"""
    strategy_name: str
    asset: str
    timeframe: int
    direction: str  # "CALL", "PUT", "NEUTRAL"
    entry_price: Optional[float] = None
    confidence: float = 0.0  # 0.0 a 1.0
    indicators: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte resultado para dicionário"""
        return {
            "strategy": self.strategy_name,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "confidence": self.confidence,
            "indicators": self.indicators,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }


class BaseStrategy(ABC):
    """Interface base para todas as estratégias"""
    
    def __init__(self, timeframe: int = 5, min_confidence: float = 0.7):
        self.timeframe = timeframe
        self.min_confidence = min_confidence
        self._indicators: List[Any] = []
        self._last_signal_time: Optional[float] = None
        self._cooldown_seconds: float = 5.0  # Cooldown entre sinais
        
    @property
    @abstractmethod
    def name(self) -> str:
        """Nome da estratégia"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Descrição da estratégia"""
        pass
    
    @abstractmethod
    def setup_indicators(self) -> None:
        """Configura indicadores usados pela estratégia"""
        pass
    
    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        """
        Analisa dados e retorna resultado da estratégia.
        
        Args:
            df: DataFrame com colunas 'timestamp' e 'close' (price)
            
        Returns:
            StrategyResult com direção, confiança e indicadores
        """
        pass
    
    def validate_data(self, df: pd.DataFrame, min_rows: int = 30) -> bool:
        """Valida se há dados suficientes para análise"""
        if df is None or df.empty:
            return False
        if len(df) < min_rows:
            return False
        if 'close' not in df.columns:
            return False
        return True
    
    def prepare_dataframe(self, ticks: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Prepara DataFrame a partir de lista de ticks.
        
        Args:
            ticks: Lista de dicts com 'timestamp' e 'price'
            
        Returns:
            DataFrame com colunas timestamp, close, high, low, open
        """
        if not ticks:
            return pd.DataFrame()
        
        df = pd.DataFrame(ticks)
        
        # Renomear price para close
        if 'price' in df.columns:
            df['close'] = df['price']
        
        # Ordenar por timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Como só temos close, usar close para high, low, open
        # Isso permite usar indicadores que precisam dessas colunas
        df['high'] = df['close']
        df['low'] = df['close']
        df['open'] = df['close'].shift(1).fillna(df['close'])
        
        return df
    
    def calculate_price_metrics(self, df: pd.DataFrame, periods: List[int] = [1, 3, 10, 20]) -> Dict[str, Any]:
        """
        Calcula métricas derivadas do preço.
        
        Args:
            df: DataFrame com coluna 'close'
            periods: Períodos para cálculo de variação
            
        Returns:
            Dict com variação, velocidade, aceleração, volatilidade
        """
        close = df['close']
        metrics = {}
        
        for period in periods:
            if len(close) > period:
                # Variação absoluta
                variation = close.iloc[-1] - close.iloc[-period-1]
                metrics[f'variation_{period}'] = float(variation)
                
                # Variação percentual
                pct_change = (variation / close.iloc[-period-1]) * 100 if close.iloc[-period-1] != 0 else 0
                metrics[f'pct_change_{period}'] = float(pct_change)
        
        # Velocidade (mudança por segundo)
        if len(df) >= 2:
            time_diff = df['timestamp'].iloc[-1] - df['timestamp'].iloc[-2]
            if time_diff > 0:
                velocity = (close.iloc[-1] - close.iloc[-2]) / time_diff
                metrics['velocity'] = float(velocity)
        
        # Aceleração (mudança da velocidade)
        if len(df) >= 3:
            time_diff1 = df['timestamp'].iloc[-1] - df['timestamp'].iloc[-2]
            time_diff2 = df['timestamp'].iloc[-2] - df['timestamp'].iloc[-3]
            if time_diff1 > 0 and time_diff2 > 0:
                v1 = (close.iloc[-1] - close.iloc[-2]) / time_diff1
                v2 = (close.iloc[-2] - close.iloc[-3]) / time_diff2
                acceleration = v1 - v2
                metrics['acceleration'] = float(acceleration)
        
        # Volatilidade (desvio padrão)
        for period in [5, 10, 20]:
            if len(close) >= period:
                volatility = close.tail(period).std()
                metrics[f'volatility_{period}'] = float(volatility)
        
        return metrics
    
    def can_emit_signal(self) -> bool:
        """Verifica se pode emitir sinal (respeitando cooldown)"""
        if self._last_signal_time is None:
            return True
        
        elapsed = datetime.now().timestamp() - self._last_signal_time
        return elapsed >= self._cooldown_seconds
    
    def mark_signal_emitted(self):
        """Marca que um sinal foi emitido"""
        self._last_signal_time = datetime.now().timestamp()
