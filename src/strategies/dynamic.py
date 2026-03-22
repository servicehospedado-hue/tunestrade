"""
Estratégia Dinâmica — usa exatamente os indicadores escolhidos pelo usuário.
Instanciada via _get_user_custom_strategy com os indicadores e parâmetros
salvos na tabela user_strategies.
"""
import pandas as pd
import logging
from typing import Dict, Any, List
from datetime import datetime

from .base import BaseStrategy, StrategyResult
from ..indicators import IndicatorFactory

logger = logging.getLogger(__name__)


class DynamicStrategy(BaseStrategy):
    """
    Estratégia configurável em runtime com qualquer combinação de indicadores.

    Cada indicador contribui com um sinal (buy/sell/neutral) e peso igual.
    Direção final = maioria ponderada; confiança = ratio de concordância.
    """

    def __init__(
        self,
        indicators_config: List[Dict[str, Any]],
        timeframe: int = 5,
        min_confidence: float = 0.50,
        strategy_label: str = "Customizada",
    ):
        """
        Args:
            indicators_config: lista de dicts vindos de user_strategies.indicators
                Cada item: {"id": "sma", "type": "sma", "parameters": {...}, "sliderParams": [...]}
            timeframe: timeframe em segundos
            min_confidence: confiança mínima para emitir sinal
            strategy_label: nome exibido nos logs
        """
        super().__init__(timeframe, min_confidence)
        self._indicators_config = indicators_config
        self._strategy_label = strategy_label
        self._indicator_instances: Dict[str, Any] = {}
        self.setup_indicators()

    @property
    def name(self) -> str:
        return "Scalping5s"  # mantém compatibilidade com trade_executor

    @property
    def description(self) -> str:
        names = [c.get("name", c.get("type", "?")) for c in self._indicators_config]
        return f"Estratégia dinâmica: {', '.join(names)}"

    # Mapa de aliases: parâmetros que o frontend usa com nomes diferentes do indicador interno
    _PARAM_ALIASES: Dict[str, Dict[str, str]] = {
        "parabolic_sar": {"initial_af": "af"},
    }

    def setup_indicators(self) -> None:
        """Instancia cada indicador via IndicatorFactory usando os parâmetros do usuário."""
        self._indicator_instances = {}
        for cfg in self._indicators_config:
            ind_type = (cfg.get("type") or cfg.get("id") or "").lower()
            if not ind_type:
                continue

            # Parâmetros: prioriza sliderParams (valores ajustados pelo usuário)
            params = dict(cfg.get("parameters") or {})
            for sp in cfg.get("sliderParams") or []:
                name = sp.get("name")
                value = sp.get("value")
                if name is not None and value is not None:
                    params[name] = value

            # Aplicar aliases de parâmetros (ex: initial_af → af para parabolic_sar)
            aliases = self._PARAM_ALIASES.get(ind_type, {})
            for alias, canonical in aliases.items():
                if alias in params and canonical not in params:
                    params[canonical] = params.pop(alias)

            try:
                instance = IndicatorFactory.create(ind_type, params)
                # Chave única por tipo (ex: "sma", "ema", "macd")
                key = ind_type
                # Se já existe, adicionar sufixo numérico
                if key in self._indicator_instances:
                    i = 2
                    while f"{key}_{i}" in self._indicator_instances:
                        i += 1
                    key = f"{key}_{i}"
                self._indicator_instances[key] = instance
                logger.debug(f"[DynamicStrategy] Indicador instanciado: {key} | params={params}")
            except Exception as e:
                logger.warning(f"[DynamicStrategy] Falha ao instanciar '{ind_type}': {e}")

    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        if not self.validate_data(df, min_rows=20):
            return self._neutral_result(df)

        buy_score = 0.0
        sell_score = 0.0
        total = 0.0
        reasons: List[str] = []
        indicator_summary: Dict[str, Any] = {}

        for key, indicator in self._indicator_instances.items():
            try:
                result = indicator.calculate(df)
                signal = (result.signal or "neutral").lower()
                indicator_summary[key] = {
                    "value": result.current_value,
                    "signal": signal,
                }
                total += 1.0
                if signal in ("buy", "bullish"):
                    buy_score += 1.0
                    reasons.append(f"{key} bullish")
                elif signal in ("sell", "bearish"):
                    sell_score += 1.0
                    reasons.append(f"{key} bearish")
                # neutral não pontua
            except Exception as e:
                logger.debug(f"[DynamicStrategy] Erro em {key}: {e}")

        if total == 0:
            return self._neutral_result(df)

        buy_ratio = buy_score / total
        sell_ratio = sell_score / total

        if buy_ratio > sell_ratio and buy_ratio > 0.4:
            direction = "CALL"
            confidence = buy_ratio
            reason = " + ".join(reasons[:3]) or "Convergência bullish"
        elif sell_ratio > buy_ratio and sell_ratio > 0.4:
            direction = "PUT"
            confidence = sell_ratio
            reason = " + ".join(reasons[:3]) or "Convergência bearish"
        else:
            direction = "NEUTRAL"
            confidence = max(buy_ratio, sell_ratio)
            reason = "Sinais mistos"

        return StrategyResult(
            strategy_name=self.name,
            asset="",
            timeframe=self.timeframe,
            direction=direction,
            entry_price=float(df["close"].iloc[-1]) if not df.empty else None,
            confidence=confidence,
            indicators=indicator_summary,
            reason=reason,
            timestamp=float(df["timestamp"].iloc[-1]) if not df.empty else datetime.now().timestamp(),
            metadata={
                "dynamic": True,
                "label": self._strategy_label,
                "buy_score": buy_score,
                "sell_score": sell_score,
                "total_indicators": int(total),
            },
        )

    def _neutral_result(self, df: pd.DataFrame) -> StrategyResult:
        return StrategyResult(
            strategy_name=self.name,
            asset="",
            timeframe=self.timeframe,
            direction="NEUTRAL",
            entry_price=float(df["close"].iloc[-1]) if df is not None and not df.empty else None,
            confidence=0.0,
            indicators={},
            reason="Dados insuficientes",
            timestamp=datetime.now().timestamp(),
        )
