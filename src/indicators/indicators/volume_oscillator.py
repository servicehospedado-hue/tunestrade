"""
Volume Oscillator - Oscilador de Volume
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class VolumeOscillatorIndicator(BaseIndicator):
    """Volume Oscillator - compara médias móveis de volume de curto e longo prazo"""
    
    @property
    def name(self) -> str:
        return "VOLUME_OSCILLATOR"
    
    @property
    def description(self) -> str:
        return "Volume Oscillator - Análise de Volume"
    
    @property
    def required_params(self) -> list:
        return ["fast", "slow"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o Volume Oscillator"""
        fast = self.params.get("fast", 14)
        slow = self.params.get("slow", 28)
        
        # Usar volume se disponível
        if "volume" in df.columns:
            volume = df["volume"]
        else:
            volume = pd.Series(1, index=df.index)
        
        # Médias móveis do volume
        vma_fast = volume.rolling(window=fast).mean()
        vma_slow = volume.rolling(window=slow).mean()
        
        # Volume Oscillator = ((VMA Fast - VMA Slow) / VMA Slow) * 100
        values = ((vma_fast - vma_slow) / vma_slow) * 100
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(values)
        
        return IndicatorResult(
            indicator_type="VOLUME_OSCILLATOR",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None
        )
    
    def _generate_signal(self, vo: pd.Series) -> str:
        """Gera sinal baseado no Volume Oscillator"""
        if len(vo) < 2:
            return "neutral"
        
        last = vo.iloc[-1]
        prev = vo.iloc[-2]
        
        if prev < 0 and last > 0:
            return "buy"
        elif prev > 0 and last < 0:
            return "sell"
        elif last > 0:
            return "buy_weak"
        elif last < 0:
            return "sell_weak"
        
        return "neutral"
