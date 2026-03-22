"""
Chaikin Money Flow (CMF) - Fluxo de Dinheiro de Chaikin
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class ChaikinMoneyFlowIndicator(BaseIndicator):
    """Chaikin Money Flow - mede compra/venda pressão acumulada"""
    
    @property
    def name(self) -> str:
        return "CMF"
    
    @property
    def description(self) -> str:
        return "Chaikin Money Flow - Pressão de Compra/Venda"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o Chaikin Money Flow"""
        period = self.params.get("period", 20)
        
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # Usar volume se disponível
        if "volume" in df.columns:
            volume = df["volume"]
        else:
            volume = pd.Series(1, index=df.index)
        
        # Money Flow Multiplier = ((Close - Low) - (High - Close)) / (High - Low)
        money_flow_multiplier = ((close - low) - (high - close)) / (high - low)
        money_flow_multiplier = money_flow_multiplier.fillna(0)  # Handle division by zero
        
        # Money Flow Volume
        money_flow_volume = money_flow_multiplier * volume
        
        # CMF = Sum(MFV) / Sum(Volume)
        values = money_flow_volume.rolling(window=period).sum() / volume.rolling(window=period).sum()
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(values)
        
        return IndicatorResult(
            indicator_type="CMF",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={"overbought": 0.1, "oversold": -0.1}
        )
    
    def _generate_signal(self, cmf: pd.Series) -> str:
        """Gera sinal baseado no CMF"""
        if len(cmf) < 2:
            return "neutral"
        
        last = cmf.iloc[-1]
        prev = cmf.iloc[-2]
        
        if prev < 0 and last > 0:
            return "buy"
        elif prev > 0 and last < 0:
            return "sell"
        elif last > 0.1:
            return "buy_weak"
        elif last < -0.1:
            return "sell_weak"
        
        return "neutral"
