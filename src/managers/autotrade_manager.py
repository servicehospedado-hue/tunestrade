"""
AutotradeManager - Gerenciador de estado/configs de autotrade
Responsabilidade única: monitorar configs de autotrade dos usuários
"""
import asyncio
from typing import Dict, Set, Optional, Callable, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import logging

from ..database import DatabaseManager, User
from ..cache.manager import CacheManager

logger = logging.getLogger("autotrade_manager")

CACHE_KEY_PREFIX = "autotrade:status:"
CACHE_TTL = 30  # segundos


@dataclass
class AutotradeStatus:
    """Status de autotrade de um usuário"""
    user_id: str
    enabled: bool
    amount: float
    strategy_name: str
    cooldown: str = "60"  # Cooldown: '60' (fixo) ou '60-120' (intervalo)
    ssid_demo: Optional[str] = None
    ssid_real: Optional[str] = None
    operator: str = "demo"
    cached_at: datetime = field(default_factory=datetime.now)
    # Stops
    stop_loss_enabled: bool = False
    stop_loss_value: float = 0.0
    stop_gain_enabled: bool = False
    stop_gain_value: float = 0.0
    stop_soft_mode: bool = False
    stop_win_seq_enabled: bool = False
    stop_win_seq: int = 3
    stop_loss_seq_enabled: bool = False
    stop_loss_seq: int = 3
    stop_seq_soft_mode: bool = False
    stop_medium_enabled: bool = False
    stop_medium_pct: float = 0.0
    stop_medium_soft_mode: bool = False
    # Redução Inteligente
    reduce_enabled: bool = False
    reduce_loss_trigger: int = 3
    reduce_win_exit: int = 2
    reduce_pct: float = 50.0
    # Martingale
    martingale_enabled: bool = False
    martingale_levels: int = 3
    martingale_multiplier: float = 2.0
    # Soros
    soros_enabled: bool = False
    soros_levels: int = 3
    soros_pct: float = 100.0
    
    def get_cooldown_seconds(self) -> int:
        """
        Retorna o cooldown em segundos.
        Se for intervalo (ex: '60-120'), retorna valor aleatório dentro do intervalo.
        """
        import random
        if '-' in self.cooldown:
            min_val, max_val = self.cooldown.split('-')
            return random.randint(int(min_val.strip()), int(max_val.strip()))
        return int(self.cooldown)
    
    @property
    def can_connect(self) -> bool:
        """Verifica se o usuário pode conectar (tem SSID)"""
        ssid = self.ssid_demo if self.operator == "demo" else self.ssid_real
        return self.enabled and ssid is not None and len(ssid) > 0
    
    def is_cache_valid(self, ttl_seconds: int) -> bool:
        """Verifica se o cache ainda é válido"""
        elapsed = (datetime.now() - self.cached_at).total_seconds()
        return elapsed < ttl_seconds


