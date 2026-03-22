"""
VWAP - Volume Weighted Average Price (Preço Médio Ponderado por Volume)
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class VWAPIndicator(BaseIndicator):
    """Preço Médio Ponderado por Volume"""
    
    @property
    def name(self) -> str:
        return "VWAP"
    
    @property
    def description(self) -> str:
        return "Volume Weighted Average Price"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o VWAP"""
        period = self.params.get("period", 14)
        
        # Verifica se tem volume, se não usa tick count
        if "volume" in df.columns:
            volume = df["volume"]
        else:
            volume = pd.Series(1, index=df.index)
        
        # Typical price = (high + low + close) / 3
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        
        # VWAP = cumulative(typical_price * volume) / cumulative(volume)
        tp_vol = typical_price * volume
        
        values = tp_vol.rolling(window=period).sum() / volume.rolling(window=period).sum()
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(df["close"], values)
        
        return IndicatorResult(
            indicator_type="VWAP",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None
        )
    
    def _generate_signal(self, price: pd.Series, vwap: pd.Series) -> str:
        """Gera sinal baseado em cruzamento de preço com VWAP"""
        if len(price) < 2 or len(vwap) < 2:
            return "neutral"
        
        last_price = price.iloc[-1]
        prev_price = price.iloc[-2]
        last_vwap = vwap.iloc[-1]
        prev_vwap = vwap.iloc[-2]
        
        if prev_price < prev_vwap and last_price > last_vwap:
            return "buy"
        elif prev_price > prev_vwap and last_price < last_vwap:
            return "sell"
        
        if last_price > last_vwap:
            return "buy_weak"
        elif last_price < last_vwap:
            return "sell_weak"
        
        return "neutral"
