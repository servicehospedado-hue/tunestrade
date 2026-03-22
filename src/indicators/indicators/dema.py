"""
DEMA - Double Exponential Moving Average (Média Móvel Exponencial Dupla)
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class DEMAIndicator(BaseIndicator):
    """Média Móvel Exponencial Dupla - reduz lag da EMA"""
    
    @property
    def name(self) -> str:
        return "DEMA"
    
    @property
    def description(self) -> str:
        return "Double Exponential Moving Average"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula a DEMA"""
        period = self.params.get("period", 14)
        close = df["close"]
        
        # EMA do preço
        ema1 = close.ewm(span=period, adjust=False).mean()
        # EMA da EMA
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        
        # DEMA = 2 * EMA1 - EMA2
        values = 2 * ema1 - ema2
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(close, values)
        
        return IndicatorResult(
            indicator_type="DEMA",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None
        )
    
    def _generate_signal(self, price: pd.Series, dema: pd.Series) -> str:
        """Gera sinal baseado em cruzamento de preço com média"""
        if len(price) < 2 or len(dema) < 2:
            return "neutral"
        
        last_price = price.iloc[-1]
        prev_price = price.iloc[-2]
        last_dema = dema.iloc[-1]
        prev_dema = dema.iloc[-2]
        
        if prev_price < prev_dema and last_price > last_dema:
            return "buy"
        elif prev_price > prev_dema and last_price < last_dema:
            return "sell"
        
        if last_price > last_dema:
            return "buy_weak"
        elif last_price < last_dema:
            return "sell_weak"
        
        return "neutral"