class AutotradeManager:
    """
    Gerenciador de estado/configs de autotrade.
    
    Responsabilidade única: monitorar configs de autotrade dos usuários.
    NÃO conecta usuários (isso é da Engine).
    NÃO executa trades (isso é do TradeExecutor).
    
    Apenas notifica a Engine quando configs mudam via callbacks.
    """
    
    def __init__(
        self,
        db_manager: DatabaseManager,
        cache_manager: Optional[CacheManager] = None,
        full_refresh_interval: int = 60,  # Refresh completo a cada 60s
    ):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.full_refresh_interval = full_refresh_interval
        
        # Apenas rastreia IDs ativos (dados ficam no CacheManager)
        self._active_ids: Set[str] = set()
        
        # Cache de status dos usuários
        self._status_cache: Dict[str, AutotradeStatus] = {}
        self._cache_lock = asyncio.Lock()
        
        # Callbacks para mudanças de status
        self._on_enabled: Set[Callable[[str, AutotradeStatus], None]] = set()
        self._on_disabled: Set[Callable[[str, AutotradeStatus], None]] = set()
        self._on_changed: Set[Callable[[str, AutotradeStatus, AutotradeStatus], None]] = set()
        
        # Estado de conexão dos usuários
        self._connected_users: Set[str] = set()
        self._connection_manager: Optional[Any] = None
        self._user_manager: Optional[Any] = None
        
        # Callbacks para notificar sobre conexão
        self._on_connected: Set[Callable[[str], None]] = set()
        self._on_disconnected: Set[Callable[[str], None]] = set()
        
        # Estado
        self._running = False
        self._refresh_task: Optional[asyncio.Task] = None
        self._pubsub_task: Optional[asyncio.Task] = None  # Inicializado aqui
        self._last_full_refresh: Optional[datetime] = None  # Timestamp do último refresh completo
        self.use_redis_pubsub: bool = False  # Desabilitado por padrão
        self.cache_ttl: int = CACHE_TTL  # TTL do cache
        
    def _cache_key(self, user_id: str) -> str:
        """Gera chave de cache para um usuário"""
        return f"{CACHE_KEY_PREFIX}{user_id}"
        
    async def start(self):
        """Inicia o monitor de configs"""
        logger.info("[AutotradeManager] Iniciando monitor de configs...")
        self._running = True
        
        # Primeiro carregamento
        await self._do_full_refresh()
        
        # Iniciar loop de refresh periódico
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        
        # Iniciar listener de pubsub se habilitado
        if self.use_redis_pubsub and self.cache_manager:
            self._pubsub_task = asyncio.create_task(self._pubsub_listener())
            
    async def stop(self):
        """Para o monitor"""
        logger.info("[AutotradeManager] Parando...")
        self._running = False
        
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
                
        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
                
        logger.info("AutotradeMonitor parado")
        
    async def _refresh_loop(self):
        """Loop de refresh periódico do cache"""
        while self._running:
            try:
                await asyncio.sleep(self.full_refresh_interval)
                if self._running:
                    await self._do_full_refresh()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no refresh loop: {e}")
                
    async def _do_full_refresh(self):
        """Faz refresh completo do cache consultando o banco"""
        try:
            start_time = datetime.now()
            
            async with self.db_manager.get_session() as session:
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload
                
                # Buscar todos os usuários com autotrade habilitado
                result = await session.execute(
                    select(User)
                    .options(selectinload(User.autotrade_config))
                    .where(User.autotrade_config.has(autotrade=1))
                )
                users = result.scalars().all()
                
                # Novo estado
                new_active_ids: Set[str] = set()
                
                async with self._cache_lock:
                    for user in users:
                        user_id = str(user.id)
                        new_active_ids.add(user_id)
                        
                        # Verificar se houve mudança
                        old_status = self._status_cache.get(user_id)
                        cfg = user.autotrade_config
                        new_status = AutotradeStatus(
                            user_id=user_id,
                            enabled=True,
                            amount=float(cfg.amount),
                            strategy_name=cfg.strategy_name,
                            cooldown=cfg.cooldown if cfg.cooldown else "60",
                            ssid_demo=user.ssid_demo,
                            ssid_real=user.ssid_real,
                            operator=user.operator,
                            cached_at=datetime.now(),
                            # Stops
                            stop_loss_enabled=bool(cfg.stop_loss_enabled) if cfg.stop_loss_enabled else False,
                            stop_loss_value=float(cfg.stop_loss_value) if cfg.stop_loss_value else 0.0,
                            stop_gain_enabled=bool(cfg.stop_gain_enabled) if cfg.stop_gain_enabled else False,
                            stop_gain_value=float(cfg.stop_gain_value) if cfg.stop_gain_value else 0.0,
                            stop_soft_mode=bool(cfg.stop_soft_mode) if cfg.stop_soft_mode else False,
                            stop_win_seq_enabled=bool(cfg.stop_win_seq_enabled) if cfg.stop_win_seq_enabled else False,
                            stop_win_seq=int(cfg.stop_win_seq) if cfg.stop_win_seq else 3,
                            stop_loss_seq_enabled=bool(cfg.stop_loss_seq_enabled) if cfg.stop_loss_seq_enabled else False,
                            stop_loss_seq=int(cfg.stop_loss_seq) if cfg.stop_loss_seq else 3,
                            stop_seq_soft_mode=bool(cfg.stop_seq_soft_mode) if cfg.stop_seq_soft_mode else False,
                            stop_medium_enabled=bool(cfg.stop_medium_enabled) if cfg.stop_medium_enabled else False,
                            stop_medium_pct=float(cfg.stop_medium_pct) if cfg.stop_medium_pct else 0.0,
                            stop_medium_soft_mode=bool(cfg.stop_medium_soft_mode) if cfg.stop_medium_soft_mode else False,
                            # Redução
                            reduce_enabled=bool(cfg.reduce_enabled) if cfg.reduce_enabled else False,
                            reduce_loss_trigger=int(cfg.reduce_loss_trigger) if cfg.reduce_loss_trigger else 3,
                            reduce_win_exit=int(cfg.reduce_win_exit) if cfg.reduce_win_exit else 2,
                            reduce_pct=float(cfg.reduce_pct) if cfg.reduce_pct else 50.0,
                            # Martingale
                            martingale_enabled=bool(cfg.martingale_enabled) if cfg.martingale_enabled else False,
                            martingale_levels=int(cfg.martingale_levels) if cfg.martingale_levels else 3,
                            martingale_multiplier=float(cfg.martingale_multiplier) if cfg.martingale_multiplier else 2.0,
                            # Soros
                            soros_enabled=bool(cfg.soros_enabled) if cfg.soros_enabled else False,
                            soros_levels=int(cfg.soros_levels) if cfg.soros_levels else 3,
                            soros_pct=float(cfg.soros_pct) if cfg.soros_pct else 100.0,
                        )
                        
                        # Detectar mudanças
                        if old_status is None:
                            # Novo usuário ativado
                            self._status_cache[user_id] = new_status
                            await self._notify_enabled(user_id, new_status)
                        elif not old_status.enabled:
                            # Reativado
                            self._status_cache[user_id] = new_status
                            await self._notify_enabled(user_id, new_status)
                        elif user_id not in self._connected_users:
                            # Usuário ativo no banco mas não conectado (ex: restart do servidor)
                            self._status_cache[user_id] = new_status
                            logger.info(f"[AutotradeManager] Usuário {user_id} ativo mas não conectado — reconectando...")
                            await self._notify_enabled(user_id, new_status)
                        elif old_status.strategy_name != new_status.strategy_name:
                            # Mudança de estratégia
                            self._status_cache[user_id] = new_status
                            await self._notify_changed(user_id, old_status, new_status)
                        else:
                            # Sem mudanças — apenas atualiza cache_at para evitar expiração
                            self._status_cache[user_id] = new_status
                            
                    # Detectar desativações
                    old_active_ids = set(self._status_cache.keys())
                    disabled_ids = old_active_ids - new_active_ids
                    
                    for user_id in disabled_ids:
                        old_status = self._status_cache[user_id]
                        if old_status.enabled:
                            # Desativado
                            new_status = AutotradeStatus(
                                user_id=user_id,
                                enabled=False,
                                amount=old_status.amount,
                                strategy_name=old_status.strategy_name,
                                ssid_demo=old_status.ssid_demo,
                                ssid_real=old_status.ssid_real,
                                operator=old_status.operator,
                                cached_at=datetime.now()
                            )
                            self._status_cache[user_id] = new_status
                            await self._notify_disabled(user_id, new_status)
                
                elapsed = (datetime.now() - start_time).total_seconds()
                self._last_full_refresh = datetime.now()
                logger.debug(f"Full refresh concluído em {elapsed:.3f}s: {len(new_active_ids)} ativos")
                
        except Exception as e:
            logger.error(f"Erro no full refresh: {e}")
            
    async def get_status(self, user_id: str) -> Optional[AutotradeStatus]:
        """
        Obtém status de autotrade de um usuário.
        Usa cache se válido, senão consulta o banco (lazy loading).
        """
        # Verificar cache primeiro
        async with self._cache_lock:
            cached = self._status_cache.get(user_id)
            if cached:
                if cached.is_cache_valid(self.cache_ttl):
                    logger.debug(f"[get_status] Cache válido para {user_id}: enabled={cached.enabled}")
                    return cached
                else:
                    logger.debug(f"[get_status] Cache expirado para {user_id}")
        
        # Cache expirado ou não existe - lazy load do banco
        logger.debug(f"[get_status] Buscando do banco: {user_id}")
        try:
            async with self.db_manager.get_session() as session:
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload
                
                result = await session.execute(
                    select(User)
                    .options(selectinload(User.autotrade_config))
                    .where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    logger.warning(f"[get_status] Usuário {user_id} não encontrado no banco")
                    return None
                
                # Criar novo status com todos os campos de gestão de banca
                cfg = user.autotrade_config
                status = AutotradeStatus(
                    user_id=user_id,
                    enabled=cfg.autotrade == 1 if cfg else False,
                    amount=float(cfg.amount) if cfg else 0.0,
                    strategy_name=cfg.strategy_name if cfg else "",
                    cooldown=cfg.cooldown if cfg else "60",
                    ssid_demo=user.ssid_demo,
                    ssid_real=user.ssid_real,
                    operator=user.operator,
                    cached_at=datetime.now(),
                    # Stops
                    stop_loss_enabled=bool(cfg.stop_loss_enabled) if cfg else False,
                    stop_loss_value=float(cfg.stop_loss_value) if cfg and cfg.stop_loss_value else 0.0,
                    stop_gain_enabled=bool(cfg.stop_gain_enabled) if cfg else False,
                    stop_gain_value=float(cfg.stop_gain_value) if cfg and cfg.stop_gain_value else 0.0,
                    stop_soft_mode=bool(cfg.stop_soft_mode) if cfg else False,
                    stop_win_seq_enabled=bool(cfg.stop_win_seq_enabled) if cfg else False,
                    stop_win_seq=int(cfg.stop_win_seq) if cfg and cfg.stop_win_seq else 3,
                    stop_loss_seq_enabled=bool(cfg.stop_loss_seq_enabled) if cfg else False,
                    stop_loss_seq=int(cfg.stop_loss_seq) if cfg and cfg.stop_loss_seq else 3,
                    stop_seq_soft_mode=bool(cfg.stop_seq_soft_mode) if cfg else False,
                    stop_medium_enabled=bool(cfg.stop_medium_enabled) if cfg else False,
                    stop_medium_pct=float(cfg.stop_medium_pct) if cfg and cfg.stop_medium_pct else 0.0,
                    stop_medium_soft_mode=bool(cfg.stop_medium_soft_mode) if cfg else False,
                    # Redução
                    reduce_enabled=bool(cfg.reduce_enabled) if cfg else False,
                    reduce_loss_trigger=int(cfg.reduce_loss_trigger) if cfg and cfg.reduce_loss_trigger else 3,
                    reduce_win_exit=int(cfg.reduce_win_exit) if cfg and cfg.reduce_win_exit else 2,
                    reduce_pct=float(cfg.reduce_pct) if cfg and cfg.reduce_pct else 50.0,
                    # Martingale
                    martingale_enabled=bool(cfg.martingale_enabled) if cfg else False,
                    martingale_levels=int(cfg.martingale_levels) if cfg and cfg.martingale_levels else 3,
                    martingale_multiplier=float(cfg.martingale_multiplier) if cfg and cfg.martingale_multiplier else 2.0,
                    # Soros
                    soros_enabled=bool(cfg.soros_enabled) if cfg else False,
                    soros_levels=int(cfg.soros_levels) if cfg and cfg.soros_levels else 3,
                    soros_pct=float(cfg.soros_pct) if cfg and cfg.soros_pct else 100.0,
                )
                
                logger.info(
                    f"[get_status] Status carregado: {user_id} | enabled={status.enabled} | "
                    f"strategy={status.strategy_name} | soros={status.soros_enabled} | "
                    f"mart={status.martingale_enabled} | reduce={status.reduce_enabled}"
                )
                
                async with self._cache_lock:
                    self._status_cache[user_id] = status
                
                return status
                
        except Exception as e:
            logger.error(f"Erro ao buscar status do usuário {user_id}: {e}")
            return None
    
    async def get_all_active(self) -> Dict[str, AutotradeStatus]:
        """Retorna todos os usuários com autotrade ativo"""
        async with self._cache_lock:
            return {
                uid: status for uid, status in self._status_cache.items()
                if status.enabled
            }
    
    async def invalidate_cache(self, user_id: str):
        """Invalida o cache de um usuário específico"""
        async with self._cache_lock:
            if user_id in self._status_cache:
                del self._status_cache[user_id]
                logger.debug(f"Cache invalidado para usuário {user_id}")
    
    async def invalidate_user_cache(self, user_id: str) -> Optional[AutotradeStatus]:
        """
        Invalida cache e recarrega status do usuário do banco.
        Notifica callbacks se houve mudança de estado.
        
        Args:
            user_id: ID do usuário
            
        Returns:
            Novo status ou None se erro
        """
        logger.info(f"[INVALIDATE] Invalidando cache para user {user_id}")
        
        # Guardar status antigo
        async with self._cache_lock:
            old_status = self._status_cache.get(user_id)
            if user_id in self._status_cache:
                del self._status_cache[user_id]
        
        # Recarregar do banco
        new_status = await self.get_status(user_id)
        
        if new_status:
            # Notificar mudanças
            if old_status:
                if not old_status.enabled and new_status.enabled:
                    # Ativado
                    await self._notify_enabled(user_id, new_status)
                elif old_status.enabled and not new_status.enabled:
                    # Desativado
                    await self._notify_disabled(user_id, new_status)
                elif old_status.enabled and new_status.enabled:
                    if old_status.strategy_name != new_status.strategy_name:
                        # Mudança de estratégia
                        await self._notify_changed(user_id, old_status, new_status)
            elif new_status.enabled:
                # Novo usuário ativado
                await self._notify_enabled(user_id, new_status)
        
        return new_status
    
    async def handle_webhook(self, user_id: str, event_type: str, data: Dict[str, Any]):
        """
        Handler para webhooks de mudança de autotrade.
        Chamado quando o frontend notifica uma mudança.
        """
        logger.info(f"Webhook recebido: user={user_id}, event={event_type}")
        
        if event_type == "autotrade_enabled":
            await self.invalidate_cache(user_id)
            status = await self.get_status(user_id)
            if status and status.enabled:
                await self._notify_enabled(user_id, status)
                
        elif event_type == "autotrade_disabled":
            async with self._cache_lock:
                if user_id in self._status_cache:
                    old_status = self._status_cache[user_id]
                    new_status = AutotradeStatus(
                        user_id=user_id,
                        enabled=False,
                        amount=old_status.amount,
                        strategy_name=old_status.strategy_name,
                        ssid_demo=old_status.ssid_demo,
                        ssid_real=old_status.ssid_real,
                        operator=old_status.operator,
                        cached_at=datetime.now()
                    )
                    self._status_cache[user_id] = new_status
                    await self._notify_disabled(user_id, new_status)
                    
        elif event_type == "config_updated":
            await self.invalidate_cache(user_id)
            # Forçar recarregamento
            await self.get_status(user_id)
            
        elif event_type == "full_refresh":
            await self._do_full_refresh()
    
    def on_enabled(self, callback: Callable[[str, AutotradeStatus], None]):
        """Registra callback para quando autotrade é ativado"""
        self._on_enabled.add(callback)
        
    def on_disabled(self, callback: Callable[[str, AutotradeStatus], None]):
        """Registra callback para quando autotrade é desativado"""
        self._on_disabled.add(callback)
        
    def on_changed(self, callback: Callable[[str, AutotradeStatus, AutotradeStatus], None]):
        """Registra callback para quando config muda"""
        self._on_changed.add(callback)
        
    def remove_callback(self, callback):
        """Remove um callback"""
        self._on_enabled.discard(callback)
        self._on_disabled.discard(callback)
        self._on_changed.discard(callback)
    
    async def _notify_enabled(self, user_id: str, status: AutotradeStatus):
        """Notifica callbacks de ativação"""
        logger.info(f"Autotrade ATIVADO para usuário {user_id}")
        for callback in self._on_enabled:
            try:
                callback(user_id, status)
            except Exception as e:
                logger.error(f"Erro em callback on_enabled: {e}")
                
    async def _notify_disabled(self, user_id: str, status: AutotradeStatus):
        """Notifica callbacks de desativação"""
        logger.info(f"Autotrade DESATIVADO para usuário {user_id}")
        for callback in self._on_disabled:
            try:
                callback(user_id, status)
            except Exception as e:
                logger.error(f"Erro em callback on_disabled: {e}")
                
    async def _notify_changed(self, user_id: str, old: AutotradeStatus, new: AutotradeStatus):
        """Notifica callbacks de mudança"""
        logger.info(f"Autotrade ALTERADO para usuário {user_id}: {old.strategy_name} -> {new.strategy_name}")
        for callback in self._on_changed:
            try:
                callback(user_id, old, new)
            except Exception as e:
                logger.error(f"Erro em callback on_changed: {e}")
    
    async def _pubsub_listener(self):
        """Listener de Redis pub/sub para notificações em tempo real"""
        if not self.cache_manager:
            return
            
        try:
            # Assumindo que o cache_manager tem método pubsub
            # Implementação depende do Redis ou similar
            logger.info("Iniciando listener de pubsub...")
            
            while self._running:
                # Implementação específica do pubsub aqui
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Erro no pubsub listener: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do monitor"""
        return {
            "cache_size": len(self._status_cache),
            "active_users": sum(1 for s in self._status_cache.values() if s.enabled),
            "connected_users": len(self._connected_users),
            "last_full_refresh": self._last_full_refresh.isoformat() if self._last_full_refresh else None,
            "cache_ttl_seconds": self.cache_ttl,
            "full_refresh_interval": self.full_refresh_interval,
            "running": self._running
        }
    
    # ============================================================
    # Métodos de Gerenciamento de Conexão (movidos da Engine)
    # ============================================================
    
    def set_dependencies(self, connection_manager: Any, user_manager: Any):
        """Define dependências necessárias para gerenciar conexões"""
        self._connection_manager = connection_manager
        self._user_manager = user_manager
        logger.info("[AutotradeManager] Dependências definidas: connection_manager, user_manager")
    
    async def connect_user(self, user_id: str, status: AutotradeStatus) -> bool:
        """Conecta um usuário autotrade à corretora"""
        if not self._connection_manager or not self._user_manager:
            logger.warning(f"[AutotradeManager] Dependências não definidas para conectar {user_id}")
            return False
        
        if user_id in self._connected_users:
            logger.debug(f"[AutotradeManager] Usuário {user_id} já está conectado")
            return True
        
        try:
            # Obter SSID do usuário via UserManager (memória ou banco)
            is_demo = status.operator == "demo"
            ssid = await self._user_manager.get_user_ssid(user_id, is_demo)
            
            if not ssid:
                logger.warning(f"[AutotradeManager] Usuário {user_id} não tem SSID configurado")
                return False
            
            # Registrar usuário no UserManager (se não estiver registrado)
            if user_id not in self._user_manager.users:
                await self._user_manager.register_user(
                    user_id=user_id,
                    ssid=ssid,
                    is_demo=is_demo
                )
                logger.info(f"[AutotradeManager] Usuário {user_id} registrado no UserManager")
            
            # Conectar via ConnectionManager
            success, msg = await self._connection_manager.connect(
                user_id=user_id,
                ssid=ssid,
                is_demo=is_demo
            )
            
            if success:
                self._connected_users.add(user_id)
                logger.info(f"[AutotradeManager] Usuário {user_id} conectado com sucesso")
                
                # Notificar callbacks
                for callback in self._on_connected:
                    try:
                        callback(user_id)
                    except Exception as e:
                        logger.error(f"[AutotradeManager] Erro em callback on_connected: {e}")
                
                return True
            else:
                logger.warning(f"[AutotradeManager] Falha ao conectar {user_id}: {msg}")
                return False
                
        except Exception as e:
            logger.error(f"[AutotradeManager] Erro ao conectar {user_id}: {e}")
            return False
    
    async def disconnect_user(self, user_id: str) -> bool:
        """Desconecta um usuário autotrade da corretora"""
        if not self._connection_manager:
            return False
        
        try:
            success = await self._connection_manager.disconnect(user_id)
            
            if success and user_id in self._connected_users:
                self._connected_users.discard(user_id)
                logger.info(f"[AutotradeManager] Usuário {user_id} desconectado")
                
                # Remover do UserManager
                if self._user_manager and user_id in self._user_manager.users:
                    await self._user_manager.remove_user(user_id)
                    logger.info(f"[AutotradeManager] Usuário {user_id} removido do UserManager")
                
                # Notificar callbacks
                for callback in self._on_disconnected:
                    try:
                        callback(user_id)
                    except Exception as e:
                        logger.error(f"[AutotradeManager] Erro em callback on_disconnected: {e}")
                
                return True
            
            return success
            
        except Exception as e:
            logger.error(f"[AutotradeManager] Erro ao desconectar {user_id}: {e}")
            return False
    
    def is_user_connected(self, user_id: str) -> bool:
        """Verifica se um usuário está conectado"""
        return user_id in self._connected_users
    
    def get_connected_users(self) -> List[str]:
        """Retorna lista de usuários conectados"""
        return list(self._connected_users)
    
    def on_connected(self, callback: Callable[[str], None]):
        """Registra callback para quando usuário conecta"""
        self._on_connected.add(callback)
    
    def on_disconnected(self, callback: Callable[[str], None]):
        """Registra callback para quando usuário desconecta"""
        self._on_disconnected.add(callback)
    
    def remove_connection_callback(self, callback: Callable[[str], None]):
        """Remove callback de conexão"""
        self._on_connected.discard(callback)
        self._on_disconnected.discard(callback)
