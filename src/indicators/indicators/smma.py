"""
SMMA - Smoothed Moving Average (Média Móvel Suavizada)
Também conhecida como RMA (Running Moving Average) ou Modified Moving Average
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class SMMAIndicator(BaseIndicator):
    """Média Móvel Suavizada"""
    
    @property
    def name(self) -> str:
        return "SMMA"
    
    @property
    def description(self) -> str:
        return "Smoothed Moving Average - Média Móvel Suavizada"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula a SMMA"""
        period = self.params.get("period", 14)
        close = df["close"]
        
        # SMMA = EMA com alpha = 1/period
        values = close.ewm(alpha=1/period, adjust=False).mean()
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(close, values)
        
        return IndicatorResult(
            indicator_type="SMMA",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None
        )
    
    def _generate_signal(self, price: pd.Series, smma: pd.Series) -> str:
        """Gera sinal baseado em cruzamento de preço com média"""
        if len(price) < 2 or len(smma) < 2:
            return "neutral"
        
        last_price = price.iloc[-1]
        prev_price = price.iloc[-2]
        last_smma = smma.iloc[-1]
        prev_smma = smma.iloc[-2]
        
        if prev_price < prev_smma and last_price > last_smma:
            return "buy"
        elif prev_price > prev_smma and last_price < last_smma:
            return "sell"
        
        if last_price > last_smma:
            return "buy_weak"
        elif last_price < last_smma:
            return "sell_weak"
        
        return "neutral"
