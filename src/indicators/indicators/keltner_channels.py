"""
Keltner Channels - Canais de Keltner
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class KeltnerChannelsIndicator(BaseIndicator):
    """Keltner Channels - bandas baseadas em ATR"""
    
    @property
    def name(self) -> str:
        return "KELTNER_CHANNELS"
    
    @property
    def description(self) -> str:
        return "Keltner Channels - Canais baseados em ATR"
    
    @property
    def required_params(self) -> list:
        return ["ema_period", "atr_period", "multiplier"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula os Keltner Channels"""
        ema_period = self.params.get("ema_period", 20)
        atr_period = self.params.get("atr_period", 10)
        multiplier = self.params.get("multiplier", 2.0)
        
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # EMA do Typical Price como linha central
        typical_price = (high + low + close) / 3
        ema_tp = typical_price.ewm(span=ema_period, adjust=False).mean()
        
        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=atr_period).mean()
        
        # Bandas superior e inferior
        upper_band = ema_tp + (multiplier * atr)
        lower_band = ema_tp - (multiplier * atr)
        
        # %K (posição relativa)
        keltner_position = (close - lower_band) / (upper_band - lower_band)
        
        current_value = keltner_position.iloc[-1] if not keltner_position.empty else None
        previous_value = keltner_position.iloc[-2] if len(keltner_position) > 1 else None
        
        signal = self._generate_signal(close.iloc[-1], upper_band.iloc[-1], lower_band.iloc[-1])
        
        return IndicatorResult(
            indicator_type="KELTNER_CHANNELS",
            values=keltner_position,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={
                "upper": float(upper_band.iloc[-1]) if not upper_band.empty else None,
                "middle": float(ema_tp.iloc[-1]) if not ema_tp.empty else None,
                "lower": float(lower_band.iloc[-1]) if not lower_band.empty else None
            }
        )
    
    def _generate_signal(self, close: float, upper: float, lower: float) -> str:
        """Gera sinal baseado na posição nas bandas"""
        if close is None or upper is None or lower is None:
            return "neutral"
        
        if close > upper:
            return "sell"
        elif close < lower:
            return "buy"
        
        return "neutral"
