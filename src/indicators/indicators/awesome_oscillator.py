"""
Awesome Oscillator - Oscilador Incrível de Bill Williams
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class AwesomeOscillatorIndicator(BaseIndicator):
    """Awesome Oscillator - mede momentum do mercado usando médias móveis simples"""
    
    @property
    def name(self) -> str:
        return "AWESOME_OSCILLATOR"
    
    @property
    def description(self) -> str:
        return "Awesome Oscillator - Mede momentum do mercado"
    
    @property
    def required_params(self) -> list:
        return ["fast", "slow"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o Awesome Oscillator"""
        fast = self.params.get("fast", 5)
        slow = self.params.get("slow", 34)
        
        # Median Price = (High + Low) / 2
        median_price = (df["high"] + df["low"]) / 2
        
        # SMA do Median Price
        sma_fast = median_price.rolling(window=fast).mean()
        sma_slow = median_price.rolling(window=slow).mean()
        
        # AO = SMA5 - SMA34
        values = sma_fast - sma_slow
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(values)
        
        return IndicatorResult(
            indicator_type="AWESOME_OSCILLATOR",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None
        )
    
    def _generate_signal(self, ao: pd.Series) -> str:
        """Gera sinal baseado no cruzamento do zero"""
        if len(ao) < 2:
            return "neutral"
        
        last = ao.iloc[-1]
        prev = ao.iloc[-2]
        
        if prev < 0 and last > 0:
            return "buy"
        elif prev > 0 and last < 0:
            return "sell"
        elif last > 0:
            return "buy_weak"
        elif last < 0:
            return "sell_weak"
        
        return "neutral"
