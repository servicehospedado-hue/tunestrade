"""
Configurações do sistema
"""
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum
import os
from dotenv import load_dotenv

load_dotenv()


class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class NotificationProvider(Enum):
    FIREBASE = "firebase"
    ONESIGNAL = "onesignal"
    EXPO = "expo"


@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    name: str = "trading_db"
    user: str = "postgres"
    password: str = ""
    pool_size: int = 20
    max_overflow: int = 10

    @property
    def async_url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def admin_sync_url(self) -> str:
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/postgres"


@dataclass
class RedisConfig:
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    enabled: bool = False


@dataclass
class CacheConfig:
    max_size_mb: int = 512
    default_ttl: int = 60
    candles_ttl: int = 30
    indicators_ttl: int = 300


@dataclass
class TaskManagerConfig:
    max_workers: int = 100
    max_concurrent_tasks: int = 1000
    queue_size: int = 5000


@dataclass
class UserManagerConfig:
    max_users: int = 1000
    session_timeout: int = 1800
    inactive_cleanup_interval: int = 600


@dataclass
class SignalManagerConfig:
    max_signals_per_user: int = 100
    default_signal_ttl: int = 600
    cleanup_interval: int = 300


@dataclass
class ConnectionManagerConfig:
    max_connections: int = 1000
    heartbeat_interval: int = 20
    heartbeat_timeout: int = 30
    max_reconnects: int = 5
    reconnect_delay: int = 5
    reconnect_max_delay: int = 60
    reconnect_jitter: float = 0.3
    connection_timeout: int = 30
    ping_max_missed: int = 3
    cleanup_interval: int = 60
    stale_timeout: int = 300


@dataclass
class DataCollectorConfig:
    max_assets: int = 100
    min_payout: float = 70.0


@dataclass
class StrategyManagerConfig:
    max_strategies_per_user: int = 10


@dataclass
class SystemHealthConfig:
    check_interval: int = 30


@dataclass
class APIConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    reload: bool = False
    log_level: str = "info"
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    api_key_header: str = "X-API-Key"
    rate_limit_per_minute: int = 60


@dataclass
class Settings:
    """Configurações globais do sistema"""

    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)

    task_manager: TaskManagerConfig = field(default_factory=TaskManagerConfig)
    user_manager: UserManagerConfig = field(default_factory=UserManagerConfig)
    signal_manager: SignalManagerConfig = field(default_factory=SignalManagerConfig)
    connection_manager: ConnectionManagerConfig = field(default_factory=ConnectionManagerConfig)
    data_collector: DataCollectorConfig = field(default_factory=DataCollectorConfig)
    strategy_manager: StrategyManagerConfig = field(default_factory=StrategyManagerConfig)
    system_health: SystemHealthConfig = field(default_factory=SystemHealthConfig)
    api: APIConfig = field(default_factory=APIConfig)

    # Notificações Push
    notification_provider: NotificationProvider = NotificationProvider.FIREBASE
    firebase_credentials: str = ""
    onesignal_app_id: str = ""
    onesignal_api_key: str = ""
    expo_access_token: str = ""

    log_level: str = "INFO"
    log_format: str = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    @classmethod
    def from_env(cls) -> "Settings":
        """Cria configurações a partir de variáveis de ambiente"""
        settings = cls()

        # Ambiente
        env = os.getenv("ENVIRONMENT", "development").lower()
        settings.environment = Environment(env)
        settings.debug = os.getenv("DEBUG", "true").lower() == "true"

        # Database
        settings.database.host = os.getenv("DB_HOST", "localhost")
        settings.database.port = int(os.getenv("DB_PORT", "5432"))
        settings.database.name = os.getenv("DB_NAME", "trading_db")
        settings.database.user = os.getenv("DB_USER", "postgres")
        settings.database.password = os.getenv("DB_PASSWORD", "")

        # Redis
        settings.redis.host = os.getenv("REDIS_HOST", "localhost")
        settings.redis.port = int(os.getenv("REDIS_PORT", "6379"))
        settings.redis.enabled = os.getenv("REDIS_ENABLED", "false").lower() == "true"
        settings.redis.password = os.getenv("REDIS_PASSWORD", "") or None

        # API
        settings.api.host = os.getenv("API_HOST", "0.0.0.0")
        settings.api.port = int(os.getenv("API_PORT", "8000"))
        settings.api.log_level = os.getenv("LOG_LEVEL", "info")

        # Connection Manager
        settings.connection_manager.max_connections = int(os.getenv("CONNECTION_MAX", "1000"))
        settings.connection_manager.heartbeat_interval = int(os.getenv("CONNECTION_HEARTBEAT_INTERVAL", "20"))
        settings.connection_manager.max_reconnects = int(os.getenv("CONNECTION_MAX_RECONNECTS", "5"))
        settings.connection_manager.reconnect_delay = int(os.getenv("CONNECTION_RECONNECT_DELAY", "5"))
        settings.connection_manager.connection_timeout = int(os.getenv("CONNECTION_TIMEOUT", "30"))
        settings.connection_manager.ping_max_missed = int(os.getenv("CONNECTION_PING_MAX_MISSED", "3"))
        settings.connection_manager.cleanup_interval = int(os.getenv("CONNECTION_CLEANUP_INTERVAL", "60"))
        settings.connection_manager.stale_timeout = int(os.getenv("CONNECTION_STALE_TIMEOUT", "300"))

        # Data Collector
        settings.data_collector.max_assets = int(os.getenv("MONITORING_ACTIVES_QUANTIDADE", "100"))
        settings.data_collector.min_payout = float(os.getenv("MONITORING_ACTIVES_PAYOUT_MINIMO", "70.0"))

        # Notificações
        provider_str = os.getenv("NOTIFICATION_PROVIDER", "firebase").lower()
        if provider_str == "onesignal":
            settings.notification_provider = NotificationProvider.ONESIGNAL
        elif provider_str == "expo":
            settings.notification_provider = NotificationProvider.EXPO
        else:
            settings.notification_provider = NotificationProvider.FIREBASE

        settings.firebase_credentials = os.getenv("FIREBASE_CREDENTIALS", "")
        settings.onesignal_app_id = os.getenv("ONESIGNAL_APP_ID", "")
        settings.onesignal_api_key = os.getenv("ONESIGNAL_API_KEY", "")
        settings.expo_access_token = os.getenv("EXPO_ACCESS_TOKEN", "")

        return settings
