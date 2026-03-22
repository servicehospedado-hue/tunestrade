"""
RSI - Relative Strength Index (Índice de Força Relativa)
"""
import pandas as pd
import numpy as np
from ..base import BaseIndicator, IndicatorResult


class RSIIndicator(BaseIndicator):
    """Índice de Força Relativa"""
    
    @property
    def name(self) -> str:
        return "RSI"
    
    @property
    def description(self) -> str:
        return "Índice de Força Relativa"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o RSI"""
        period = self.params.get("period", 14)
        close = df["close"]
        
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        values = 100 - (100 / (1 + rs))
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(current_value)
        
        return IndicatorResult(
            indicator_type="RSI",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={"overbought": 70, "oversold": 30}
        )
    
    def _generate_signal(self, current_value: float) -> str:
        """Gera sinal baseado no valor do RSI"""
        if current_value is None:
            return "neutral"
        
        if current_value > 70:
            return "sell"
        elif current_value < 30:
            return "buy"
        
        return "neutral"
