"""
Ultimate Oscillator - Oscilador Ultimate de Larry Williams
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class UltimateOscillatorIndicator(BaseIndicator):
    """Ultimate Oscillator - combina três períodos diferentes para reduzir ruído"""
    
    @property
    def name(self) -> str:
        return "ULTIMATE_OSCILLATOR"
    
    @property
    def description(self) -> str:
        return "Ultimate Oscillator - Combinação de 3 períodos"
    
    @property
    def required_params(self) -> list:
        return ["short", "medium", "long"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o Ultimate Oscillator"""
        short = self.params.get("short", 7)
        medium = self.params.get("medium", 14)
        long = self.params.get("long", 28)
        
        close = df["close"]
        low = df["low"]
        high = df["high"]
        
        # Buying Pressure = Close - True Low
        true_low = pd.concat([low, close.shift(1)], axis=1).min(axis=1)
        buying_pressure = close - true_low
        
        # True Range
        true_high = pd.concat([high, close.shift(1)], axis=1).max(axis=1)
        true_range = true_high - true_low
        
        # Calcula para 3 períodos
        def calc_ratio(bp, tr, period):
            return bp.rolling(window=period).sum() / tr.rolling(window=period).sum()
        
        ratio_short = calc_ratio(buying_pressure, true_range, short)
        ratio_medium = calc_ratio(buying_pressure, true_range, medium)
        ratio_long = calc_ratio(buying_pressure, true_range, long)
        
        # UO = 100 * [(4*RS7) + (2*RS14) + RS28] / (4+2+1)
        values = 100 * ((4 * ratio_short) + (2 * ratio_medium) + ratio_long) / 7
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(current_value)
        
        return IndicatorResult(
            indicator_type="ULTIMATE_OSCILLATOR",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={"overbought": 70, "oversold": 30}
        )
    
    def _generate_signal(self, current_value: float) -> str:
        """Gera sinal baseado no Ultimate Oscillator"""
        if current_value is None:
            return "neutral"
        
        if current_value > 70:
            return "sell"
        elif current_value < 30:
            return "buy"
        
        return "neutral"
