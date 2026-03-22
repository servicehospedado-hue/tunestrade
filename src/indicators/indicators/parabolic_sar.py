"""
Parabolic SAR - Stop And Reverse
"""
import pandas as pd
import numpy as np
from ..base import BaseIndicator, IndicatorResult


class ParabolicSARIndicator(BaseIndicator):
    """Parabolic SAR - identifica pontos de reversão de tendência"""
    
    @property
    def name(self) -> str:
        return "PARABOLIC_SAR"
    
    @property
    def description(self) -> str:
        return "Parabolic Stop And Reverse"
    
    @property
    def required_params(self) -> list:
        return ["af", "max_af"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o Parabolic SAR"""
        af = self.params.get("af", 0.02)
        max_af = self.params.get("max_af", 0.2)
        
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        
        n = len(close)
        psar = np.zeros(n)
        
        # Inicialização
        bull = True
        psar[0] = low[0]
        ep = high[0]
        af_current = af
        
        for i in range(1, n):
            if bull:
                psar[i] = psar[i-1] + af_current * (ep - psar[i-1])
                
                if low[i] < psar[i]:
                    bull = False
                    psar[i] = ep
                    ep = low[i]
                    af_current = af
                else:
                    if high[i] > ep:
                        ep = high[i]
                        af_current = min(af_current + af, max_af)
            else:
                psar[i] = psar[i-1] - af_current * (psar[i-1] - ep)
                
                if high[i] > psar[i]:
                    bull = True
                    psar[i] = ep
                    ep = high[i]
                    af_current = af
                else:
                    if low[i] < ep:
                        ep = low[i]
                        af_current = min(af_current + af, max_af)
        
        values = pd.Series(psar, index=df.index)
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(close[-1], current_value, bull)
        
        return IndicatorResult(
            indicator_type="PARABOLIC_SAR",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={"trend": "bull" if bull else "bear"}
        )
    
    def _generate_signal(self, price: float, psar: float, bull: bool) -> str:
        """Gera sinal baseado na posição do preço vs SAR"""
        if price is None or psar is None:
            return "neutral"
        
        if bull and price > psar:
            return "buy"
        elif not bull and price < psar:
            return "sell"
        
        return "neutral"
