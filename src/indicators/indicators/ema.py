"""
EMA - Exponential Moving Average (Média Móvel Exponencial)
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class EMAIndicator(BaseIndicator):
    """Média Móvel Exponencial"""
    
    @property
    def name(self) -> str:
        return "EMA"
    
    @property
    def description(self) -> str:
        return "Média Móvel Exponencial"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula a EMA"""
        period = self.params.get("period", 14)
        close = df["close"]
        
        values = close.ewm(span=period, adjust=False).mean()
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(close, values)
        
        return IndicatorResult(
            indicator_type="EMA",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None
        )
    
    def _generate_signal(self, price: pd.Series, ma: pd.Series) -> str:
        """Gera sinal baseado em cruzamento de preço com média"""
        if len(price) < 2 or len(ma) < 2:
            return "neutral"
        
        last_price = price.iloc[-1]
        prev_price = price.iloc[-2]
        last_ma = ma.iloc[-1]
        prev_ma = ma.iloc[-2]
        
        if prev_price < prev_ma and last_price > last_ma:
            return "buy"
        elif prev_price > prev_ma and last_price < last_ma:
            return "sell"
        
        if last_price > last_ma:
            return "buy_weak"
        elif last_price < last_ma:
            return "sell_weak"
        
        return "neutral"
