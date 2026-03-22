"""
Gerenciador de Usuários
Gerencia sessões, configurações e limites de múltiplos usuários
Integra com banco de dados para persistência
"""
import asyncio
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
from ..managers.log_manager import get_manager_logger

if TYPE_CHECKING:
    from ..database.database_manager import DatabaseManager

logger = get_manager_logger("user_manager")


class UserStatus(Enum):
    """Status do usuário"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


@dataclass
class UserSession:
    """Sessão de um usuário"""
    user_id: str
    ssid: str
    is_demo: bool = True
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    status: UserStatus = UserStatus.ACTIVE
    client: Any = None  # Referência ao cliente PocketOption


@dataclass
class UserLimits:
    """Limites de um usuário"""
    max_indicators: int = 10
    max_strategies: int = 5
    max_concurrent_tasks: int = 20
    max_signals_per_day: int = 100
    api_calls_per_minute: int = 60


@dataclass
class UserStats:
    """Estatísticas do usuário"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_signals: int = 0
    total_tasks: int = 0
    last_trade_at: Optional[datetime] = None
    daily_pnl: float = 0.0


class UserManager:
    """
    Gerenciador central de usuários
    Suporta múltiplos usuários simultâneos com isolamento completo
    Integra com banco de dados para persistência
    """
    
    def __init__(self, max_users: int = 1000, db_manager: Optional["DatabaseManager"] = None):
        self.max_users = max_users
        self.db_manager = db_manager
        self.connection_manager: Optional[Any] = None  # Injetado após inicialização
        self.users: Dict[str, UserSession] = {}
        self.user_limits: Dict[str, UserLimits] = {}
        self.user_stats: Dict[str, UserStats] = {}
        self.user_configs: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        
    def set_db_manager(self, db_manager: "DatabaseManager"):
        """Define o DatabaseManager para integração com banco"""
        self.db_manager = db_manager
        logger.info("[UserManager] DatabaseManager configurado")

    def set_connection_manager(self, connection_manager: Any):
        """Injeta o ConnectionManager para consultar sessões WebSocket reais"""
        self.connection_manager = connection_manager
        logger.info("[UserManager] ConnectionManager configurado")
        
    async def start(self):
        """Inicia o gerenciador de usuários"""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_inactive_users())
        logger.info(f"UserManager iniciado (max: {self.max_users} usuários)")
        
    async def stop(self):
        """Para o gerenciador de usuários"""
        self._running = False
        
        # Desconectar todos os usuários
        for user_id in list(self.users.keys()):
            await self.disconnect_user(user_id)
            
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("UserManager parado")
        
    async def register_user(self, user_id: str, ssid: str, is_demo: bool = True,
                           limits: Optional[UserLimits] = None) -> bool:
        """Registra um novo usuário no sistema"""
        async with self._lock:
            if len(self.users) >= self.max_users:
                logger.error(f"Limite de usuários atingido: {self.max_users}")
                return False
                
            if user_id in self.users:
                logger.warning(f"Usuário {user_id} já existe")
                return False
                
            # Criar sessão
            session = UserSession(
                user_id=user_id,
                ssid=ssid,
                is_demo=is_demo
            )
            
            self.users[user_id] = session
            self.user_limits[user_id] = limits or UserLimits()
            self.user_stats[user_id] = UserStats()
            self.user_configs[user_id] = {}
            
            logger.info(f"Usuário {user_id} registrado com sucesso")
            return True
            
    async def connect_user(self, user_id: str) -> bool:
        """Conecta um usuário à API PocketOption"""
        if user_id not in self.users:
            logger.error(f"Usuário {user_id} não encontrado")
            return False
            
        user = self.users[user_id]
        
        try:
            from pocketoptionapi import AsyncPocketOptionClient
            client = AsyncPocketOptionClient(
                ssid=user.ssid,
                is_demo=user.is_demo,
                enable_logging=False
            )
            
            connected = await client.connect()
            if connected:
                user.client = client
                user.status = UserStatus.ACTIVE
                user.last_activity = datetime.now()
                logger.info(f"Usuário {user_id} conectado")
                return True
            else:
                logger.error(f"Falha ao conectar usuário {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao conectar usuário {user_id}: {e}")
            return False
            
    async def disconnect_user(self, user_id: str):
        """Desconecta um usuário"""
        if user_id in self.users:
            user = self.users[user_id]
            if user.client:
                try:
                    await user.client.disconnect()
                except Exception as e:
                    logger.error(f"Erro ao desconectar usuário {user_id}: {e}")
                    
            user.status = UserStatus.INACTIVE
            user.client = None
            logger.info(f"Usuário {user_id} desconectado")
            
    async def remove_user(self, user_id: str):
        """Remove um usuário do sistema"""
        async with self._lock:
            await self.disconnect_user(user_id)
            
            self.users.pop(user_id, None)
            self.user_limits.pop(user_id, None)
            self.user_stats.pop(user_id, None)
            self.user_configs.pop(user_id, None)
            
            logger.info(f"Usuário {user_id} removido")
            
    def get_user(self, user_id: str) -> Optional[UserSession]:
        """Obtém sessão de um usuário (apenas memória)"""
        return self.users.get(user_id)
    
    async def get_user_async(self, user_id: str) -> Optional[UserSession]:
        """Obtém sessão de um usuário (memória ou banco)"""
        # Primeiro verifica se está em memória
        if user_id in self.users:
            return self.users[user_id]
        
        # Se não, busca do banco de dados
        if self.db_manager:
            try:
                async with self.db_manager.get_session() as session:
                    from sqlalchemy import select
                    from ..database.models import User
                    result = await session.execute(
                        select(User).where(User.id == user_id)
                    )
                    db_user = result.scalar_one_or_none()
                    if db_user:
                        # Retorna sessão temporária (não registra em memória)
                        return UserSession(
                            user_id=db_user.id,
                            ssid=db_user.ssid_demo or db_user.ssid_real or "",
                            is_demo=True  # Default para demo
                        )
            except Exception as e:
                logger.error(f"Erro ao buscar usuário {user_id} do banco: {e}")
        
        return None
    
    async def get_user_ssid(self, user_id: str, is_demo: bool = True) -> Optional[str]:
        """Obtém SSID de um usuário (memória ou banco)"""
        # Primeiro verifica se está em memória
        if user_id in self.users:
            return self.users[user_id].ssid
        
        # Se não, busca do banco de dados
        if self.db_manager:
            try:
                async with self.db_manager.get_session() as session:
                    from sqlalchemy import select
                    from ..database.models import User
                    result = await session.execute(
                        select(User).where(User.id == user_id)
                    )
                    db_user = result.scalar_one_or_none()
                    if db_user:
                        return db_user.ssid_demo if is_demo else db_user.ssid_real
            except Exception as e:
                logger.error(f"Erro ao buscar SSID do usuário {user_id}: {e}")
        
        return None
        
    def get_user_client(self, user_id: str) -> Optional[Any]:
        """Obtém cliente API de um usuário"""
        user = self.users.get(user_id)
        return user.client if user else None
    
    async def on_user_login(self, user_id: str, email: str, is_local: bool = False):
        """Callback chamado quando usuário faz login (via auth_routes)"""
        logger.info(
            f"[UserManager] Login detectado | User: {email} | ID: {user_id} | "
            f"Modo: {'local' if is_local else 'postgres'}"
        )
        
        # Atualizar last_activity se usuário existe em memória
        if user_id in self.users:
            self.users[user_id].last_activity = datetime.now()
            logger.debug(f"[UserManager] Last activity atualizado para {user_id}")
        
        # Contar sessões WebSocket reais via ConnectionManager
        if self.connection_manager:
            from .connection_manager import ConnectionState
            ws_active = sum(
                1 for conn in self.connection_manager.connections.values()
                if conn.state == ConnectionState.CONNECTED
                and "monitoring" not in conn.user_id.lower()
                and "payout" not in conn.user_id.lower()
            )
            logger.info(f"[UserManager] Sessões WebSocket ativas (usuários): {ws_active}")
        else:
            active_count = len([u for u in self.users.values() if u.status == UserStatus.ACTIVE])
            logger.info(f"[UserManager] Sessões ativas: {active_count}")
        
    def get_user_limits(self, user_id: str) -> UserLimits:
        """Obtém limites de um usuário"""
        return self.user_limits.get(user_id, UserLimits())
        
    def get_user_stats(self, user_id: str) -> UserStats:
        """Obtém estatísticas de um usuário"""
        return self.user_stats.get(user_id, UserStats())
        
    async def update_user_config(self, user_id: str, config: Dict[str, Any]):
        """Atualiza configuração de um usuário"""
        if user_id in self.user_configs:
            self.user_configs[user_id].update(config)
            logger.debug(f"Configuração atualizada para usuário {user_id}")
            
    def get_user_config(self, user_id: str) -> Dict[str, Any]:
        """Obtém configuração de um usuário"""
        return self.user_configs.get(user_id, {})
        
    async def on_strategy_activated(self, user_id: str, strategy_name: str, enabled: bool = True):
        """Callback chamado quando usuário ativa/desativa uma estratégia"""
        status = "ATIVADA" if enabled else "DESATIVADA"
        logger.info(
            f"[STRATEGY] Estratégia {status} | User: {user_id} | "
            f"Strategy: {strategy_name}"
        )
        
        # Atualizar config do usuário se existir
        if user_id in self.user_configs:
            self.user_configs[user_id]['strategy_name'] = strategy_name
            self.user_configs[user_id]['autotrade_enabled'] = enabled
            self.user_configs[user_id]['strategy_activated_at'] = datetime.now().isoformat()
            logger.debug(f"[STRATEGY] Config atualizada para user {user_id}")
        
        # Atualizar estatísticas
        if user_id in self.user_stats:
            self.user_stats[user_id].last_activity = datetime.now()
            
    async def on_strategy_config_updated(self, user_id: str, config: Dict[str, Any]):
        """Callback chamado quando configuração da estratégia é atualizada"""
        logger.info(
            f"[STRATEGY CONFIG] Atualizada | User: {user_id} | "
            f"Config: {config}"
        )
        
    async def update_user_stats(self, user_id: str, **kwargs):
        """Atualiza estatísticas de um usuário"""
        if user_id in self.user_stats:
            stats = self.user_stats[user_id]
            for key, value in kwargs.items():
                if hasattr(stats, key):
                    setattr(stats, key, value)
                    
    def check_user_limits(self, user_id: str, limit_type: str, current_value: int) -> bool:
        """Verifica se usuário está dentro dos limites"""
        limits = self.get_user_limits(user_id)
        limit_value = getattr(limits, limit_type, 0)
        return current_value < limit_value
        
    def get_active_users(self) -> List[str]:
        """Retorna lista de usuários ativos"""
        return [
            uid for uid, user in self.users.items()
            if user.status == UserStatus.ACTIVE
        ]
        
    async def _cleanup_inactive_users(self):
        """Remove usuários inativos periodicamente"""
        while self._running:
            try:
                await asyncio.sleep(600)  # Verificar a cada 10 minutos
                
                now = datetime.now()
                inactive_users = []
                
                for user_id, user in self.users.items():
                    # Desconectar usuários inativos por mais de 30 minutos
                    if user.status == UserStatus.ACTIVE:
                        elapsed = (now - user.last_activity).total_seconds()
                        if elapsed > 1800:  # 30 minutos
                            inactive_users.append(user_id)
                            
                for user_id in inactive_users:
                    await self.disconnect_user(user_id)
                    logger.info(f"Usuário {user_id} desconectado por inatividade")
                    
            except Exception as e:
                logger.error(f"Erro na limpeza de usuários: {e}")
                
    def get_stats(self) -> Dict:
        """Retorna estatísticas gerais"""
        total = len(self.users)
        active = sum(1 for u in self.users.values() if u.status == UserStatus.ACTIVE)
        inactive = sum(1 for u in self.users.values() if u.status == UserStatus.INACTIVE)
        
        return {
            "total_users": total,
            "active_users": active,
            "inactive_users": inactive,
            "max_users": self.max_users,
            "usage_percentage": (total / self.max_users) * 100
        }
