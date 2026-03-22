"""
Estratégia de Scalping para Timeframe de 5 segundos

Análise rápida de preços usando múltiplos indicadores para detectar
oportunidades de entrada em operações de curto prazo.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from .base import BaseStrategy, StrategyResult
from ..indicators import (
    RSIIndicator, EMAIndicator, MomentumIndicator, 
    BBIndicator, StochasticIndicator, MACDIndicator
)

logger = logging.getLogger(__name__)


class ScalpingStrategy(BaseStrategy):
    """
    Estratégia de Scalping otimizada para timeframe de 5 segundos.
    
    Usa convergência de múltiplos indicadores para gerar sinais:
    - RSI (7): Detecta sobrecompra/sobrevenda
    - EMA Cross (3/7): Cruzamento de médias rápidas
    - Momentum (3): Velocidade de mudança
    - Stochastic (5,3): Oscilador para reversões
    - BB (10, 1.5): Bandas para extremos de preço
    - MACD (rápido): Tendência de curto prazo
    """
    
    def __init__(
        self,
        timeframe: int = 5,
        min_confidence: float = 0.7,
        cooldown_seconds: float = 5.0,
        rsi_period: int = 7,
        ema_fast: int = 3,
        ema_slow: int = 7,
        momentum_period: int = 3,
        stoch_k: int = 5,
        stoch_d: int = 3,
        bb_period: int = 10,
        bb_std: float = 1.5,
        macd_fast: int = 5,
        macd_slow: int = 13,
        macd_signal: int = 4
    ):
        super().__init__(timeframe, min_confidence)
        self._cooldown_seconds = cooldown_seconds
        
        # Parâmetros dos indicadores
        self.rsi_period = rsi_period
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.momentum_period = momentum_period
        self.stoch_k = stoch_k
        self.stoch_d = stoch_d
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        
        # Inicializar indicadores
        self.setup_indicators()
        
        # Pesos para cálculo de confiança
        self.indicator_weights = {
            'RSI': 1.0,
            'EMA_Cross': 1.2,
            'Momentum': 0.9,
            'Stochastic': 0.8,
            'BB': 1.0,
            'MACD': 1.1
        }
        
    @property
    def name(self) -> str:
        return "Scalping5s"
    
    @property
    def description(self) -> str:
        return "Estratégia de Scalping para timeframe de 5 segundos"
    
    def setup_indicators(self) -> None:
        """Configura indicadores usados pela estratégia"""
        self._indicators = {
            'rsi': RSIIndicator({'period': self.rsi_period}),
            'ema_fast': EMAIndicator({'period': self.ema_fast}),
            'ema_slow': EMAIndicator({'period': self.ema_slow}),
            'momentum': MomentumIndicator({'period': self.momentum_period}),
            'stochastic': StochasticIndicator({
                'k_period': self.stoch_k, 
                'd_period': self.stoch_d
            }),
            'bb': BBIndicator({
                'period': self.bb_period, 
                'std_dev': self.bb_std
            }),
            'macd': MACDIndicator({
                'fast': self.macd_fast,
                'slow': self.macd_slow,
                'signal': self.macd_signal
            })
        }
    
    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        """
        Analisa dados e retorna resultado da estratégia.
        
        Args:
            df: DataFrame com colunas 'timestamp' e 'close'
            
        Returns:
            StrategyResult com direção, confiança e indicadores
        """
        # Validar dados mínimos
        min_rows = max(self.rsi_period, self.ema_slow, self.bb_period, self.macd_slow) + 5
        if not self.validate_data(df, min_rows):
            return self._neutral_result(df)
        
        # Calcular todos os indicadores
        indicator_results = self._calculate_all_indicators(df)
        
        # Calcular métricas de preço derivadas
        price_metrics = self.calculate_price_metrics(df)
        
        # Avaliar sinais individuais
        signals = self._evaluate_signals(indicator_results, price_metrics)
        
        # Calcular confiança e direção final
        direction, confidence, reason = self._calculate_final_signal(signals, indicator_results)
        
        # Construir resultado
        result = StrategyResult(
            strategy_name=self.name,
            asset="",  # Será preenchido pelo chamador
            timeframe=self.timeframe,
            direction=direction,
            entry_price=float(df['close'].iloc[-1]) if not df.empty else None,
            confidence=confidence,
            indicators=self._build_indicator_summary(indicator_results, signals),
            reason=reason,
            timestamp=float(df['timestamp'].iloc[-1]) if not df.empty else datetime.now().timestamp(),
            metadata={
                'price_metrics': price_metrics,
                'total_indicators': len(signals),
                'buy_count': sum(1 for s in signals.values() if s in ['buy', 'buy_weak']),
                'sell_count': sum(1 for s in signals.values() if s in ['sell', 'sell_weak'])
            }
        )
        
        return result
    
    def _calculate_all_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calcula todos os indicadores"""
        results = {}
        
        try:
            results['rsi'] = self._indicators['rsi'].calculate(df)
        except Exception as e:
            logger.debug(f"RSI calculation error: {e}")
            
        try:
            results['ema_fast'] = self._indicators['ema_fast'].calculate(df)
        except Exception as e:
            logger.debug(f"EMA fast calculation error: {e}")
            
        try:
            results['ema_slow'] = self._indicators['ema_slow'].calculate(df)
        except Exception as e:
            logger.debug(f"EMA slow calculation error: {e}")
            
        try:
            results['momentum'] = self._indicators['momentum'].calculate(df)
        except Exception as e:
            logger.debug(f"Momentum calculation error: {e}")
            
        try:
            results['stochastic'] = self._indicators['stochastic'].calculate(df)
        except Exception as e:
            logger.debug(f"Stochastic calculation error: {e}")
            
        try:
            results['bb'] = self._indicators['bb'].calculate(df)
        except Exception as e:
            logger.debug(f"BB calculation error: {e}")
            
        try:
            results['macd'] = self._indicators['macd'].calculate(df)
        except Exception as e:
            logger.debug(f"MACD calculation error: {e}")
        
        return results
    
    def _evaluate_signals(
        self, 
        indicator_results: Dict[str, Any], 
        price_metrics: Dict[str, Any]
    ) -> Dict[str, str]:
        """Avalia sinais individuais de cada indicador"""
        signals = {}
        
        # RSI
        if 'rsi' in indicator_results:
            rsi_result = indicator_results['rsi']
            rsi_val = rsi_result.current_value
            if rsi_val is not None:
                if rsi_val < 30:
                    signals['RSI'] = 'buy'
                elif rsi_val > 70:
                    signals['RSI'] = 'sell'
                elif rsi_val < 40:
                    signals['RSI'] = 'buy_weak'
                elif rsi_val > 60:
                    signals['RSI'] = 'sell_weak'
                else:
                    signals['RSI'] = 'neutral'
        
        # EMA Cross
        if 'ema_fast' in indicator_results and 'ema_slow' in indicator_results:
            ema_f = indicator_results['ema_fast']
            ema_s = indicator_results['ema_slow']
            
            if ema_f.current_value and ema_s.current_value:
                prev_diff = (ema_f.previous_value or 0) - (ema_s.previous_value or 0)
                curr_diff = ema_f.current_value - ema_s.current_value
                
                if prev_diff <= 0 and curr_diff > 0:
                    signals['EMA_Cross'] = 'buy'  # Cruzamento bullish
                elif prev_diff >= 0 and curr_diff < 0:
                    signals['EMA_Cross'] = 'sell'  # Cruzamento bearish
                elif curr_diff > 0:
                    signals['EMA_Cross'] = 'buy_weak'
                elif curr_diff < 0:
                    signals['EMA_Cross'] = 'sell_weak'
                else:
                    signals['EMA_Cross'] = 'neutral'
        
        # Momentum
        if 'momentum' in indicator_results:
            mom_result = indicator_results['momentum']
            signals['Momentum'] = mom_result.signal
        
        # Stochastic
        if 'stochastic' in indicator_results:
            stoch_result = indicator_results['stochastic']
            stoch_val = stoch_result.current_value
            if stoch_val is not None:
                if stoch_val < 20:
                    signals['Stochastic'] = 'buy'
                elif stoch_val > 80:
                    signals['Stochastic'] = 'sell'
                elif stoch_val < 30:
                    signals['Stochastic'] = 'buy_weak'
                elif stoch_val > 70:
                    signals['Stochastic'] = 'sell_weak'
                else:
                    signals['Stochastic'] = 'neutral'
        
        # Bollinger Bands
        if 'bb' in indicator_results:
            bb_result = indicator_results['bb']
            bb_pos = bb_result.current_value  # %B position
            if bb_pos is not None:
                if bb_pos < 0:  # Abaixo da banda inferior
                    signals['BB'] = 'buy'
                elif bb_pos > 1:  # Acima da banda superior
                    signals['BB'] = 'sell'
                elif bb_pos < 0.2:
                    signals['BB'] = 'buy_weak'
                elif bb_pos > 0.8:
                    signals['BB'] = 'sell_weak'
                else:
                    signals['BB'] = 'neutral'
        
        # MACD
        if 'macd' in indicator_results:
            macd_result = indicator_results['macd']
            signals['MACD'] = macd_result.signal
        
        return signals
    
    def _calculate_final_signal(
        self, 
        signals: Dict[str, str],
        indicator_results: Dict[str, Any]
    ) -> tuple:
        """
        Calcula sinal final baseado em convergência.
        
        Returns:
            tuple: (direction, confidence, reason)
        """
        buy_score = 0.0
        sell_score = 0.0
        total_weight = 0.0
        reasons = []
        
        for indicator, signal in signals.items():
            weight = self.indicator_weights.get(indicator, 1.0)
            total_weight += weight
            
            if signal in ['buy', 'buy_weak']:
                score = weight if signal == 'buy' else weight * 0.5
                buy_score += score
                if signal == 'buy':
                    reasons.append(f"{indicator} bullish")
            elif signal in ['sell', 'sell_weak']:
                score = weight if signal == 'sell' else weight * 0.5
                sell_score += score
                if signal == 'sell':
                    reasons.append(f"{indicator} bearish")
        
        if total_weight == 0:
            return "NEUTRAL", 0.0, "Dados insuficientes"
        
        buy_ratio = buy_score / total_weight
        sell_ratio = sell_score / total_weight
        
        # Determinar direção e confiança
        if buy_ratio > 0.5:
            direction = "CALL"
            confidence = min(buy_ratio, 1.0)
            reason = " + ".join(reasons[:3]) if reasons else "Convergência bullish"
        elif sell_ratio > 0.5:
            direction = "PUT"
            confidence = min(sell_ratio, 1.0)
            reason = " + ".join(reasons[:3]) if reasons else "Convergência bearish"
        else:
            direction = "NEUTRAL"
            confidence = max(buy_ratio, sell_ratio)
            reason = "Sinais mistos"
        
        return direction, confidence, reason
    
    def _build_indicator_summary(
        self, 
        indicator_results: Dict[str, Any],
        signals: Dict[str, str]
    ) -> Dict[str, Any]:
        """Constrói resumo dos indicadores para o sinal"""
        summary = {}
        
        if 'rsi' in indicator_results:
            r = indicator_results['rsi']
            summary['RSI'] = {
                'value': r.current_value,
                'signal': signals.get('RSI', 'neutral'),
                'overbought': 70,
                'oversold': 30
            }
        
        if 'ema_fast' in indicator_results and 'ema_slow' in indicator_results:
            ef = indicator_results['ema_fast']
            es = indicator_results['ema_slow']
            summary['EMA_Cross'] = {
                'fast': ef.current_value,
                'slow': es.current_value,
                'signal': signals.get('EMA_Cross', 'neutral')
            }
        
        if 'momentum' in indicator_results:
            m = indicator_results['momentum']
            summary['Momentum'] = {
                'value': m.current_value,
                'signal': signals.get('Momentum', 'neutral')
            }
        
        if 'stochastic' in indicator_results:
            s = indicator_results['stochastic']
            summary['Stochastic'] = {
                'value': s.current_value,
                'signal': signals.get('Stochastic', 'neutral'),
                'k': s.metadata.get('k_line') if s.metadata else None,
                'd': s.metadata.get('d_line') if s.metadata else None
            }
        
        if 'bb' in indicator_results:
            b = indicator_results['bb']
            summary['BB'] = {
                'position': b.current_value,
                'signal': signals.get('BB', 'neutral'),
                'upper': b.metadata.get('upper') if b.metadata else None,
                'lower': b.metadata.get('lower') if b.metadata else None
            }
        
        if 'macd' in indicator_results:
            m = indicator_results['macd']
            summary['MACD'] = {
                'histogram': m.current_value,
                'signal': signals.get('MACD', 'neutral'),
                'macd_line': m.metadata.get('macd_line') if m.metadata else None
            }
        
        return summary
    
    def _neutral_result(self, df: pd.DataFrame) -> StrategyResult:
        """Retorna resultado neutro quando dados insuficientes"""
        return StrategyResult(
            strategy_name=self.name,
            asset="",
            timeframe=self.timeframe,
            direction="NEUTRAL",
            entry_price=float(df['close'].iloc[-1]) if df is not None and not df.empty else None,
            confidence=0.0,
            indicators={},
            reason="Dados insuficientes para análise",
            timestamp=datetime.now().timestamp()
        )
