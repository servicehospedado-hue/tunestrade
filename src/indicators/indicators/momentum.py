"""
Momentum - Indicador de Momento
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class MomentumIndicator(BaseIndicator):
    """Indicador de Momento - mede taxa de mudança do preço"""
    
    @property
    def name(self) -> str:
        return "MOMENTUM"
    
    @property
    def description(self) -> str:
        return "Momentum - Taxa de Mudança do Preço"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o Momentum"""
        period = self.params.get("period", 10)
        close = df["close"]
        
        # Momentum = Close[t] - Close[t-n]
        values = close - close.shift(period)
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(values)
        
        return IndicatorResult(
            indicator_type="MOMENTUM",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None
        )
    
    def _generate_signal(self, momentum: pd.Series) -> str:
        """Gera sinal baseado no cruzamento do zero"""
        if len(momentum) < 2:
            return "neutral"
        
        last = momentum.iloc[-1]
        prev = momentum.iloc[-2]
        
        if prev < 0 and last > 0:
            return "buy"
        elif prev > 0 and last < 0:
            return "sell"
        elif last > 0:
            return "buy_weak"
        elif last < 0:
            return "sell_weak"
        
        return "neutral"
