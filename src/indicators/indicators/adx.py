"""
ADX - Average Directional Index (Índice Direcional Médio)
"""
import pandas as pd
import numpy as np
from ..base import BaseIndicator, IndicatorResult


class ADXIndicator(BaseIndicator):
    """Average Directional Index - mede força da tendência"""
    
    @property
    def name(self) -> str:
        return "ADX"
    
    @property
    def description(self) -> str:
        return "Average Directional Index - Força da Tendência"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o ADX"""
        period = self.params.get("period", 14)
        
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # +DM and -DM
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        plus_dm[plus_dm <= minus_dm] = 0
        minus_dm[minus_dm <= plus_dm] = 0
        
        # Smoothed TR, +DM, -DM
        atr = tr.ewm(alpha=1/period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
        
        # DX and ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        values = dx.ewm(alpha=1/period, adjust=False).mean()
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(current_value, plus_di.iloc[-1] if not plus_di.empty else None, minus_di.iloc[-1] if not minus_di.empty else None)
        
        return IndicatorResult(
            indicator_type="ADX",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={
                "plus_di": float(plus_di.iloc[-1]) if not plus_di.empty else None,
                "minus_di": float(minus_di.iloc[-1]) if not minus_di.empty else None,
                "strong_trend": 25
            }
        )
    
    def _generate_signal(self, adx: float, plus_di: float, minus_di: float) -> str:
        """Gera sinal baseado no ADX e DI"""
        if adx is None or plus_di is None or minus_di is None:
            return "neutral"
        
        if adx > 25:
            if plus_di > minus_di:
                return "buy"
            else:
                return "sell"
        
        return "neutral"
