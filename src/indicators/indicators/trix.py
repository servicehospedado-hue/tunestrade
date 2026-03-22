"""
TRIX - Triple Exponential Moving Average
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class TRIXIndicator(BaseIndicator):
    """TRIX - Triple EMA do Triple EMA do Triple EMA"""
    
    @property
    def name(self) -> str:
        return "TRIX"
    
    @property
    def description(self) -> str:
        return "TRIX - Triple Exponential Moving Average"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o TRIX"""
        period = self.params.get("period", 15)
        
        close = df["close"]
        
        # Triple EMA
        ema1 = close.ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        ema3 = ema2.ewm(span=period, adjust=False).mean()
        
        # TRIX = Percentage change in Triple EMA
        values = ema3.pct_change() * 100
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(values)
        
        return IndicatorResult(
            indicator_type="TRIX",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None
        )
    
    def _generate_signal(self, trix: pd.Series) -> str:
        """Gera sinal baseado no TRIX"""
        if len(trix) < 2:
            return "neutral"
        
        last = trix.iloc[-1]
        prev = trix.iloc[-2]
        
        if prev < 0 and last > 0:
            return "buy"
        elif prev > 0 and last < 0:
            return "sell"
        elif last > 0:
            return "buy_weak"
        elif last < 0:
            return "sell_weak"
        
        return "neutral"
