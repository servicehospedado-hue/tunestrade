"""
Stochastic - Oscilador Estocástico
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class StochasticIndicator(BaseIndicator):
    """Oscilador Estocástico"""
    
    @property
    def name(self) -> str:
        return "Stochastic"
    
    @property
    def description(self) -> str:
        return "Oscilador Estocástico"
    
    @property
    def required_params(self) -> list:
        return ["k_period", "d_period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o Oscilador Estocástico"""
        k_period = self.params.get("k_period", 14)
        d_period = self.params.get("d_period", 3)
        
        low_min = df["low"].rolling(window=k_period).min()
        high_max = df["high"].rolling(window=k_period).max()
        
        k = 100 * ((df["close"] - low_min) / (high_max - low_min))
        d = k.rolling(window=d_period).mean()
        
        current_value = k.iloc[-1] if not k.empty else None
        previous_value = k.iloc[-2] if len(k) > 1 else None
        
        signal = self._generate_signal(current_value)
        
        return IndicatorResult(
            indicator_type="Stochastic",
            values=k,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={
                "k_line": float(current_value) if current_value else None,
                "d_line": float(d.iloc[-1]) if not d.empty else None,
                "overbought": 80,
                "oversold": 20
            }
        )
    
    def _generate_signal(self, current_value: float) -> str:
        """Gera sinal baseado no valor do Stochastic"""
        if current_value is None:
            return "neutral"
        
        if current_value > 80:
            return "sell"
        elif current_value < 20:
            return "buy"
        
        return "neutral"
