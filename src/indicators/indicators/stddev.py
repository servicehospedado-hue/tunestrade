"""
StdDev - Standard Deviation (Desvio Padrão)
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class StdDevIndicator(BaseIndicator):
    """Standard Deviation - mede volatilidade"""
    
    @property
    def name(self) -> str:
        return "STDDEV"
    
    @property
    def description(self) -> str:
        return "Standard Deviation - Medida de Volatilidade"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o Standard Deviation"""
        period = self.params.get("period", 20)
        close = df["close"]
        
        # Standard Deviation do preço de fechamento
        values = close.rolling(window=period).std()
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(close, values, period)
        
        return IndicatorResult(
            indicator_type="STDDEV",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={"volatility": float(current_value) if current_value else None}
        )
    
    def _generate_signal(self, close: pd.Series, stddev: pd.Series, period: int) -> str:
        """Gera sinal baseado na volatilidade (Bollinger Bands concept)"""
        if len(close) < period or len(stddev) < 2:
            return "neutral"
        
        # SMA
        sma = close.rolling(window=period).mean()
        
        last_close = close.iloc[-1]
        last_sma = sma.iloc[-1]
        last_std = stddev.iloc[-1]
        
        if any(v is None for v in [last_close, last_sma, last_std]):
            return "neutral"
        
        # Bandas de Bollinger simplificadas
        upper = last_sma + (2 * last_std)
        lower = last_sma - (2 * last_std)
        
        if last_close > upper:
            return "sell"
        elif last_close < lower:
            return "buy"
        
        return "neutral"
