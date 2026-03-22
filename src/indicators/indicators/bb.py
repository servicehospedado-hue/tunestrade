"""
BB - Bollinger Bands (Bandas de Bollinger)
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class BBIndicator(BaseIndicator):
    """Bandas de Bollinger"""
    
    @property
    def name(self) -> str:
        return "BB"
    
    @property
    def description(self) -> str:
        return "Bandas de Bollinger"
    
    @property
    def required_params(self) -> list:
        return ["period", "std_dev"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula as Bandas de Bollinger"""
        period = self.params.get("period", 20)
        std_dev = self.params.get("std_dev", 2.0)
        
        close = df["close"]
        
        sma = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        
        # %B (posição relativa na banda)
        bb_position = (close - lower) / (upper - lower)
        
        current_value = bb_position.iloc[-1] if not bb_position.empty else None
        previous_value = bb_position.iloc[-2] if len(bb_position) > 1 else None
        
        signal = self._generate_signal(close.iloc[-1], upper.iloc[-1], lower.iloc[-1])
        
        return IndicatorResult(
            indicator_type="BB",
            values=bb_position,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={
                "upper": float(upper.iloc[-1]) if not upper.empty else None,
                "middle": float(sma.iloc[-1]) if not sma.empty else None,
                "lower": float(lower.iloc[-1]) if not lower.empty else None
            }
        )
    
    def _generate_signal(self, last_price: float, last_upper: float, last_lower: float) -> str:
        """Gera sinal baseado na posição do preço nas bandas"""
        if last_price > last_upper:
            return "sell"
        elif last_price < last_lower:
            return "buy"
        
        return "neutral"
