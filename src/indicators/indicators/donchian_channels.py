"""
Donchian Channels - Canais de Donchian
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class DonchianChannelsIndicator(BaseIndicator):
    """Donchian Channels - bandas baseadas em máximos e mínimos"""
    
    @property
    def name(self) -> str:
        return "DONCHIAN_CHANNELS"
    
    @property
    def description(self) -> str:
        return "Donchian Channels - Canais de Máximos e Mínimos"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula os Donchian Channels"""
        period = self.params.get("period", 20)
        
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # Upper band = Highest High
        upper_band = high.rolling(window=period).max()
        # Lower band = Lowest Low
        lower_band = low.rolling(window=period).min()
        # Middle line
        middle_line = (upper_band + lower_band) / 2
        
        # %D (posição relativa)
        donchian_position = (close - lower_band) / (upper_band - lower_band)
        
        current_value = donchian_position.iloc[-1] if not donchian_position.empty else None
        previous_value = donchian_position.iloc[-2] if len(donchian_position) > 1 else None
        
        signal = self._generate_signal(close, upper_band, lower_band)
        
        return IndicatorResult(
            indicator_type="DONCHIAN_CHANNELS",
            values=donchian_position,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={
                "upper": float(upper_band.iloc[-1]) if not upper_band.empty else None,
                "middle": float(middle_line.iloc[-1]) if not middle_line.empty else None,
                "lower": float(lower_band.iloc[-1]) if not lower_band.empty else None
            }
        )
    
    def _generate_signal(self, close: pd.Series, upper: pd.Series, lower: pd.Series) -> str:
        """Gera sinal baseado em breakout das bandas"""
        if len(close) < 2 or len(upper) < 2 or len(lower) < 2:
            return "neutral"
        
        last_close = close.iloc[-1]
        prev_close = close.iloc[-2]
        last_upper = upper.iloc[-1]
        prev_upper = upper.iloc[-2]
        last_lower = lower.iloc[-1]
        prev_lower = lower.iloc[-2]
        
        # Breakout para cima
        if prev_close <= prev_upper and last_close > last_upper:
            return "buy"
        # Breakout para baixo
        elif prev_close >= prev_lower and last_close < last_lower:
            return "sell"
        
        return "neutral"
