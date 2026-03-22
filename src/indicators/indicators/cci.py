"""
CCI - Commodity Channel Index (Índice do Canal de Commodities)
"""
import pandas as pd
import numpy as np
from ..base import BaseIndicator, IndicatorResult


class CCIIndicator(BaseIndicator):
    """Índice do Canal de Commodities - identifica início/fim de tendências"""
    
    @property
    def name(self) -> str:
        return "CCI"
    
    @property
    def description(self) -> str:
        return "Commodity Channel Index"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o CCI"""
        period = self.params.get("period", 20)
        
        # Typical Price
        tp = (df["high"] + df["low"] + df["close"]) / 3
        
        # SMA of Typical Price
        sma_tp = tp.rolling(window=period).mean()
        
        # Mean Deviation - cálculo manual (mad() foi depreciado)
        def mean_dev(x):
            return np.mean(np.abs(x - np.mean(x)))
        
        mean_deviation = tp.rolling(window=period).apply(mean_dev, raw=True)
        
        # CCI = (TP - SMA_TP) / (0.015 * Mean Deviation)
        values = (tp - sma_tp) / (0.015 * mean_deviation)
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(current_value)
        
        return IndicatorResult(
            indicator_type="CCI",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={"overbought": 100, "oversold": -100}
        )
    
    def _generate_signal(self, current_value: float) -> str:
        """Gera sinal baseado no CCI"""
        if current_value is None:
            return "neutral"
        
        if current_value > 100:
            return "sell"
        elif current_value < -100:
            return "buy"
        
        return "neutral"
