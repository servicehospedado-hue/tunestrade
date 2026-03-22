"""
Fibonacci Levels - Níveis de Fibonacci
"""
import pandas as pd
from ..base import BaseIndicator, IndicatorResult


class FibonacciLevelsIndicator(BaseIndicator):
    """Fibonacci Levels - níveis de retração e extensão"""
    
    @property
    def name(self) -> str:
        return "FIBONACCI"
    
    @property
    def description(self) -> str:
        return "Fibonacci Retracement Levels"
    
    @property
    def required_params(self) -> list:
        return ["period"]
    
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula os níveis de Fibonacci baseado no range recente"""
        period = self.params.get("period", 20)
        
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # Encontra máximo e mínimo do período
        highest = high.rolling(window=period).max()
        lowest = low.rolling(window=period).min()
        
        # Range
        range_val = highest - lowest
        
        # Níveis de Fibonacci
        fib_236 = lowest + 0.236 * range_val
        fib_382 = lowest + 0.382 * range_val
        fib_500 = lowest + 0.500 * range_val
        fib_618 = lowest + 0.618 * range_val
        fib_786 = lowest + 0.786 * range_val
        
        # Valor atual = posição relativa do preço no range
        fib_position = (close - lowest) / range_val
        
        current_value = fib_position.iloc[-1] if not fib_position.empty else None
        previous_value = fib_position.iloc[-2] if len(fib_position) > 1 else None
        
        signal = self._generate_signal(close.iloc[-1], fib_236.iloc[-1], fib_618.iloc[-1], fib_786.iloc[-1])
        
        return IndicatorResult(
            indicator_type="FIBONACCI",
            values=fib_position,
            signal=signal,
            current_value=float(current_value) if current_value else None,
            previous_value=float(previous_value) if previous_value else None,
            metadata={
                "fib_236": float(fib_236.iloc[-1]) if not fib_236.empty else None,
                "fib_382": float(fib_382.iloc[-1]) if not fib_382.empty else None,
                "fib_500": float(fib_500.iloc[-1]) if not fib_500.empty else None,
                "fib_618": float(fib_618.iloc[-1]) if not fib_618.empty else None,
                "fib_786": float(fib_786.iloc[-1]) if not fib_786.empty else None
            }
        )
    
    def _generate_signal(self, close: float, fib_236: float, fib_618: float, fib_786: float) -> str:
        """Gera sinal baseado na posição nos níveis de Fibonacci"""
        if any(v is None for v in [close, fib_236, fib_618, fib_786]):
            return "neutral"
        
        # fib_236 (23.6%) está próximo ao topo -> resistência (sell zone)
        # fib_786 (78.6%) está próximo ao fundo -> suporte (buy zone)
        if close >= fib_236:
            return "sell"  # Próximo ao topo, zona de resistência
        elif close <= fib_786:
            return "buy"   # Próximo ao fundo, zona de suporte
        elif close <= fib_618:
            return "buy_weak"   # Entre 61.8% e 78.6%, zona de compra fraca
        elif close >= fib_382:
            return "sell_weak"  # Entre 38.2% e 23.6%, zona de venda fraca
        
        return "neutral"
