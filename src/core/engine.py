"""
Engine central de trading
Coordena todos os componentes do sistema
"""
import asyncio
from typing import Dict, Optional, List, Any, Any
from dataclasses import dataclass
from datetime import datetime
import logging

from ..managers import (
    SignalManager, SignalConfig,
    UserManager, IndicatorManager,
    ConnectionManager, NotificationManager,
    StrategyManager, TradeExecutor,
    AutotradeManager, AutotradeStatus,
    DataCollectorManager, SystemHealthManager
)
from ..cache.manager import CacheManager
from ..cache.redis_cache import init_redis_cache, close_redis_cache
from ..database.database_manager import DatabaseManager, init_database_manager
from ..database.autotrade_dao import AutotradeDAO, init_autotrade_dao, autotrade_dao
from ..config.settings import Settings
from ..managers.log_manager import get_manager_logger

logger = get_manager_logger("engine")


@dataclass
class SystemStatus:
    """Status do sistema"""
    running: bool = False
    started_at: Optional[datetime] = None
    users_connected: int = 0
    active_tasks: int = 0
    pending_signals: int = 0
    cache_hit_rate: float = 0.0


class TradingEngine:
    """
    Engine central que coordena todo o sistema de trading
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.status = SystemStatus()
        
        # Componentes
        self.db_manager: Optional[DatabaseManager] = None
        self.cache_manager: Optional[CacheManager] = None
        self.user_manager: Optional[UserManager] = None
        self.signal_manager: Optional[SignalManager] = None
        self.indicator_manager: Optional[IndicatorManager] = None
        self.connection_manager: Optional[ConnectionManager] = None
        self.notification_manager: Optional[NotificationManager] = None
        self.strategy_manager: Optional["StrategyManager"] = None
        self.trade_executor: Optional[TradeExecutor] = None
        self.autotrade_manager: Optional[AutotradeManager] = None
        self.data_collector: Optional[DataCollectorManager] = None
        self.system_health: Optional[SystemHealthManager] = None
        
        # Estado de autotrade
        self._autotrade_users: Dict[str, AutotradeStatus] = {}
        
        # Loop de monitoramento
        self._monitoring_task: Optional[asyncio.Task] = None
        self._anti_hibernate_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Inicia o engine de trading"""
        logger.info("Iniciando TradingEngine...")
        
        try:
            # Inicializar banco de dados (auto-cria DB e tabelas)
            db_cfg = self.settings.database
            self.db_manager = await init_database_manager(
                database_url=db_cfg.async_url,
                admin_url=db_cfg.admin_sync_url,
                db_name=db_cfg.name,
                pool_size=db_cfg.pool_size,
                max_overflow=db_cfg.max_overflow,
            )
            logger.info("[OK] DatabaseManager inicializado")
            
            # Inicializar AutotradeDAO e garantir config do admin com estratégia scalping
            await init_autotrade_dao(self.db_manager)
            logger.info("[OK] AutotradeDAO inicializado - Admin vinculado à estratégia Scalping5s")
            
            # Inicializar Redis cache para payouts
            redis_host = self.settings.redis.host
            redis_port = self.settings.redis.port
            if self.settings.redis.enabled:
                redis_initialized = await init_redis_cache(
                    host=redis_host,
                    port=redis_port,
                    password=self.settings.redis.password,
                )
                if redis_initialized:
                    logger.info("[OK] Redis cache conectado para payouts")
                else:
                    logger.warning("[WARN] Redis cache não disponível - payouts só em memória")
            else:
                logger.info("[INFO] Redis desativado (REDIS_ENABLED=false) - payouts só em memória")
            
            # Inicializar componentes
            self.cache_manager = CacheManager(
                max_size_mb=self.settings.cache.max_size_mb,
                default_ttl=self.settings.cache.default_ttl
            )
            await self.cache_manager.start()
            logger.info("[OK] CacheManager iniciado")
            
            # Inicializar ConnectionManager ANTES do DataCollectorManager (para conectar contas de monitoramento)
            self.connection_manager = ConnectionManager(
                config=self.settings.connection_manager
            )
            await self.connection_manager.start()
            logger.info("[OK] ConnectionManager iniciado")
            
            # Inicializar DataCollectorManager (precisa do ConnectionManager para conectar contas)
            dc_cfg = self.settings.data_collector
            self.data_collector = DataCollectorManager(
                db_manager=self.db_manager,
                connection_manager=self.connection_manager,
                max_assets=dc_cfg.max_assets,
                min_payout=dc_cfg.min_payout
            )
            await self.data_collector.start()
            logger.info("[OK] DataCollectorManager iniciado")
            
            self.user_manager = UserManager(
                max_users=self.settings.user_manager.max_users,
                db_manager=self.db_manager
            )
            await self.user_manager.start()
            logger.info("[OK] UserManager iniciado com banco de dados")
            
            # Vincular ConnectionManager ao UserManager para sessões WebSocket reais
            self.user_manager.set_connection_manager(self.connection_manager)
            self.signal_manager = SignalManager(
                max_signals_per_user=self.settings.signal_manager.max_signals_per_user
            )
            # Configurar SignalManager para executar trades automaticamente via Engine
            self.signal_manager.set_autotrade_checker(self)
            await self.signal_manager.start()
            logger.info("[OK] SignalManager iniciado")
            
            self.indicator_manager = IndicatorManager(
                cache_manager=self.cache_manager
            )
            await self.indicator_manager.start()
            logger.info("[OK] IndicatorManager iniciado")
            
            self.notification_manager = NotificationManager(
                provider=self.settings.notification_provider,
                firebase_credentials=self.settings.firebase_credentials,
                onesignal_app_id=self.settings.onesignal_app_id,
                onesignal_api_key=self.settings.onesignal_api_key,
                expo_access_token=self.settings.expo_access_token
            )
            await self.notification_manager.start()
            logger.info("[OK] NotificationManager iniciado")
            
            # Inicializar StrategyManager
            self.strategy_manager = StrategyManager(
                signal_manager=self.signal_manager,
                max_strategies_per_user=self.settings.strategy_manager.max_strategies_per_user,
                data_collector=self.data_collector,
                indicator_manager=self.indicator_manager
            )
            await self.strategy_manager.start()
            logger.info("[OK] StrategyManager iniciado")
            
            # Inicializar TradeExecutor (usa ConnectionManager para executar trades)
            self.trade_executor = TradeExecutor(
                db_manager=self.db_manager,
                connection_manager=self.connection_manager,
            )
            await self.trade_executor.start()
            logger.info("[OK] TradeExecutor iniciado")
            
            # Configurar DataCollector no ConnectionManager (para processar ticks dos clientes)
            if self.connection_manager:
                self.connection_manager.set_data_collector(self.data_collector)
                
                # Registrar callback para sincronizar ordens após reconexão
                self.connection_manager.subscribe("reconnected", self._on_connection_reconnected)
            
            # Inicializar AutotradeManager (apenas monitora configs, engine orquestra)
            self.autotrade_manager = AutotradeManager(
                db_manager=self.db_manager,
                cache_manager=self.cache_manager,
                full_refresh_interval=60
            )
            
            # Configurar dependências do AutotradeManager ANTES do start()
            self.autotrade_manager.set_dependencies(
                connection_manager=self.connection_manager,
                user_manager=self.user_manager
            )
            
            # Registrar callbacks ANTES do start() para capturar usuários ativos
            self.autotrade_manager.on_enabled(self._on_autotrade_enabled)
            self.autotrade_manager.on_disabled(self._on_autotrade_disabled)
            
            await self.autotrade_manager.start()
            logger.info("[OK] AutotradeManager iniciado")
            
            # Configurar DataCollector no StrategyManager (dependência circular resolvida)
            if self.strategy_manager:
                self.strategy_manager.set_data_collector(self.data_collector)
            
            # Conectar callback de payout_update do ConnectionManager ao DataCollectorManager
            async def on_payout_update(event_data: dict):
                logger.info(f"[Engine] payout_update recebido: {len(event_data.get('data', {}).get('assets', {}))} ativos")
                data = event_data.get("data", {})
                if data and "assets" in data:
                    # Converter para formato esperado pelo DataCollectorManager
                    payouts = {symbol: info.get("payout", 0) for symbol, info in data["assets"].items()}
                    logger.info(f"[Engine] Chamando update_all_assets com {len(payouts)} ativos")
                    await self.data_collector.update_all_assets(payouts)
                    logger.info(f"[Engine] update_all_assets concluído")
                else:
                    logger.warning(f"[Engine] payout_update sem dados de ativos: {event_data}")
            
            self.connection_manager.subscribe("payout_update", on_payout_update)
            logger.info("[Engine] Callback payout_update registrado no ConnectionManager")
            
            # Inicializar SystemHealthManager (métricas do sistema)
            self.system_health = SystemHealthManager(
                check_interval=self.settings.system_health.check_interval
            )
            await self.system_health.start()
            logger.info("[OK] SystemHealthManager iniciado")
            
            # Registrar componentes para monitoramento de saúde
            self.system_health.register_component("cache", self.cache_manager)
            self.system_health.register_component("users", self.user_manager)
            self.system_health.register_component("signals", self.signal_manager)
            self.system_health.register_component("indicators", self.indicator_manager)
            self.system_health.register_component("connection", self.connection_manager)
            self.system_health.register_component("notifications", self.notification_manager)
            self.system_health.register_component("strategy", self.strategy_manager)
            self.system_health.register_component("trade_executor", self.trade_executor)
            self.system_health.register_component("autotrade", self.autotrade_manager)
            self.system_health.register_component("data_collector", self.data_collector)
            
            # Registrar callbacks para orquestrar conexões (já registrados antes do start())
            # self.autotrade_manager.on_enabled(self._on_autotrade_enabled)  # duplicado removido
            # self.autotrade_manager.on_disabled(self._on_autotrade_disabled)  # duplicado removido
            
            # Estado de usuários autotrade ativos
            self._autotrade_users: Dict[str, AutotradeStatus] = {}
            
            # Iniciar monitoramento do sistema
            self._running = True
            self._monitoring_task = asyncio.create_task(self._monitor_system())
            self._anti_hibernate_task = asyncio.create_task(self._anti_hibernate_loop())
            
            # Configurar integração entre componentes
            await self._setup_integration()
            
            self.status.running = True
            self.status.started_at = datetime.now()
            
            logger.info("[OK] TradingEngine iniciado com sucesso!")
            logger.info("[OK] API disponível - Contas de monitoramento conectando em paralelo...")
            
        except Exception as e:
            logger.exception(f"[ERRO] Falha ao iniciar TradingEngine: {e}")
            raise
        
    async def stop(self):
        """Para o engine de trading"""
        # Proteção contra chamada dupla
        if not self._running:
            logger.debug("Engine já está parado ou parando, ignorando...")
            return
        
        logger.info("Parando TradingEngine...")
        
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"Erro ao cancelar monitoring task: {e}")

        if self._anti_hibernate_task:
            self._anti_hibernate_task.cancel()
            try:
                await self._anti_hibernate_task
            except asyncio.CancelledError:
                pass
        
        # Parar autotrade
        if self.autotrade_manager:
            try:
                await self.autotrade_manager.stop()
                logger.info("[OK] AutotradeManager parado")
            except Exception as e:
                logger.warning(f"Erro ao parar AutotradeManager: {e}")
        
        # Parar componentes com tratamento de erro
        try:
            await close_redis_cache()
        except Exception as e:
            logger.warning(f"Erro ao fechar Redis: {e}")
            
        components = [
            ("DataCollectorManager", self.data_collector),
            ("AutotradeManager", self.autotrade_manager),
            ("TradeExecutor", self.trade_executor),
            ("StrategyManager", self.strategy_manager),
            ("NotificationManager", self.notification_manager),
            ("ConnectionManager", self.connection_manager),
            ("IndicatorManager", self.indicator_manager),
            ("SignalManager", self.signal_manager),
            ("UserManager", self.user_manager),
            ("CacheManager", self.cache_manager),
            ("DatabaseManager", self.db_manager),
        ]
        
        for name, component in components:
            if component:
                try:
                    await component.stop()
                except Exception as e:
                    logger.warning(f"Erro ao parar {name}: {e}")
                    
        self.status.running = False
        logger.info("TradingEngine parado")
        
    async def _setup_integration(self):
        """Configura integração entre componentes"""
        # Quando um indicador é calculado, processar para sinais
        async def on_indicator_completed(task):
            if task.result and task.status == "completed":
                await self.signal_manager.process_indicator_result(
                    user_id=task.user_id,
                    asset=task.asset,
                    timeframe=task.timeframe,
                    indicator_result=task.result
                )
                
        # Registrar callback global (implementação simplificada)
        logger.info("Integração entre componentes configurada")
        
    async def register_user(self, user_id: str, ssid: str, is_demo: bool = True) -> bool:
        """Registra um usuário no sistema"""
        if not self.user_manager:
            return False
            
        success = await self.user_manager.register_user(user_id, ssid, is_demo)
        if success:
            await self.user_manager.connect_user(user_id)
        return success
        
    async def setup_user_signals(self, user_id: str, config: SignalConfig):
        """Configura geração de sinais para um usuário"""
        if not self.signal_manager:
            return
            
        await self.signal_manager.add_user_config(config)
        
        # Configurar indicadores necessários
        indicators = [
            {"type": ind.name, "params": ind.params}
            for ind in config.indicators
        ]
        
        await self.indicator_manager.set_user_indicators(user_id, indicators)
        
    async def process_user_request(self, user_id: str, asset: str, timeframe: int):
        """Processa requisição de análise para um usuário"""
        if not self.indicator_manager:
            return
            
        indicators = self.indicator_manager.get_user_indicators(user_id)
        
        if indicators:
            await self.indicator_manager.calculate_multiple(
                user_id=user_id,
                asset=asset,
                timeframe=timeframe,
                indicators=indicators
            )
            
    async def get_system_status(self) -> SystemStatus:
        """Retorna status atual do sistema"""
        if self.user_manager:
            user_stats = self.user_manager.get_stats()
            self.status.users_connected = user_stats.get("active_users", 0)
            
        if self.signal_manager:
            signal_stats = self.signal_manager.get_stats()
            self.status.pending_signals = signal_stats.get("pending", 0)
            
        if self.cache_manager:
            cache_stats = self.cache_manager.get_stats()
            self.status.cache_hit_rate = cache_stats.get("hit_rate", 0.0)
            
        return self.status
        
    async def _monitor_system(self):
        """Monitora sistema periodicamente"""
        while self._running:
            try:
                await asyncio.sleep(60)  # Log a cada minuto
                
                status = await self.get_system_status()
                logger.info(
                    f"Status: {status.users_connected} usuários, "
                    f"{status.active_tasks} tarefas, "
                    f"{status.pending_signals} sinais, "
                    f"cache: {status.cache_hit_rate:.1%}"
                )
                
            except Exception as e:
                logger.error(f"Erro no monitoramento: {e}")

    async def _anti_hibernate_loop(self):
        """Self-ping a cada 10 minutos para evitar hibernação no Railway."""
        import aiohttp
        import os
        await asyncio.sleep(60)  # aguardar sistema subir antes do primeiro ping
        host = os.getenv("API_HOST", "0.0.0.0")
        port = int(os.getenv("API_PORT", "8000"))
        url = f"http://127.0.0.1:{port}/system/ping"
        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        logger.debug(f"[ANTI-HIBERNATE] self-ping {resp.status}")
            except Exception as e:
                logger.debug(f"[ANTI-HIBERNATE] ping falhou: {e}")
            await asyncio.sleep(600)  # 10 minutos
                
    async def get_user_signals(self, user_id: str, status: Optional[str] = None) -> List:
        """Obtém sinais de um usuário"""
        if not self.signal_manager:
            return []
        return self.signal_manager.get_user_signals(user_id, status)
        
    async def get_full_stats(self) -> Dict:
        """Retorna estatísticas completas do sistema"""
        return {
            "system": self.status,
            "users": self.user_manager.get_stats() if self.user_manager else {},
            "signals": self.signal_manager.get_stats() if self.signal_manager else {},
            "cache": self.cache_manager.get_stats() if self.cache_manager else {},
            "indicators": self.indicator_manager.get_stats() if self.indicator_manager else {},
            "notifications": self.notification_manager.get_stats() if self.notification_manager else {},
            "data_collector": self.data_collector.get_stats() if self.data_collector else {},
            "autotrade": self.autotrade_manager.get_stats() if self.autotrade_manager else {},
            "trade_executor": self.trade_executor.get_stats() if self.trade_executor else {}
        }

    # ========== Autotrade Methods (Engine orquestra) ==========

    def _on_autotrade_enabled(self, user_id: str, status: AutotradeStatus):
        """Callback quando usuário ativa autotrade - Engine conecta via AutotradeManager"""
        logger.info(f"[AUTOTRADE] Ativado para {user_id}, conectando...")
        asyncio.create_task(self.autotrade_manager.connect_user(user_id, status))
    
    def _on_autotrade_disabled(self, user_id: str, status: AutotradeStatus):
        """Callback quando usuário desativa autotrade - Engine desconecta via AutotradeManager"""
        logger.info(f"[AUTOTRADE] Desativado para {user_id}, desconectando...")
        asyncio.create_task(self.autotrade_manager.disconnect_user(user_id))
        # Resetar estado de sessão ao desativar (zera contadores para próxima sessão)
        if self.trade_executor:
            asyncio.create_task(self.trade_executor.reset_session_state(user_id))
    
    def _on_connection_reconnected(self, data: Dict[str, Any]):
        """Callback quando uma conexão é reconectada - sincroniza ordens pendentes"""
        user_id = data.get("user_id")
        client = data.get("client")
        
        if user_id and client and self.trade_executor:
            logger.info(f"[RECONNECT] Sincronizando ordens para {user_id}")
            asyncio.create_task(self.trade_executor.sync_pending_orders(user_id, client))

    async def execute_signal(self, signal: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Executa um sinal - Engine orquestra via TradeExecutor"""
        logger.info(f"[SIGNAL] Recebido: {signal.get('asset')} | {signal.get('direction')} | conf: {signal.get('confidence', 0):.2f}")
        
        if not self.trade_executor:
            logger.warning("[SIGNAL] TradeExecutor não disponível")
            return []
        
        # Obter usuários conectados do AutotradeManager
        connected_users = self.autotrade_manager.get_connected_users() if self.autotrade_manager else []
        logger.info(f"[SIGNAL] Usuários conectados: {connected_users}")
        
        if not connected_users and self.autotrade_manager:
            # Tentar reconectar usuários ativos no banco que ainda não estão conectados
            try:
                all_active = await self.autotrade_manager.get_all_active()
                if all_active:
                    logger.info(f"[SIGNAL] {len(all_active)} usuário(s) ativo(s) no banco — tentando conectar...")
                    for uid, status in all_active.items():
                        if not self.autotrade_manager.is_user_connected(uid):
                            await self.autotrade_manager.connect_user(uid, status)
                    connected_users = self.autotrade_manager.get_connected_users()
                    logger.info(f"[SIGNAL] Após reconexão: {connected_users}")
            except Exception as _e:
                logger.debug(f"[SIGNAL] Erro ao tentar reconectar usuários: {_e}")

        if not connected_users:
            logger.warning("[SIGNAL] Nenhum usuário conectado para executar trade")
            return []
        
        try:
            asset = signal.get("asset")
            direction = signal.get("direction")
            confidence = signal.get("confidence", 0)
            
            if not asset or direction == "NEUTRAL" or confidence < 0.40:
                logger.info(f"[SIGNAL] Sinal ignorado: asset={asset}, direction={direction}, confidence={confidence}")
                return []
            
            logger.info(f"[SIGNAL] Executando: {asset} | {direction} | conf: {confidence:.2f}")
            
            # Construir dict de usuários ativos a partir dos usuários conectados
            active_users = {}
            for user_id in connected_users:
                # get_status é async, precisamos aguardar
                status = await self.autotrade_manager.get_status(user_id)
                if status and status.enabled:
                    active_users[user_id] = status
                    logger.info(f"[SIGNAL] Usuário ativo: {user_id} | strategy: {status.strategy_name}")
            
            if not active_users:
                logger.warning("[SIGNAL] Nenhum usuário ativo encontrado (get_status retornou None ou disabled)")
                return []
            
            # Executar via TradeExecutor
            results = await self.trade_executor.execute_signal(signal, active_users)
            
            if results:
                logger.info(f"[TRADE] {len(results)} trades executados")
            else:
                logger.debug("[SIGNAL] TradeExecutor retornou sem resultados (cooldown ativo ou confiança baixa)")
            
            return results
            
        except Exception as e:
            logger.error(f"[SIGNAL] Erro ao executar: {e}")
            return []
    
    def get_autotrade_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do autotrade"""
        if not self.autotrade_manager:
            return {"running": False, "active_users": 0}
        return self.autotrade_manager.get_stats()

