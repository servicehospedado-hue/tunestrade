"""
Pivot Points - Pontos de Pivô
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class PivotPointsIndicator(BaseIndicator):
    """Pivot Points - níveis de suporte e resistência clássicos"""
    
    @property
    def name(self) -> str:
        return "PIVOT_POINTS"
    
    @property
    def description(self) -> str:
        return "Pivot Points Classic - Suporte e Resistência"
    
    @property
    def required_params(self) -> list:
        return []
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula os Pivot Points clássicos"""
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # Pivot Point (PP) = (High + Low + Close) / 3
        pivot = (high.shift(1) + low.shift(1) + close.shift(1)) / 3
        
        # Support 1 (S1) = (2 * PP) - High
        s1 = (2 * pivot) - high.shift(1)
        # Support 2 (S2) = PP - (High - Low)
        s2 = pivot - (high.shift(1) - low.shift(1))
        # Support 3 (S3) = Low - 2 * (High - PP)
        s3 = low.shift(1) - 2 * (high.shift(1) - pivot)
        
        # Resistance 1 (R1) = (2 * PP) - Low
        r1 = (2 * pivot) - low.shift(1)
        # Resistance 2 (R2) = PP + (High - Low)
        r2 = pivot + (high.shift(1) - low.shift(1))
        # Resistance 3 (R3) = High + 2 * (PP - Low)
        r3 = high.shift(1) + 2 * (pivot - low.shift(1))
        
        # Posição relativa
        range_val = r3 - s3
        pivot_position = (close - s3) / range_val
        
        current_value = pivot_position.iloc[-1] if not pivot_position.empty else None
        previous_value = pivot_position.iloc[-2] if len(pivot_position) > 1 else None
        
        signal = self._generate_signal(close.iloc[-1], r1.iloc[-1], s1.iloc[-1], pivot.iloc[-1])
        
        return IndicatorResult(
            indicator_type="PIVOT_POINTS",
            values=pivot_position,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={
                "pivot": float(pivot.iloc[-1]) if not pivot.empty else None,
                "r1": float(r1.iloc[-1]) if not r1.empty else None,
                "s1": float(s1.iloc[-1]) if not s1.empty else None,
                "r2": float(r2.iloc[-1]) if not r2.empty else None,
                "s2": float(s2.iloc[-1]) if not s2.empty else None
            }
        )
    
    def _generate_signal(self, close: float, r1: float, s1: float, pivot: float) -> str:
        """Gera sinal baseado na posição relativa aos pivôs"""
        if any(v is None for v in [close, r1, s1, pivot]):
            return "neutral"
        
        if close > r1:
            return "buy"  # Breakout para cima
        elif close < s1:
            return "sell"  # Breakout para baixo
        elif close > pivot:
            return "buy_weak"
        elif close < pivot:
            return "sell_weak"
        
        return "neutral"
