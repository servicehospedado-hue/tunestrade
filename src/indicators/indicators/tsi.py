"""
TSI - True Strength Index (Índice de Força Verdadeira)
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class TSIIndicator(BaseIndicator):
    """True Strength Index - oscilador de momento com dupla suavização"""
    
    @property
    def name(self) -> str:
        return "TSI"
    
    @property
    def description(self) -> str:
        return "True Strength Index - Oscilador de Momento Suavizado"
    
    @property
    def required_params(self) -> list:
        return ["long_period", "short_period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o TSI"""
        long_period = self.params.get("long_period", 25)
        short_period = self.params.get("short_period", 13)
        
        close = df["close"]
        
        # Mudança do preço
        price_change = close.diff()
        abs_price_change = price_change.abs()
        
        # Primeira suavização EMA
        smoothed_pc = price_change.ewm(span=long_period, adjust=False).mean()
        smoothed_abs_pc = abs_price_change.ewm(span=long_period, adjust=False).mean()
        
        # Segunda suavização EMA
        double_smoothed_pc = smoothed_pc.ewm(span=short_period, adjust=False).mean()
        double_smoothed_abs = smoothed_abs_pc.ewm(span=short_period, adjust=False).mean()
        
        # TSI = (Double Smoothed PC / Double Smoothed Abs PC) * 100
        values = (double_smoothed_pc / double_smoothed_abs) * 100
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(values)
        
        return IndicatorResult(
            indicator_type="TSI",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={"overbought": 25, "oversold": -25}
        )
    
    def _generate_signal(self, tsi: pd.Series) -> str:
        """Gera sinal baseado no TSI"""
        if len(tsi) < 2:
            return "neutral"
        
        last = tsi.iloc[-1]
        prev = tsi.iloc[-2]
        
        if prev < 0 and last > 0:
            return "buy"
        elif prev > 0 and last < 0:
            return "sell"
        elif last > 25:
            return "sell_weak"  # Overbought
        elif last < -25:
            return "buy_weak"   # Oversold
        elif last > 0:
            return "buy_weak"
        elif last < 0:
            return "sell_weak"
        
        return "neutral"
