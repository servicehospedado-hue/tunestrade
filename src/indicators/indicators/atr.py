"""
ATR - Average True Range
"""
import pandas as pd
import numpy as np
from ..base import BaseIndicator, IndicatorResult


class ATRIndicator(BaseIndicator):
    """Average True Range"""
    
    @property
    def name(self) -> str:
        return "ATR"
    
    @property
    def description(self) -> str:
        return "Average True Range - Volatilidade"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o ATR"""
        period = self.params.get("period", 14)
        
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        values = true_range.rolling(period).mean()
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        # ATR não tem sinal direto, apenas indica volatilidade
        signal = "neutral"
        
        return IndicatorResult(
            indicator_type="ATR",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={"volatility": float(current_value) if current_value else None}
        )
