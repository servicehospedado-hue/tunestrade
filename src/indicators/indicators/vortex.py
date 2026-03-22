"""
Vortex Indicator - Identifica início de tendências
"""
import pandas as pd
import numpy as np
from ..base import BaseIndicator, IndicatorResult


class VortexIndicator(BaseIndicator):
    """Vortex Indicator - mede movimentação direcional positiva e negativa"""
    
    @property
    def name(self) -> str:
        return "VORTEX"
    
    @property
    def description(self) -> str:
        return "Vortex Indicator - Movimentação Direcional"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o Vortex Indicator"""
        period = self.params.get("period", 14)
        
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # VM+ = |High[t] - Low[t-1]|
        vm_plus = abs(high - low.shift(1))
        
        # VM- = |Low[t] - High[t-1]|
        vm_minus = abs(low - high.shift(1))
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Sum over period
        sum_tr = tr.rolling(window=period).sum()
        sum_vm_plus = vm_plus.rolling(window=period).sum()
        sum_vm_minus = vm_minus.rolling(window=period).sum()
        
        # VI+ = Sum(VM+) / Sum(TR)
        vi_plus = sum_vm_plus / sum_tr
        # VI- = Sum(VM-) / Sum(TR)
        vi_minus = sum_vm_minus / sum_tr
        
        # Usar VI+ como valores principais
        values = vi_plus
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(vi_plus, vi_minus)
        
        return IndicatorResult(
            indicator_type="VORTEX",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={
                "vi_plus": float(vi_plus.iloc[-1]) if not vi_plus.empty else None,
                "vi_minus": float(vi_minus.iloc[-1]) if not vi_minus.empty else None
            }
        )
    
    def _generate_signal(self, vi_plus: pd.Series, vi_minus: pd.Series) -> str:
        """Gera sinal baseado no cruzamento de VI+ e VI-"""
        if len(vi_plus) < 2 or len(vi_minus) < 2:
            return "neutral"
        
        last_plus = vi_plus.iloc[-1]
        last_minus = vi_minus.iloc[-1]
        prev_plus = vi_plus.iloc[-2]
        prev_minus = vi_minus.iloc[-2]
        
        if prev_plus < prev_minus and last_plus > last_minus:
            return "buy"
        elif prev_plus > prev_minus and last_plus < last_minus:
            return "sell"
        elif last_plus > last_minus:
            return "buy_weak"
        elif last_plus < last_minus:
            return "sell_weak"
        
        return "neutral"
