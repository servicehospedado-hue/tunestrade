"""
WMA - Weighted Moving Average (Média Móvel Ponderada)
"""
import pandas as pd
import numpy as np
from ..base import BaseIndicator, IndicatorResult


class WMAIndicator(BaseIndicator):
    """Média Móvel Ponderada"""
    
    @property
    def name(self) -> str:
        return "WMA"
    
    @property
    def description(self) -> str:
        return "Média Móvel Ponderada"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula a WMA"""
        period = self.params.get("period", 14)
        close = df["close"]
        
        # Pesos lineares: period, period-1, ..., 1
        weights = np.arange(1, period + 1)
        
        def wma_calc(x):
            return np.dot(x, weights) / weights.sum()
        
        values = close.rolling(window=period).apply(wma_calc, raw=True)
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(close, values)
        
        return IndicatorResult(
            indicator_type="WMA",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None
        )
    
    def _generate_signal(self, price: pd.Series, wma: pd.Series) -> str:
        """Gera sinal baseado em cruzamento de preço com média"""
        if len(price) < 2 or len(wma) < 2:
            return "neutral"
        
        last_price = price.iloc[-1]
        prev_price = price.iloc[-2]
        last_wma = wma.iloc[-1]
        prev_wma = wma.iloc[-2]
        
        if prev_price < prev_wma and last_price > last_wma:
            return "buy"
        elif prev_price > prev_wma and last_price < last_wma:
            return "sell"
        
        if last_price > last_wma:
            return "buy_weak"
        elif last_price < last_wma:
            return "sell_weak"
        
        return "neutral"
