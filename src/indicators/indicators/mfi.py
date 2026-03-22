"""
MFI - Money Flow Index (Índice de Fluxo de Dinheiro)
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class MFIIndicator(BaseIndicator):
    """Money Flow Index - RSI ponderado por volume"""
    
    @property
    def name(self) -> str:
        return "MFI"
    
    @property
    def description(self) -> str:
        return "Money Flow Index - RSI com Volume"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o MFI"""
        period = self.params.get("period", 14)
        
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # Usar volume se disponível
        if "volume" in df.columns:
            volume = df["volume"]
        else:
            volume = pd.Series(1, index=df.index)
        
        # Typical Price
        typical_price = (high + low + close) / 3
        
        # Raw Money Flow
        raw_money_flow = typical_price * volume
        
        # Money Flow Direction
        money_flow_sign = typical_price.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        
        # Positive and Negative Money Flow
        positive_flow = raw_money_flow.where(money_flow_sign > 0, 0)
        negative_flow = raw_money_flow.where(money_flow_sign < 0, 0)
        
        # Sum over period
        positive_sum = positive_flow.rolling(window=period).sum()
        negative_sum = negative_flow.rolling(window=period).sum()
        
        # Money Ratio
        money_ratio = positive_sum / negative_sum
        
        # MFI = 100 - (100 / (1 + Money Ratio))
        values = 100 - (100 / (1 + money_ratio))
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(current_value)
        
        return IndicatorResult(
            indicator_type="MFI",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={"overbought": 80, "oversold": 20}
        )
    
    def _generate_signal(self, current_value: float) -> str:
        """Gera sinal baseado no MFI"""
        if current_value is None:
            return "neutral"
        
        if current_value > 80:
            return "sell"
        elif current_value < 20:
            return "buy"
        
        return "neutral"
