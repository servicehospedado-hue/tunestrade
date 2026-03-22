"""
Ichimoku Cloud - Indicador completo de tendência
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class IchimokuIndicator(BaseIndicator):
    """Ichimoku Cloud - sistema completo de análise de tendência"""
    
    @property
    def name(self) -> str:
        return "ICHIMOKU"
    
    @property
    def description(self) -> str:
        return "Ichimoku Cloud - Sistema Completo de Tendência"
    
    @property
    def required_params(self) -> list:
        return ["tenkan", "kijun", "senkou_b"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o Ichimoku Cloud"""
        tenkan_period = self.params.get("tenkan", 9)
        kijun_period = self.params.get("kijun", 26)
        senkou_b_period = self.params.get("senkou_b", 52)
        
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # Tenkan-sen (Linha de Conversão) = (Highest High + Lowest Low) / 2 for 9 periods
        tenkan_sen = (high.rolling(window=tenkan_period).max() + low.rolling(window=tenkan_period).min()) / 2
        
        # Kijun-sen (Linha Base) = (Highest High + Lowest Low) / 2 for 26 periods
        kijun_sen = (high.rolling(window=kijun_period).max() + low.rolling(window=kijun_period).min()) / 2
        
        # Senkou Span A = (Tenkan-sen + Kijun-sen) / 2 (shifted 26 periods forward)
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
        
        # Senkou Span B = (Highest High + Lowest Low) / 2 for 52 periods (shifted 26 periods forward)
        senkou_span_b = ((high.rolling(window=senkou_b_period).max() + low.rolling(window=senkou_b_period).min()) / 2).shift(kijun_period)
        
        # Chikou Span = Close (shifted 26 periods backward)
        chikou_span = close.shift(-kijun_period)
        
        # Usar Tenkan-sen como valores principais para sinais
        values = tenkan_sen
        
        current_value = values.iloc[-1] if not values.empty else None
        previous_value = values.iloc[-2] if len(values) > 1 else None
        
        signal = self._generate_signal(close.iloc[-1], tenkan_sen.iloc[-1], kijun_sen.iloc[-1], senkou_span_a.iloc[-1], senkou_span_b.iloc[-1])
        
        return IndicatorResult(
            indicator_type="ICHIMOKU",
            values=values,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={
                "tenkan_sen": float(tenkan_sen.iloc[-1]) if not tenkan_sen.empty else None,
                "kijun_sen": float(kijun_sen.iloc[-1]) if not kijun_sen.empty else None,
                "senkou_span_a": float(senkou_span_a.iloc[-1]) if not senkou_span_a.empty else None,
                "senkou_span_b": float(senkou_span_b.iloc[-1]) if not senkou_span_b.empty else None
            }
        )
    
    def _generate_signal(self, close: float, tenkan: float, kijun: float, senkou_a: float, senkou_b: float) -> str:
        """Gera sinal baseado no Ichimoku"""
        if any(v is None for v in [close, tenkan, kijun, senkou_a, senkou_b]):
            return "neutral"
        
        # Verifica se está acima da nuvem
        above_cloud = close > max(senkou_a, senkou_b)
        below_cloud = close < min(senkou_a, senkou_b)
        
        if above_cloud and tenkan > kijun:
            return "buy"
        elif below_cloud and tenkan < kijun:
            return "sell"
        
        return "neutral"
