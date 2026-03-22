"""
SuperTrend - Indicador de tendência baseado em ATR
"""
import pandas as pd
import numpy as np
from ..base import BaseIndicator, IndicatorResult


class SuperTrendIndicator(BaseIndicator):
    """SuperTrend - identifica tendência usando ATR e bandas"""
    
    @property
    def name(self) -> str:
        return "SUPER_TREND"
    
    @property
    def description(self) -> str:
        return "SuperTrend - Indicador de Tendência baseado em ATR"
    
    @property
    def required_params(self) -> list:
        return ["period", "multiplier"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o SuperTrend"""
        period = self.params.get("period", 10)
        multiplier = self.params.get("multiplier", 3.0)
        
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        # HL2 (média de high e low)
        hl2 = (high + low) / 2
        
        # Bandas superior e inferior
        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)
        
        # Calcula SuperTrend
        supertrend = pd.Series(0.0, index=df.index)
        trend = pd.Series(True, index=df.index)  # True = bull, False = bear
        
        for i in range(1, len(close)):
            if close.iloc[i] > upper_band.iloc[i-1]:
                trend.iloc[i] = True
            elif close.iloc[i] < lower_band.iloc[i-1]:
                trend.iloc[i] = False
            else:
                trend.iloc[i] = trend.iloc[i-1]
                
                if trend.iloc[i] and lower_band.iloc[i] < lower_band.iloc[i-1]:
                    lower_band.iloc[i] = lower_band.iloc[i-1]
                if not trend.iloc[i] and upper_band.iloc[i] > upper_band.iloc[i-1]:
                    upper_band.iloc[i] = upper_band.iloc[i-1]
            
            if trend.iloc[i]:
                supertrend.iloc[i] = lower_band.iloc[i]
            else:
                supertrend.iloc[i] = upper_band.iloc[i]
        
        values = supertrend
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(close.iloc[-1], current_value, trend.iloc[-1])
        
        return IndicatorResult(
            indicator_type="SUPER_TREND",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={"trend": "bull" if trend.iloc[-1] else "bear"}
        )
    
    def _generate_signal(self, close: float, supertrend: float, trend: bool) -> str:
        """Gera sinal baseado na tendência do SuperTrend"""
        if close is None or supertrend is None:
            return "neutral"
        
        if trend and close > supertrend:
            return "buy"
        elif not trend and close < supertrend:
            return "sell"
        
        return "neutral"
