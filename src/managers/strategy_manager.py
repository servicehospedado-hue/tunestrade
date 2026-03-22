"""
Gerenciador de Estratégias de Trading
Coordena execução de estratégias e emissão de sinais
"""
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from dataclasses import dataclass
import logging

from ..managers.log_manager import get_manager_logger

logger = get_manager_logger("strategy_manager")


@dataclass
class StrategyConfig:
    """Configuração de uma estratégia para um usuário/asset"""
    user_id: str
    asset: str
    strategy_name: str
    timeframe: int
    enabled: bool = True
    min_confidence: float = 0.7
    params: Dict[str, Any] = None


class StrategyManager:
    """
    Gerenciador central de estratégias
    Coordena execução periódica e emissão de sinais
    """
    
    def __init__(self, signal_manager, max_strategies_per_user: int = 10, data_collector=None, indicator_manager=None):
        self.signal_manager = signal_manager
        self.max_strategies_per_user = max_strategies_per_user
        self._data_collector = data_collector
        self._indicator_manager = indicator_manager
        
        # Estratégias registradas
        self._strategies: Dict[str, Any] = {}  # name -> strategy instance
        self._configs: Dict[str, List[StrategyConfig]] = {}  # user_id -> configs
        
        # Cache de DynamicStrategy por usuário (evita query no banco a cada ciclo)
        # Formato: {user_id: {"strategy": DynamicStrategy, "cached_at": float, "strategy_id": str}}
        self._user_strategy_cache: Dict[str, Dict] = {}
        self._user_strategy_cache_ttl: float = 30.0  # segundos
        
        # Controle de execução
        self._running = False
        self._execution_task: Optional[asyncio.Task] = None
        self._last_execution: Dict[str, float] = {}  # asset -> timestamp
        
        # Callbacks para sinais
        self._signal_callbacks: List[Callable] = []
        
    async def start(self):
        """Inicia o gerenciador de estratégias"""
        self._running = True
        self._register_default_strategies()
        self._execution_task = asyncio.create_task(self._execution_loop())
        logger.info(f"StrategyManager iniciado | indicator_manager={self._indicator_manager is not None}")
        
    async def stop(self):
        """Para o gerenciador de estratégias"""
        self._running = False
        if self._execution_task:
            self._execution_task.cancel()
            try:
                await self._execution_task
            except asyncio.CancelledError:
                pass
        logger.info("StrategyManager parado")
        
    def _register_default_strategies(self):
        """Registra estratégias padrão disponíveis"""
        from ..strategies import ScalpingStrategy, TrendM1Strategy

        # Estratégia de Scalping 5s
        self._strategies['Scalping5s'] = ScalpingStrategy(
            timeframe=5,
            min_confidence=0.7
        )

        # Estratégia de Tendência M1
        self._strategies['TrendM1'] = TrendM1Strategy(
            timeframe=60,
            min_confidence=0.40
        )

        logger.info(f"Estratégias registradas: {list(self._strategies.keys())}")
        
    def set_data_collector(self, data_collector):
        """Define o DataCollector (para resolver dependência circular)"""
        self._data_collector = data_collector
        logger.info("[StrategyManager] DataCollector configurado")
        
    def set_indicator_manager(self, indicator_manager):
        """Define o IndicatorManager para logar cálculos"""
        self._indicator_manager = indicator_manager
        logger.info("[StrategyManager] IndicatorManager configurado")
        
    def register_strategy(self, name: str, strategy: Any):
        """Registra uma nova estratégia"""
        self._strategies[name] = strategy
        logger.info(f"Estratégia registrada: {name}")
        
    def get_available_strategies(self) -> Dict[str, Any]:
        """Retorna estratégias disponíveis"""
        return {
            name: {
                'name': strategy.name,
                'description': strategy.description,
                'timeframe': strategy.timeframe
            }
            for name, strategy in self._strategies.items()
        }
        
    async def add_config(self, config: StrategyConfig):
        """Adiciona configuração de estratégia para um usuário"""
        if config.user_id not in self._configs:
            self._configs[config.user_id] = []
            
        # Verificar limite
        if len(self._configs[config.user_id]) >= self.max_strategies_per_user:
            logger.warning(f"Limite de estratégias atingido para {config.user_id}")
            return False
            
        # Remover config anterior para mesmo asset/strategy
        self._configs[config.user_id] = [
            c for c in self._configs[config.user_id]
            if not (c.asset == config.asset and c.strategy_name == config.strategy_name)
        ]
        
        self._configs[config.user_id].append(config)
        logger.info(f"Config adicionada: {config.user_id}/{config.asset}/{config.strategy_name}")
        return True
        
    async def remove_config(self, user_id: str, asset: Optional[str] = None):
        """Remove configurações de estratégia"""
        if user_id not in self._configs:
            return
            
        if asset:
            self._configs[user_id] = [
                c for c in self._configs[user_id] if c.asset != asset
            ]
        else:
            del self._configs[user_id]
            
    def get_user_configs(self, user_id: str) -> List[StrategyConfig]:
        """Retorna configurações de um usuário"""
        return self._configs.get(user_id, [])
        
    def subscribe_signals(self, callback: Callable):
        """Subscreve para receber sinais emitidos"""
        self._signal_callbacks.append(callback)
        
    async def _execution_loop(self):
        """Loop principal de execução das estratégias"""
        execution_count = 0
        while self._running:
            try:
                # Aguardar 1 segundo entre execuções
                await asyncio.sleep(1.0)
                execution_count += 1
                
                # Obter assets monitorados do DataCollector
                monitored_assets = []
                if self._data_collector:
                    monitored_assets = list(self._data_collector._monitored_assets.keys())
                else:
                    if execution_count % 30 == 0:  # Log a cada 30s
                        logger.warning("[STRATEGY] DataCollector nao disponivel")
                    continue
                
                if not monitored_assets:
                    if execution_count % 30 == 0:  # Log a cada 30s
                        logger.info("[STRATEGY] Nenhum asset monitorado")
                    continue
                
                if execution_count % 10 == 0:  # Log a cada 10s
                    logger.info(f"[STRATEGY] Verificando {len(monitored_assets)} assets: {monitored_assets}...")
                
                # Coletar resultados de todos os assets
                results = []
                start_time = datetime.now()
                    
                # Executar estratégias para cada asset
                for asset in monitored_assets:
                    try:
                        result = await self._execute_for_asset(asset)
                        if result:
                            results.append(result)
                    except Exception as e:
                        logger.error(f"[STRATEGY] Erro ao executar {asset}: {e}")
                
                elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
                if execution_count % 10 == 0:
                    logger.info(f"[STRATEGY] Loop executado em {elapsed_ms:.0f}ms | {len(results)} resultados")
                
                # Log resumo se houver sinais
                if results:
                    signals = [r for r in results if r.direction != "NEUTRAL"]
                    if signals:
                        best = max(signals, key=lambda x: x.confidence)
                        logger.info(f"[STRATEGY SUMMARY] {len(signals)} sinais | Melhor: {best.asset} {best.direction} ({best.confidence:.2f})")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no loop de execução: {e}")
                
    async def _execute_for_asset(self, asset: str):
        """Executa estratégias configuradas para um asset. Retorna o resultado."""
        # Verificar cooldown (executar a cada timeframe segundos)
        now = datetime.now().timestamp()
        
        last_exec = self._last_execution.get(asset, 0)
        if now - last_exec < 5:  # Mínimo 5 segundos entre execuções
            return None
        
        self._last_execution[asset] = now
        
        # Obter dados do asset do DataCollector
        # Para TrendM1 (M1): precisa ~36 candles × ~130 ticks/min = ~4700 ticks
        # Para Scalping5s: 100 ticks suficientes
        # Usamos 5000 como limite seguro para cobrir ambos os casos
        ticks = None
        if self._data_collector:
            ticks = await self._data_collector.get_asset_data(asset, limit=5000)
        else:
            logger.debug(f"[STRATEGY] DataCollector não disponível para {asset}")
            return None
        
        if not ticks:
            logger.debug(f"[STRATEGY] Sem dados para {asset}")
            return None
            
        if len(ticks) < 30:
            logger.debug(f"[STRATEGY] Dados insuficientes para {asset}: {len(ticks)} ticks (min: 30)")
            return None
            
        logger.debug(f"[STRATEGY] Analisando {asset} com {len(ticks)} ticks")
            
        # Preparar DataFrame
        import pandas as pd
        df = pd.DataFrame(ticks)
        if 'price' in df.columns:
            df['close'] = df['price']
        df = df.sort_values('timestamp').reset_index(drop=True)
        df['high'] = df['close']
        df['low'] = df['close']
        df['open'] = df['close'].shift(1).fillna(df['close'])
        
        # Se não há configs em memória, buscar usuários ativos no banco
        if not self._configs:
            await self._execute_for_active_users(asset, df)
            return None
        
        # Executar estratégias configuradas
        for user_id, configs in self._configs.items():
            for config in configs:
                if config.asset != asset or not config.enabled:
                    continue
                    
                strategy = self._strategies.get(config.strategy_name)
                if not strategy:
                    continue
                    
                try:
                    # Analisar
                    result = strategy.analyze(df)
                    result.asset = asset
                    
                    # Verificar se deve emitir sinal
                    if result.direction != "NEUTRAL" and result.confidence >= config.min_confidence:
                        await self._emit_signal(config, result)
                    
                    return result
                        
                except Exception as e:
                    logger.error(f"Erro ao executar {config.strategy_name} para {asset}: {e}")
        
        return None
                    
    async def _execute_for_active_users(self, asset: str, df) -> None:
        """Busca usuários com autotrade ativo no banco e executa a estratégia de cada um.
        Emite apenas o sinal de maior confiança por ciclo (sem filtro mínimo)."""
        try:
            from ..database.autotrade_dao import autotrade_dao
            active_configs = await autotrade_dao.list_active_configs()
        except Exception as e:
            logger.debug(f"[STRATEGY] Erro ao buscar configs ativas: {e}")
            active_configs = []

        if not active_configs:
            # Nenhum usuário ativo — executar Scalping5s como fallback de sistema
            result = await self._run_strategy_for_asset('Scalping5s', asset, df, user_id='system')
            if result and result.direction != "NEUTRAL":
                logger.info(f"[STRATEGY] Sinal FORTE: {asset} | Scalping5s | {result.direction} | Conf: {result.confidence:.2f}")
                await self._emit_signal_auto(asset, result)
            return

        # Coletar todos os resultados não-NEUTRAL de todos os usuários ativos
        candidates: list = []
        for config in active_configs:
            strategy_name = config.strategy_name or 'Scalping5s'
            user_id = str(config.user_id)

            # Verificar se o usuário tem estratégia pessoal ativa
            user_strategy_instance = await self._get_user_custom_strategy(user_id, strategy_name)

            result = await self._run_strategy_for_asset(
                strategy_name, asset, df, user_id=user_id,
                custom_strategy=user_strategy_instance
            )
            if result and result.direction != "NEUTRAL":
                candidates.append(result)

        if not candidates:
            return

        # Emitir apenas o sinal de maior confiança
        best = max(candidates, key=lambda r: r.confidence)
        logger.info(f"[STRATEGY] Sinal FORTE: {asset} | {best.direction} | Conf: {best.confidence:.2f}")
        await self._emit_signal_auto(asset, best)

    async def _get_user_custom_strategy(self, user_id: str, base_strategy_name: str):
        """
        Retorna instância de DynamicStrategy com os indicadores exatos escolhidos
        pelo usuário. Usa cache de 30s para evitar queries repetidas ao banco.
        Caso não haja estratégia pessoal ativa, retorna None (usa global).
        """
        now = datetime.now().timestamp()

        # Verificar cache
        cached = self._user_strategy_cache.get(user_id)
        if cached and (now - cached["cached_at"]) < self._user_strategy_cache_ttl:
            return cached["strategy"]  # pode ser None (sem estratégia ativa)

        try:
            from ..database.user_strategy_dao import get_user_strategy_dao
            dao = get_user_strategy_dao()
            if not dao:
                self._user_strategy_cache[user_id] = {"strategy": None, "cached_at": now}
                return None

            strategies = await dao.get_by_user(user_id)
            active = next((s for s in strategies if s.is_active), None)

            if not active or not active.indicators:
                self._user_strategy_cache[user_id] = {"strategy": None, "cached_at": now}
                return None

            from ..strategies.dynamic import DynamicStrategy
            strategy = DynamicStrategy(
                indicators_config=active.indicators,
                timeframe=5,
                min_confidence=0.40,
                strategy_label=active.name,
            )
            logger.info(
                f"[STRATEGY] DynamicStrategy instanciada para user {user_id}: "
                f"'{active.name}' | {len(active.indicators)} indicadores"
            )
            self._user_strategy_cache[user_id] = {
                "strategy": strategy,
                "cached_at": now,
                "strategy_id": str(active.id),
            }
            return strategy

        except Exception as e:
            logger.warning(f"[STRATEGY] Erro ao carregar estratégia customizada para {user_id}: {e}")
            self._user_strategy_cache[user_id] = {"strategy": None, "cached_at": now}
            return None

    def invalidate_user_strategy_cache(self, user_id: str):
        """Invalida cache de estratégia de um usuário (chamar ao salvar/ativar estratégia)."""
        self._user_strategy_cache.pop(user_id, None)
        logger.debug(f"[STRATEGY] Cache de estratégia invalidado para {user_id}")

    def _aggregate_to_candles(self, df, timeframe_seconds: int):
        """Agrega ticks brutos em candles OHLC para o timeframe especificado."""
        if df.empty or len(df) < 2:
            return df
        df = df.copy()
        df['candle_time'] = (df['timestamp'] // timeframe_seconds) * timeframe_seconds
        candles = df.groupby('candle_time').agg(
            open=('close', 'first'),
            high=('close', 'max'),
            low=('close', 'min'),
            close=('close', 'last'),
        ).reset_index()
        candles.rename(columns={'candle_time': 'timestamp'}, inplace=True)
        return candles.sort_values('timestamp').reset_index(drop=True)

    async def _run_strategy_for_asset(self, strategy_name: str, asset: str, df, user_id: str, custom_strategy=None) -> Any:
        """Executa uma estratégia específica para um asset e retorna o resultado (sem filtro de confiança).
        Se custom_strategy for fornecida, usa ela em vez da instância global."""
        # Normalizar snake_case → PascalCase para bater com as chaves de _strategies
        _name_map = {'scalping_5s': 'Scalping5s', 'trend_m1': 'TrendM1'}
        strategy_name = _name_map.get(strategy_name, strategy_name)

        # TrendM1 precisa de candles de 1 minuto — agregar ticks brutos
        _strategy_timeframes = {'TrendM1': 60}
        tf = _strategy_timeframes.get(strategy_name)
        if tf:
            df = self._aggregate_to_candles(df, tf)
            if len(df) < 12:
                logger.debug(f"[STRATEGY] {asset} | {strategy_name} | candles insuficientes após agregação: {len(df)} (min: 12)")
                return None

        # Usar estratégia customizada do usuário se disponível, senão a global
        strategy = custom_strategy or self._strategies.get(strategy_name)
        if not strategy:
            logger.warning(f"[STRATEGY] Estratégia '{strategy_name}' não encontrada para user {user_id}")
            return None

        source = "customizada" if custom_strategy else "global"
        display_name = getattr(custom_strategy, '_strategy_label', strategy_name) if custom_strategy else strategy_name
        try:
            result = strategy.analyze(df)
            result.asset = asset

            logger.info(
                f"[STRATEGY] {asset} | {display_name} ({source}) | user={user_id} | "
                f"{result.direction} | Conf: {result.confidence:.2f} | {result.reason}"
            )

            # Logar indicadores no indicator_manager se disponível
            if self._indicator_manager and result.indicators:
                ind_logger = logging.getLogger("indicator_manager")
                ind_logger.info(
                    f"[{display_name}] {asset} | {result.direction} | Conf: {result.confidence:.2f} | "
                    f"Indicadores: { {k: v.get('signal', '?') for k, v in result.indicators.items()} }"
                )

            return result
        except Exception as e:
            logger.error(f"[STRATEGY] Erro ao executar {strategy_name} para {asset}: {e}")
            return None

    async def _emit_signal(self, config: StrategyConfig, result: Any):
        """Emite sinal via SignalManager e callbacks"""
        from ..managers.signal_manager import SignalType
        
        # Mapear direção para SignalType
        direction_map = {
            "CALL": SignalType.BUY,
            "PUT": SignalType.SELL,
            "NEUTRAL": SignalType.NEUTRAL
        }
        
        signal_type = direction_map.get(result.direction, SignalType.NEUTRAL)
        
        # Criar sinal
        signal_data = {
            "user_id": config.user_id,
            "asset": result.asset,
            "strategy": result.strategy_name,
            "timeframe": result.timeframe,
            "direction": result.direction,
            "entry_price": result.entry_price,
            "confidence": result.confidence,
            "indicators": result.indicators,
            "reason": result.reason,
            "timestamp": result.timestamp
        }
        
        # Notificar callbacks
        for callback in self._signal_callbacks:
            try:
                await callback(signal_data)
            except Exception as e:
                logger.error(f"Erro em callback de sinal: {e}")
                
        # Log do sinal
        logger.info(
            f"[SINAL] {result.asset} | {result.direction} | "
            f"Conf: {result.confidence:.2f} | {result.reason}"
        )
        
    async def _emit_signal_auto(self, asset: str, result: Any):
        """Emite sinal automático (sem config de usuário)"""
        from ..managers.signal_manager import SignalType, Signal, SignalStatus
        import uuid
        
        # Mapear direção para SignalType
        direction_map = {
            "CALL": SignalType.BUY,
            "PUT": SignalType.SELL,
            "NEUTRAL": SignalType.NEUTRAL
        }
        
        signal_type = direction_map.get(result.direction, SignalType.NEUTRAL)
        
        # Criar sinal oficial no SignalManager
        signal = Signal(
            id=str(uuid.uuid4()),
            user_id="system",
            asset=result.asset,
            signal_type=signal_type,
            timeframe=result.timeframe,
            indicators=list(result.indicators.keys()),
            confidence=result.confidence,
            entry_price=result.entry_price,
            status=SignalStatus.PENDING,
            metadata={
                "strategy": result.strategy_name,
                "reason": result.reason,
                "indicators": result.indicators
            }
        )
        
        # Registrar no SignalManager
        if self.signal_manager:
            logger.info(f"[STRATEGY] Registrando sinal no SignalManager: {signal.id[:8]}...")
            await self.signal_manager.register_signal(signal)
        else:
            logger.warning("[STRATEGY] SignalManager não disponível para registrar sinal")
        
        # Criar sinal data para callbacks
        signal_data = {
            "user_id": "system",
            "asset": result.asset,
            "strategy": result.strategy_name,
            "timeframe": result.timeframe,
            "direction": result.direction,
            "entry_price": result.entry_price,
            "confidence": result.confidence,
            "indicators": result.indicators,
            "reason": result.reason,
            "timestamp": result.timestamp,
            "signal_id": signal.id
        }
        
        # Notificar callbacks
        for callback in self._signal_callbacks:
            try:
                await callback(signal_data)
            except Exception as e:
                logger.error(f"Erro em callback de sinal: {e}")
                
        # Log do sinal
        logger.info(
            f"[SINAL AUTO] {result.asset} | {result.direction} | "
            f"Conf: {result.confidence:.2f} | {result.reason}"
        )
        
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do gerenciador"""
        return {
            "registered_strategies": len(self._strategies),
            "configured_users": len(self._configs),
            "total_configs": sum(len(configs) for configs in self._configs.values()),
            "strategies": list(self._strategies.keys())
        }


# Import pandas para uso no módulo
import pandas as pd
