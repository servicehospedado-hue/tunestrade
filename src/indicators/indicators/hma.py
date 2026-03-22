"""
HMA - Hull Moving Average (Média Móvel de Hull)
"""
import pandas as pd
import numpy as np
from ..base import BaseIndicator, IndicatorResult


class HMAIndicator(BaseIndicator):
    """Média Móvel de Hull - reduz lag e aumenta suavidade"""
    
    @property
    def name(self) -> str:
        return "HMA"
    
    @property
    def description(self) -> str:
        return "Hull Moving Average - Média Móvel de Hull"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula a HMA"""
        period = self.params.get("period", 16)
        close = df["close"]
        
        half_period = period // 2
        sqrt_period = int(np.sqrt(period))
        
        # WMA do período completo
        wma_full = self._wma(close, period)
        # WMA da metade do período
        wma_half = self._wma(close, half_period)
        
        # Raw HMA = 2 * WMA(half) - WMA(full)
        raw_hma = 2 * wma_half - wma_full
        
        # HMA final = WMA do raw_hma com período sqrt
        values = self._wma(raw_hma, sqrt_period)
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(close, values)
        
        return IndicatorResult(
            indicator_type="HMA",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None
        )
    
    def _wma(self, series: pd.Series, period: int) -> pd.Series:
        """Calcula WMA auxiliar"""
        weights = np.arange(1, period + 1)
        
        def wma_calc(x):
            return np.dot(x, weights) / weights.sum()
        
        return series.rolling(window=period).apply(wma_calc, raw=True)
    
    def _generate_signal(self, price: pd.Series, hma: pd.Series) -> str:
        """Gera sinal baseado em cruzamento de preço com média"""
        if len(price) < 2 or len(hma) < 2:
            return "neutral"
        
        last_price = price.iloc[-1]
        prev_price = price.iloc[-2]
        last_hma = hma.iloc[-1]
        prev_hma = hma.iloc[-2]
        
        if prev_price < prev_hma and last_price > last_hma:
            return "buy"
        elif prev_price > prev_hma and last_price < last_hma:
            return "sell"
        
        if last_price > last_hma:
            return "buy_weak"
        elif last_price < last_hma:
            return "sell_weak"
        
        return "neutral"
