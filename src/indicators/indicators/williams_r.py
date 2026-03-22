"""
Williams %R - Williams Percent Range
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class WilliamsRIndicator(BaseIndicator):
    """Williams %R - Oscilador de momento similar ao Stochastic"""
    
    @property
    def name(self) -> str:
        return "WILLIAMS_R"
    
    @property
    def description(self) -> str:
        return "Williams Percent Range"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o Williams %R"""
        period = self.params.get("period", 14)
        
        highest_high = df["high"].rolling(window=period).max()
        lowest_low = df["low"].rolling(window=period).min()
        
        # Williams %R = (Highest High - Close) / (Highest High - Lowest Low) * -100
        values = ((highest_high - df["close"]) / (highest_high - lowest_low)) * -100
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(current_value)
        
        return IndicatorResult(
            indicator_type="WILLIAMS_R",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={"overbought": -20, "oversold": -80}
        )
    
    def _generate_signal(self, current_value: float) -> str:
        """Gera sinal baseado no Williams %R"""
        if current_value is None:
            return "neutral"
        
        if current_value > -20:
            return "sell"
        elif current_value < -80:
            return "buy"
        
        return "neutral"
