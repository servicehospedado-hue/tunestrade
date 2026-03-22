"""
OBV - On Balance Volume (Volume em Balanço)
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class OBVIndicator(BaseIndicator):
    """On Balance Volume - acumula volume baseado na direção do preço"""
    
    @property
    def name(self) -> str:
        return "OBV"
    
    @property
    def description(self) -> str:
        return "On Balance Volume"
    
    @property
    def required_params(self) -> list:
        return []
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o OBV"""
        close = df["close"]
        
        # Usar volume se disponível, senão usar 1
        if "volume" in df.columns:
            volume = df["volume"]
        else:
            volume = pd.Series(1, index=df.index)
        
        # Calcula mudança do preço
        price_change = close.diff()
        
        # OBV acumulado
        obv = pd.Series(0, index=df.index)
        for i in range(1, len(close)):
            if price_change.iloc[i] > 0:
                obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
            elif price_change.iloc[i] < 0:
                obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        
        values = obv
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(close, obv)
        
        return IndicatorResult(
            indicator_type="OBV",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None
        )
    
    def _generate_signal(self, close: pd.Series, obv: pd.Series) -> str:
        """Gera sinal baseado na divergência entre preço e OBV"""
        if len(close) < 3 or len(obv) < 3:
            return "neutral"
        
        # Verifica se OBV está subindo enquanto preço também sobe (confirmação)
        price_trend = close.iloc[-1] > close.iloc[-3]
        obv_trend = obv.iloc[-1] > obv.iloc[-3]
        
        if price_trend and obv_trend:
            return "buy"
        elif not price_trend and not obv_trend:
            return "sell"
        elif obv_trend:
            return "buy_weak"
        else:
            return "sell_weak"
