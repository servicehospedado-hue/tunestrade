"""
Estratégia Trend M1 para Timeframe de 1 Minuto

Combina indicadores de tendência, momentum e volume para detectar
entradas de alta probabilidade em operações de 1 minuto.

Indicadores utilizados:
- RSI (14): Sobrecompra/sobrevenda
- EMA Cross (9/21): Tendência de curto prazo
- MACD (12/26/9): Confirmação de tendência
- ADX (14): Força da tendência
- Stochastic (14/3): Reversões em extremos
- BB (20/2): Posição relativa ao preço
- CCI (14): Commodity Channel Index para extremos
- Williams %R (14): Oscilador de momentum
- ATR (14): Volatilidade para filtro de ruído
- Parabolic SAR: Direção da tendência
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from .base import BaseStrategy, StrategyResult
from ..indicators import (
    RSIIndicator, EMAIndicator, MACDIndicator, ADXIndicator,
    StochasticIndicator, BBIndicator, CCIIndicator,
    WilliamsRIndicator, ATRIndicator, ParabolicSARIndicator,
)

logger = logging.getLogger(__name__)


class TrendM1Strategy(BaseStrategy):
    """
    Estratégia de tendência otimizada para timeframe de 1 minuto.

    Lógica de entrada:
    - Tendência confirmada por EMA Cross + MACD + ADX
    - Momentum validado por RSI + Stochastic + Williams %R + CCI
    - Posição de preço verificada por BB + Parabolic SAR
    - Filtro de volatilidade via ATR (evita entradas em mercado flat)

    Pesos por grupo:
    - Tendência (EMA, MACD, ADX, PSAR): peso 1.3 cada
    - Momentum (RSI, Stoch, Williams, CCI): peso 1.0 cada
    - Volatilidade/Posição (BB, ATR): peso 0.8 cada
    """

    def __init__(
        self,
        timeframe: int = 60,
        min_confidence: float = 0.65,
        cooldown_seconds: float = 60.0,
        rsi_period: int = 7,
        ema_fast: int = 5,
        ema_slow: int = 10,
        macd_fast: int = 5,
        macd_slow: int = 10,
        macd_signal: int = 4,
        adx_period: int = 7,
        stoch_k: int = 7,
        stoch_d: int = 3,
        bb_period: int = 10,
        bb_std: float = 2.0,
        cci_period: int = 7,
        williams_period: int = 7,
        atr_period: int = 7,
    ):
        super().__init__(timeframe, min_confidence)
        self._cooldown_seconds = cooldown_seconds

        self.rsi_period = rsi_period
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.adx_period = adx_period
        self.stoch_k = stoch_k
        self.stoch_d = stoch_d
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.cci_period = cci_period
        self.williams_period = williams_period
        self.atr_period = atr_period

        self.setup_indicators()

        self.indicator_weights = {
            'EMA_Cross':   1.3,
            'MACD':        1.3,
            'ADX':         1.2,
            'PSAR':        1.2,
            'RSI':         1.0,
            'Stochastic':  1.0,
            'Williams':    1.0,
            'CCI':         1.0,
            'BB':          0.8,
            'ATR':         0.6,
        }

    @property
    def name(self) -> str:
        return "TrendM1"

    @property
    def description(self) -> str:
        return "Estratégia de tendência para timeframe de 1 minuto"

    def setup_indicators(self) -> None:
        self._indicators = {
            'rsi':        RSIIndicator({'period': self.rsi_period}),
            'ema_fast':   EMAIndicator({'period': self.ema_fast}),
            'ema_slow':   EMAIndicator({'period': self.ema_slow}),
            'macd':       MACDIndicator({'fast': self.macd_fast, 'slow': self.macd_slow, 'signal': self.macd_signal}),
            'adx':        ADXIndicator({'period': self.adx_period}),
            'stochastic': StochasticIndicator({'k_period': self.stoch_k, 'd_period': self.stoch_d}),
            'bb':         BBIndicator({'period': self.bb_period, 'std_dev': self.bb_std}),
            'cci':        CCIIndicator({'period': self.cci_period}),
            'williams':   WilliamsRIndicator({'period': self.williams_period}),
            'atr':        ATRIndicator({'period': self.atr_period}),
            'psar':       ParabolicSARIndicator({'af': 0.02, 'max_af': 0.2}),
        }

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        min_rows = max(self.macd_slow, self.bb_period, self.adx_period, self.ema_slow) + 3
        if not self.validate_data(df, min_rows):
            return self._neutral_result(df)

        ind = self._calculate_all_indicators(df)
        price_metrics = self.calculate_price_metrics(df)
        signals = self._evaluate_signals(ind, df)
        direction, confidence, reason = self._calculate_final_signal(signals, ind)

        return StrategyResult(
            strategy_name=self.name,
            asset="",
            timeframe=self.timeframe,
            direction=direction,
            entry_price=float(df['close'].iloc[-1]) if not df.empty else None,
            confidence=confidence,
            indicators=self._build_indicator_summary(ind, signals),
            reason=reason,
            timestamp=float(df['timestamp'].iloc[-1]) if not df.empty else datetime.now().timestamp(),
            metadata={
                'price_metrics': price_metrics,
                'buy_count': sum(1 for s in signals.values() if s in ['buy', 'buy_weak']),
                'sell_count': sum(1 for s in signals.values() if s in ['sell', 'sell_weak']),
            }
        )

    def _calculate_all_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        results = {}
        for key, indicator in self._indicators.items():
            try:
                results[key] = indicator.calculate(df)
            except Exception as e:
                logger.debug(f"[TrendM1] {key} error: {e}")
        return results

    def _evaluate_signals(self, ind: Dict[str, Any], df: pd.DataFrame) -> Dict[str, str]:
        signals = {}
        close = df['close'].iloc[-1]

        # RSI
        if 'rsi' in ind and ind['rsi'].current_value is not None:
            v = ind['rsi'].current_value
            if v < 30:       signals['RSI'] = 'buy'
            elif v > 70:     signals['RSI'] = 'sell'
            elif v < 45:     signals['RSI'] = 'buy_weak'
            elif v > 55:     signals['RSI'] = 'sell_weak'
            else:            signals['RSI'] = 'neutral'

        # EMA Cross
        if 'ema_fast' in ind and 'ema_slow' in ind:
            ef = ind['ema_fast']
            es = ind['ema_slow']
            if ef.current_value and es.current_value:
                prev_diff = (ef.previous_value or 0) - (es.previous_value or 0)
                curr_diff = ef.current_value - es.current_value
                if prev_diff <= 0 and curr_diff > 0:   signals['EMA_Cross'] = 'buy'
                elif prev_diff >= 0 and curr_diff < 0: signals['EMA_Cross'] = 'sell'
                elif curr_diff > 0:                    signals['EMA_Cross'] = 'buy_weak'
                elif curr_diff < 0:                    signals['EMA_Cross'] = 'sell_weak'
                else:                                  signals['EMA_Cross'] = 'neutral'

        # MACD
        if 'macd' in ind:
            signals['MACD'] = ind['macd'].signal

        # ADX — força da tendência + direção via DI
        if 'adx' in ind and ind['adx'].current_value is not None:
            adx_val = ind['adx'].current_value
            meta = ind['adx'].metadata or {}
            di_plus = meta.get('di_plus', 0) or 0
            di_minus = meta.get('di_minus', 0) or 0
            if adx_val > 25:
                if di_plus > di_minus:   signals['ADX'] = 'buy'
                elif di_minus > di_plus: signals['ADX'] = 'sell'
                else:                    signals['ADX'] = 'neutral'
            elif adx_val > 15:
                if di_plus > di_minus:   signals['ADX'] = 'buy_weak'
                elif di_minus > di_plus: signals['ADX'] = 'sell_weak'
                else:                    signals['ADX'] = 'neutral'
            else:
                signals['ADX'] = 'neutral'  # Tendência fraca

        # Stochastic
        if 'stochastic' in ind and ind['stochastic'].current_value is not None:
            v = ind['stochastic'].current_value
            if v < 20:       signals['Stochastic'] = 'buy'
            elif v > 80:     signals['Stochastic'] = 'sell'
            elif v < 35:     signals['Stochastic'] = 'buy_weak'
            elif v > 65:     signals['Stochastic'] = 'sell_weak'
            else:            signals['Stochastic'] = 'neutral'

        # Bollinger Bands (%B)
        if 'bb' in ind and ind['bb'].current_value is not None:
            v = ind['bb'].current_value
            if v < 0:        signals['BB'] = 'buy'
            elif v > 1:      signals['BB'] = 'sell'
            elif v < 0.2:    signals['BB'] = 'buy_weak'
            elif v > 0.8:    signals['BB'] = 'sell_weak'
            else:            signals['BB'] = 'neutral'

        # CCI
        if 'cci' in ind and ind['cci'].current_value is not None:
            v = ind['cci'].current_value
            if v < -100:     signals['CCI'] = 'buy'
            elif v > 100:    signals['CCI'] = 'sell'
            elif v < -50:    signals['CCI'] = 'buy_weak'
            elif v > 50:     signals['CCI'] = 'sell_weak'
            else:            signals['CCI'] = 'neutral'

        # Williams %R
        if 'williams' in ind and ind['williams'].current_value is not None:
            v = ind['williams'].current_value
            if v < -80:      signals['Williams'] = 'buy'
            elif v > -20:    signals['Williams'] = 'sell'
            elif v < -65:    signals['Williams'] = 'buy_weak'
            elif v > -35:    signals['Williams'] = 'sell_weak'
            else:            signals['Williams'] = 'neutral'

        # Parabolic SAR — preço acima = bullish, abaixo = bearish
        if 'psar' in ind and ind['psar'].current_value is not None:
            sar = ind['psar'].current_value
            if close > sar:  signals['PSAR'] = 'buy'
            else:            signals['PSAR'] = 'sell'

        # ATR — filtro de volatilidade (não emite sinal direcional, apenas armazena valor)
        # ATR não vota na direção — só é usado para filtrar mercado flat externamente
        # Não adicionar 'ATR' em signals para não poluir o score direcional

        return signals

    def _calculate_final_signal(self, signals: Dict[str, str], ind: Dict[str, Any]):
        buy_score = 0.0
        sell_score = 0.0
        total_weight = 0.0
        reasons = []

        for name, signal in signals.items():
            weight = self.indicator_weights.get(name, 1.0)
            total_weight += weight
            if signal in ['buy', 'buy_weak']:
                score = weight if signal == 'buy' else weight * 0.5
                buy_score += score
                if signal == 'buy':
                    reasons.append(f"{name} bullish")
            elif signal in ['sell', 'sell_weak']:
                score = weight if signal == 'sell' else weight * 0.5
                sell_score += score
                if signal == 'sell':
                    reasons.append(f"{name} bearish")

        if total_weight == 0:
            return "NEUTRAL", 0.0, "Dados insuficientes"

        buy_ratio = buy_score / total_weight
        sell_ratio = sell_score / total_weight
        margin = buy_ratio - sell_ratio

        logger.info(
            f"[TrendM1] buy={buy_score:.2f}/{buy_ratio:.2f} sell={sell_score:.2f}/{sell_ratio:.2f} "
            f"margin={margin:.2f} | {signals}"
        )

        # Emite sinal se uma direção domina com margem clara (>= 10% de diferença)
        # e razão absoluta supera 35% do peso total
        if buy_ratio >= 0.35 and margin >= 0.10:
            return "CALL", min(buy_ratio, 1.0), " + ".join(reasons[:4]) or "Convergência bullish"
        elif sell_ratio >= 0.35 and (-margin) >= 0.10:
            return "PUT", min(sell_ratio, 1.0), " + ".join(reasons[:4]) or "Convergência bearish"
        else:
            return "NEUTRAL", max(buy_ratio, sell_ratio), "Sinais mistos"

    def _build_indicator_summary(self, ind: Dict[str, Any], signals: Dict[str, str]) -> Dict[str, Any]:
        summary = {}

        if 'rsi' in ind:
            summary['RSI'] = {'value': ind['rsi'].current_value, 'signal': signals.get('RSI', 'neutral')}

        if 'ema_fast' in ind and 'ema_slow' in ind:
            summary['EMA_Cross'] = {
                'fast': ind['ema_fast'].current_value,
                'slow': ind['ema_slow'].current_value,
                'signal': signals.get('EMA_Cross', 'neutral')
            }

        if 'macd' in ind:
            m = ind['macd']
            summary['MACD'] = {
                'histogram': m.current_value,
                'macd_line': (m.metadata or {}).get('macd_line'),
                'signal': signals.get('MACD', 'neutral')
            }

        if 'adx' in ind:
            a = ind['adx']
            summary['ADX'] = {
                'value': a.current_value,
                'period': self.adx_period,
                'di_plus': (a.metadata or {}).get('di_plus'),
                'di_minus': (a.metadata or {}).get('di_minus'),
                'signal': signals.get('ADX', 'neutral')
            }

        if 'stochastic' in ind:
            s = ind['stochastic']
            summary['Stochastic'] = {
                'value': s.current_value,
                'k': (s.metadata or {}).get('k_line'),
                'd': (s.metadata or {}).get('d_line'),
                'signal': signals.get('Stochastic', 'neutral')
            }

        if 'bb' in ind:
            b = ind['bb']
            summary['BB'] = {
                'position': b.current_value,
                'upper': (b.metadata or {}).get('upper'),
                'lower': (b.metadata or {}).get('lower'),
                'signal': signals.get('BB', 'neutral')
            }

        if 'cci' in ind:
            summary['CCI'] = {
                'value': ind['cci'].current_value,
                'period': self.cci_period,
                'signal': signals.get('CCI', 'neutral')
            }

        if 'williams' in ind:
            summary['Williams'] = {
                'value': ind['williams'].current_value,
                'period': self.williams_period,
                'signal': signals.get('Williams', 'neutral')
            }

        if 'psar' in ind:
            p = ind['psar']
            summary['PSAR'] = {
                'value': p.current_value,
                'af': 0.02,
                'max_af': 0.2,
                'trend': (p.metadata or {}).get('trend'),
                'signal': signals.get('PSAR', 'neutral')
            }

        if 'atr' in ind:
            summary['ATR'] = {
                'value': ind['atr'].current_value,
                'period': self.atr_period,
                'signal': signals.get('ATR', 'neutral')
            }

        return summary

    def _neutral_result(self, df: pd.DataFrame) -> StrategyResult:
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
