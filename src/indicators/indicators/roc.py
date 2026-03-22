"""
ROC - Rate of Change (Taxa de Variação)
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class ROCIndicator(BaseIndicator):
    """Rate of Change - mede a variação percentual do preço"""
    
    @property
    def name(self) -> str:
        return "ROC"
    
    @property
    def description(self) -> str:
        return "Rate of Change - Taxa de Variação Percentual"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o ROC"""
        period = self.params.get("period", 12)
        close = df["close"]
        
        # ROC = ((Close[t] - Close[t-n]) / Close[t-n]) * 100
        values = ((close - close.shift(period)) / close.shift(period)) * 100
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(values)
        
        return IndicatorResult(
            indicator_type="ROC",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None
        )
    
    def _generate_signal(self, roc: pd.Series) -> str:
        """Gera sinal baseado no cruzamento do zero"""
        if len(roc) < 2:
            return "neutral"
        
        last = roc.iloc[-1]
        prev = roc.iloc[-2]
        
        if prev < 0 and last > 0:
            return "buy"
        elif prev > 0 and last < 0:
            return "sell"
        elif last > 0:
            return "buy_weak"
        elif last < 0:
            return "sell_weak"
        
        return "neutral"
