"""
MACD - Moving Average Convergence Divergence
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class MACDIndicator(BaseIndicator):
    """MACD - Moving Average Convergence Divergence"""
    
    @property
    def name(self) -> str:
        return "MACD"
    
    @property
    def description(self) -> str:
        return "Moving Average Convergence Divergence"
    
    @property
    def required_params(self) -> list:
        return ["fast", "slow", "signal"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o MACD"""
        fast = self.params.get("fast", 12)
        slow = self.params.get("slow", 26)
        signal_period = self.params.get("signal", 9)
        
        close = df["close"]
        
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        
        current_value = histogram.iloc[-1] if not histogram.empty else None
        previous_value = histogram.iloc[-2] if len(histogram) > 1 else None
        
        signal = self._generate_signal(histogram)
        
        return IndicatorResult(
            indicator_type="MACD",
            values=histogram,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={
                "macd_line": float(macd_line.iloc[-1]) if not macd_line.empty else None,
                "signal_line": float(signal_line.iloc[-1]) if not signal_line.empty else None
            }
        )
    
    def _generate_signal(self, histogram: pd.Series) -> str:
        """Gera sinal baseado no histograma"""
        if len(histogram) < 2:
            return "neutral"
        
        last_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]
        
        if last_hist > 0 and prev_hist <= 0:
            return "buy"
        elif last_hist < 0 and prev_hist >= 0:
            return "sell"
        
        return "neutral"
