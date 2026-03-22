"""
Database Manager Avançado
Gerenciador sofisticado de PostgreSQL com connection pooling,
auto-criação de banco, operações em batch, cache de queries e retry mechanism.
"""
import asyncio
from typing import List, Dict, Any, Optional, Type, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
import logging
from enum import Enum

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, JSON, select, insert, update, delete, text
from sqlalchemy.pool import NullPool
from sqlalchemy import create_engine

from .models import Base, AccountMonitoring, DEFAULT_ACCOUNTS_MONITORING, User, AutotradeConfig, UserStrategy

# Tentar importar bcrypt para hash de senha
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    logger.warning("bcrypt não disponível - senhas não serão hasheadas")

# Tentar importar cache manager se disponível
try:
    from ..cache.manager import CacheManager
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False

logger = logging.getLogger("database")


class DatabaseError(Exception):
    """Exceção base para erros de banco de dados"""
    pass


class ConnectionError(DatabaseError):
    """Erro de conexão"""
    pass


class RetryExhaustedError(DatabaseError):
    """Tentativas esgotadas"""
    pass


@dataclass
class BatchOperation:
    """Representa uma operação em batch"""
    operation: str  # 'insert', 'update', 'delete'
    table: str
    data: List[Dict[str, Any]]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class QueryCacheEntry:
    """Entrada de cache para queries"""
    query_hash: str
    results: Any
    created_at: datetime = field(default_factory=datetime.now)
    ttl: int = 300  # segundos
    
    def is_expired(self) -> bool:
        return (datetime.now() - self.created_at).total_seconds() > self.ttl


class DatabaseManager:
    """
    Gerenciador avançado de banco de dados PostgreSQL
    
    Features:
    - Auto-criação do banco de dados a partir do .env
    - Auto-criação de tabelas (users, etc.)
    - Connection pooling (async)
    - Operações em batch (bulk insert/update/delete)
    - Cache de queries (integrado com CacheManager)
    - Retry mechanism com exponential backoff
    - Transaction management
    """
    
    def __init__(
        self,
        database_url: str,
        admin_url: Optional[str] = None,
        db_name: Optional[str] = None,
        cache_manager: Optional[Any] = None,
        pool_size: int = 20,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        enable_cache: bool = True,
        default_cache_ttl: int = 300,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        self.database_url = database_url
        self.admin_url = admin_url  # URL sync para o banco 'postgres' (admin)
        self.db_name = db_name  # Nome do banco a criar
        self.cache_manager = cache_manager
        self.enable_cache = enable_cache and CACHE_AVAILABLE
        self.default_cache_ttl = default_cache_ttl
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Engine e session factory
        self.engine = None
        self.session_factory = None
        
        # Pool de conexões config
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        
        # Batch operations
        self._batch_queue: List[BatchOperation] = []
        self._batch_size = 1000
        self._batch_flush_interval = 5  # segundos
        self._batch_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Query cache interno (fallback se CacheManager não disponível)
        self._query_cache: Dict[str, QueryCacheEntry] = {}
        
    def _ensure_database_exists(self):
        """
        Conecta ao banco 'postgres' (admin) e cria o banco de dados
        especificado em DB_NAME caso ele não exista.
        Usa conexão síncrona porque CREATE DATABASE não pode rodar em transação.
        """
        if not self.admin_url or not self.db_name:
            logger.warning("admin_url ou db_name não configurados — pulando auto-criação do banco")
            return
        
        logger.info(f"Verificando se o banco '{self.db_name}' existe...")
        
        try:
            # Engine síncrono apontando para 'postgres'
            admin_engine = create_engine(self.admin_url, isolation_level="AUTOCOMMIT")
            
            with admin_engine.connect() as conn:
                # Verificar se o banco já existe
                result = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                    {"dbname": self.db_name}
                )
                exists = result.scalar() is not None
                
                if not exists:
                    # Criar banco de dados
                    # Não podemos usar parâmetros em DDL, então sanitizamos manualmente
                    safe_name = self.db_name.replace('"', '""')
                    conn.execute(text(f'CREATE DATABASE "{safe_name}"'))
                    logger.info(f"[OK] Banco de dados '{self.db_name}' criado com sucesso!")
                else:
                    logger.info(f"[OK] Banco de dados '{self.db_name}' já existe")
                    
            admin_engine.dispose()
            
        except Exception as e:
            logger.error(f"[ERRO] Erro ao verificar/criar banco de dados: {e}")
            raise ConnectionError(f"Não foi possível criar o banco '{self.db_name}': {e}")
    
    async def _create_tables(self):
        """
        Cria todas as tabelas definidas nos ORM models (Base.metadata)
        se elas ainda não existirem.
        Também verifica e adiciona colunas faltantes em tabelas existentes.
        """
        logger.info("Criando tabelas no banco de dados...")
        
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            # Listar tabelas criadas
            table_names = list(Base.metadata.tables.keys())
            logger.info(f"[OK] Tabelas garantidas: {table_names}")
            
            # Verificar e adicionar colunas faltantes
            await self._ensure_columns_exist()
            
            # Migrar dados de autotrade_session_state para autotrade_config
            await self._migrate_session_state_data()
            
        except Exception as e:
            logger.error(f"[ERRO] Erro ao criar tabelas: {e}")
            raise ConnectionError(f"Não foi possível criar tabelas: {e}")
    
    async def _ensure_columns_exist(self):
        """
        Verifica e adiciona colunas faltantes em tabelas existentes.
        Resolve o problema de novas colunas em modelos que não são criadas automaticamente.
        Formato: (nome_coluna, tipo_sql, default_sql, nullable)
          - nullable=True  → ADD COLUMN col TYPE DEFAULT val
          - nullable=False → ADD COLUMN col TYPE NOT NULL DEFAULT val
        """
        required_columns = {
            "users": [
                ("role",            "VARCHAR(20)",  "'user'",  False),
                ("vip",             "VARCHAR(10)",  "'free'",  False),
                ("vip_data_active", "TIMESTAMPTZ",  "NULL",    True),
            ],
            "autotrade_config": [
                ("cooldown",              "VARCHAR(50)",   "'60'",    False),
                # Stop Loss / Stop Gain
                ("stop_loss_enabled",     "BOOLEAN",       "FALSE",   False),
                ("stop_loss_value",       "NUMERIC(10,2)", "NULL",    True),
                ("stop_gain_enabled",     "BOOLEAN",       "FALSE",   False),
                ("stop_gain_value",       "NUMERIC(10,2)", "NULL",    True),
                ("stop_soft_mode",        "BOOLEAN",       "FALSE",   False),
                # Stop por Sequência
                ("stop_win_seq_enabled",  "BOOLEAN",       "FALSE",   False),
                ("stop_win_seq",          "INTEGER",       "NULL",    True),
                ("stop_loss_seq_enabled", "BOOLEAN",       "FALSE",   False),
                ("stop_loss_seq",         "INTEGER",       "NULL",    True),
                ("stop_seq_soft_mode",    "BOOLEAN",       "FALSE",   False),
                # Stop Médio
                ("stop_medium_enabled",   "BOOLEAN",       "FALSE",   False),
                ("stop_medium_pct",       "NUMERIC(5,2)",  "50.00",   True),
                ("stop_medium_soft_mode", "BOOLEAN",       "FALSE",   False),
                # Redução Inteligente
                ("reduce_enabled",        "BOOLEAN",       "FALSE",   False),
                ("reduce_loss_trigger",   "INTEGER",       "3",       True),
                ("reduce_win_exit",       "INTEGER",       "2",       True),
                ("reduce_pct",            "NUMERIC(5,2)",  "50.00",   True),
                # Martingale
                ("martingale_enabled",    "BOOLEAN",       "FALSE",   False),
                ("martingale_levels",     "INTEGER",       "3",       True),
                ("martingale_multiplier", "NUMERIC(5,2)",  "2.00",    True),
                # Soros
                ("soros_enabled",         "BOOLEAN",       "FALSE",   False),
                ("soros_levels",          "INTEGER",       "3",       True),
                ("soros_pct",             "NUMERIC(5,2)",  "100.00",  True),
                # Estado de Sessão (consolidado)
                ("amount_current",        "NUMERIC(10,2)", "1.00",    False),
                ("consecutive_wins",      "INTEGER",       "0",       False),
                ("consecutive_losses",    "INTEGER",       "0",       False),
                ("martingale_level",      "INTEGER",       "0",       False),
                ("soros_level",           "INTEGER",       "0",       False),
                ("reduce_active",         "BOOLEAN",       "FALSE",   False),
                ("reduce_level",          "INTEGER",       "0",       False),
                ("session_peak_balance",  "NUMERIC(12,2)", "NULL",    True),
                ("session_profit",        "NUMERIC(12,2)", "0.00",    False),
                ("session_trades",        "INTEGER",       "0",       False),
                ("stop_triggered",        "BOOLEAN",       "FALSE",   False),
                ("stop_type",             "VARCHAR(50)",   "NULL",    True),
            ],
            "user_strategies": [
                ("description", "TEXT",    "''",   True),
                ("is_active",   "BOOLEAN", "FALSE", False),
                ("updated_at",  "TIMESTAMPTZ", "now()", False),
            ],
        }

        try:
            async with self.engine.begin() as conn:
                for table_name, columns in required_columns.items():
                    # Verificar se a tabela existe antes de tentar adicionar colunas
                    table_exists_result = await conn.execute(text(f"""
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = '{table_name}'
                    """))
                    if not table_exists_result.fetchone():
                        logger.debug(f"Tabela '{table_name}' não existe ainda — pulando verificação de colunas")
                        continue

                    for col_name, col_type, col_default, nullable in columns:
                        result = await conn.execute(text(f"""
                            SELECT column_name
                            FROM information_schema.columns
                            WHERE table_name = '{table_name}' AND column_name = '{col_name}'
                        """))

                        if not result.fetchone():
                            logger.info(f"➕ Adicionando coluna '{col_name}' à tabela {table_name}...")
                            if nullable:
                                await conn.execute(text(f"""
                                    ALTER TABLE {table_name}
                                    ADD COLUMN {col_name} {col_type} DEFAULT {col_default}
                                """))
                            else:
                                await conn.execute(text(f"""
                                    ALTER TABLE {table_name}
                                    ADD COLUMN {col_name} {col_type} NOT NULL DEFAULT {col_default}
                                """))
                            logger.info(f"[OK] Coluna '{col_name}' adicionada a tabela {table_name}")

        except Exception as e:
            logger.warning(f"[WARN] Erro ao verificar/adicionar colunas: {e}")

    async def _migrate_session_state_data(self):
        """
        Migra dados de autotrade_session_state para autotrade_config.
        Após migração, remove a tabela autotrade_session_state.
        """
        try:
            async with self.engine.begin() as conn:
                # Verificar se a tabela autotrade_session_state existe
                table_exists_result = await conn.execute(text("""
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'autotrade_session_state'
                """))
                
                if not table_exists_result.fetchone():
                    logger.info("[OK] Tabela autotrade_session_state nao existe -- migracao nao necessaria")
                    return
                
                logger.info("[MIGR] Migrando dados de autotrade_session_state para autotrade_config...")
                
                # Migrar dados
                await conn.execute(text("""
                    UPDATE autotrade_config ac
                    SET 
                        amount_current = ass.amount_current,
                        consecutive_wins = ass.consecutive_wins,
                        consecutive_losses = ass.consecutive_losses,
                        martingale_level = ass.martingale_level,
                        soros_level = ass.soros_level,
                        reduce_active = ass.reduce_active,
                        reduce_level = ass.reduce_level,
                        session_peak_balance = ass.session_peak_balance,
                        session_profit = ass.session_profit,
                        session_trades = ass.session_trades,
                        stop_triggered = ass.stop_triggered,
                        stop_type = ass.stop_type
                    FROM autotrade_session_state ass
                    WHERE ac.user_id = ass.user_id
                """))
                
                logger.info("[OK] Dados migrados com sucesso")
                
                # Remover tabela antiga
                await conn.execute(text("DROP TABLE IF EXISTS autotrade_session_state CASCADE"))
                logger.info("[OK] Tabela autotrade_session_state removida")
                
        except Exception as e:
            logger.warning(f"[WARN] Erro ao migrar dados de sessao: {e}")

    async def _seed_default_data(self):
        """
        Insere dados padrão:
        - Contas de monitoramento (payout, actives)
        - Usuário admin padrão (se não existir)
        """
        try:
            async with self.get_session() as session:
                # 1) Seed accounts_monitoring
                result = await session.execute(select(AccountMonitoring).limit(1))
                existing_account = result.scalars().first()
                
                if not existing_account:
                    for account_data in DEFAULT_ACCOUNTS_MONITORING:
                        account = AccountMonitoring(**account_data)
                        session.add(account)
                    logger.info(f"[OK] Seed: {len(DEFAULT_ACCOUNTS_MONITORING)} contas inseridas em accounts_monitoring")
                else:
                    logger.info("[OK] accounts_monitoring já possui dados")
                
                # 2) Seed usuário admin padrão
                result = await session.execute(
                    select(User).where(User.email == "admin@gmail.com")
                )
                existing_admin = result.scalars().first()
                
                if not existing_admin:
                    # Hash da senha "leandro1228"
                    password_hash = self._hash_password("leandro1228")
                    
                    admin_user = User(
                        nome="Administrador",
                        email="admin@gmail.com",
                        senha=password_hash,
                        role="admin",
                        operator="demo",
                        vip="free",
                        vip_data_active=datetime.now(timezone.utc)
                    )
                    session.add(admin_user)
                    await session.flush()  # Para obter o ID do admin
                    
                    # Criar config de autotrade para admin com estratégia scalping
                    admin_config = AutotradeConfig(
                        user_id=admin_user.id,
                        autotrade=1,  # Ligado por padrão
                        amount=1.00,
                        strategy_name="Scalping5s"  # Estratégia Scalping
                    )
                    session.add(admin_config)
                    
                    logger.info("[OK] Seed: Usuário admin criado (admin@gmail.com / leandro1228) com autotrade Scalping5s")
                else:
                    # Verificar se admin já tem config de autotrade
                    result = await session.execute(
                        select(AutotradeConfig).where(
                            AutotradeConfig.user_id == existing_admin.id
                        )
                    )
                    existing_config = result.scalars().first()
                    
                    if not existing_config:
                        # Criar config de autotrade para admin existente
                        admin_config = AutotradeConfig(
                            user_id=existing_admin.id,
                            autotrade=1,
                            amount=1.00,
                            strategy_name="Scalping5s"
                        )
                        session.add(admin_config)
                        logger.info("[OK] Config de autotrade Scalping5s criada para admin existente")
                    else:
                        logger.info(f"[OK] Usuário admin já existe com autotrade '{existing_config.strategy_name}' — sem alterações")
                    
        except Exception as e:
            logger.error(f"Erro ao inserir dados padrão: {e}")
    
    def _hash_password(self, password: str) -> str:
        """Gera hash seguro da senha usando bcrypt"""
        if BCRYPT_AVAILABLE:
            salt = bcrypt.gensalt(rounds=12)
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
            return hashed.decode('utf-8')
        else:
            # Fallback simples (não recomendado para produção)
            import hashlib
            return hashlib.sha256(password.encode()).hexdigest()

    async def start(self):
        """Inicializa o gerenciador de banco de dados"""
        logger.info("Iniciando DatabaseManager...")
        
        try:
            # 1) Garantir que o banco de dados existe (sync, admin)
            self._ensure_database_exists()
            
            # 2) Criar engine async para o banco de dados da aplicação
            self.engine = create_async_engine(
                self.database_url,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=self.pool_timeout,
                pool_pre_ping=True,
                echo=False
            )
            
            # Session factory
            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # 3) Criar tabelas (users, accounts_monitoring, etc.)
            await self._create_tables()
            
            # 4) Seed: inserir dados padrão se tabelas estiverem vazias
            await self._seed_default_data()
            
            # 5) Inicializar DAOs dependentes
            from .user_strategy_dao import init_user_strategy_dao
            init_user_strategy_dao(self)
            
            # Iniciar batch processor
            self._running = True
            self._batch_task = asyncio.create_task(self._batch_processor())
            
            # Testar conexão
            async with self.get_session() as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar()
            
            logger.info(f"[OK] DatabaseManager conectado | Pool: {self.pool_size}/{self.max_overflow}")
            
        except Exception as e:
            logger.error(f"[ERRO] Falha ao iniciar DatabaseManager: {e}")
            raise ConnectionError(f"Não foi possível conectar ao banco: {e}")
    
    async def stop(self):
        """Para o gerenciador e fecha conexões"""
        logger.info("Parando DatabaseManager...")
        
        self._running = False
        
        # Flush batch pendente
        if self._batch_queue:
            try:
                await self._flush_batch()
            except Exception as e:
                logger.warning(f"Erro ao flush batch final: {e}")
        
        # Cancelar batch processor
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"Erro ao cancelar batch task: {e}")
        
        # Fechar engine com tratamento de erro
        if self.engine:
            try:
                # Fechar conexões do pool primeiro
                pool = self.engine.pool
                if hasattr(pool, 'close'):
                    try:
                        await pool.close()
                    except Exception:
                        pass
                
                # Dispose do engine com timeout
                await asyncio.wait_for(self.engine.dispose(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout ao fechar engine, continuando...")
            except Exception as e:
                logger.warning(f"Erro ao fechar engine (não crítico): {e}")
            finally:
                self.engine = None
        
        # Limpar cache
        self._query_cache.clear()
        
        logger.info("DatabaseManager parado")
    
    @asynccontextmanager
    async def get_session(self):
        """Context manager para obter sessão do pool"""
        if not self.session_factory:
            raise ConnectionError("DatabaseManager não iniciado")
        
        session = self.session_factory()
        try:
            logger.debug("[DB] Sessão aberta do pool")
            yield session
            await session.commit()
            logger.debug("[DB] Sessão commitada")
        except Exception as e:
            await session.rollback()
            logger.error(f"[DB] Sessão rollback: {e}")
            raise e
        finally:
            await session.close()
            logger.debug("[DB] Sessão devolvida ao pool")
    
    async def execute_with_retry(
        self,
        operation: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Executa operação com retry mechanism"""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"[DB] Executando operação (tentativa {attempt + 1})")
                result = await operation(*args, **kwargs)
                logger.debug(f"[DB] Operação concluída com sucesso")
                return result
            except Exception as e:
                last_error = e
                logger.warning(f"[DB] Tentativa {attempt + 1} falhou: {e}")
                
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.info(f"[DB] Aguardando {delay}s antes de retry...")
                    await asyncio.sleep(delay)
        
        logger.error(f"[DB] Todas as {self.max_retries} tentativas falharam")
        raise RetryExhaustedError(f"Operação falhou após {self.max_retries} tentativas: {last_error}")
    
    # ==================== BATCH OPERATIONS ====================
    
    async def add_to_batch(
        self,
        operation: str,
        table: str,
        data: List[Dict[str, Any]]
    ):
        """Adiciona operação à fila de batch"""
        batch_op = BatchOperation(
            operation=operation,
            table=table,
            data=data if isinstance(data, list) else [data]
        )
        
        self._batch_queue.append(batch_op)
        
        if len(self._batch_queue) >= self._batch_size:
            await self._flush_batch()
    
    async def _batch_processor(self):
        """Processa operações em batch periodicamente"""
        while self._running:
            try:
                await asyncio.sleep(self._batch_flush_interval)
                
                if self._batch_queue:
                    await self._flush_batch()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no batch processor: {e}")
    
    async def _flush_batch(self):
        """Executa todas as operações pendentes em batch"""
        if not self._batch_queue:
            return
        
        batch_to_process = self._batch_queue[:]
        self._batch_queue.clear()
        
        logger.info(f"[DB BATCH] Processando {len(batch_to_process)} operações")
        
        try:
            async with self.get_session() as session:
                for operation in batch_to_process:
                    if operation.operation == 'insert':
                        await self._bulk_insert(session, operation.table, operation.data)
                    elif operation.operation == 'update':
                        await self._bulk_update(session, operation.table, operation.data)
                    elif operation.operation == 'delete':
                        await self._bulk_delete(session, operation.table, operation.data)
                        
            logger.info(f"[DB BATCH] Concluído: {len(batch_to_process)} operações")
            
        except Exception as e:
            logger.error(f"[DB BATCH] Erro: {e}")
            self._batch_queue.extend(batch_to_process)
    
    async def _bulk_insert(
        self,
        session: AsyncSession,
        table: str,
        data: List[Dict[str, Any]]
    ):
        """Insert em lote"""
        if not data:
            return
        logger.debug(f"Bulk insert em {table}: {len(data)} registros")
        
    async def _bulk_update(
        self,
        session: AsyncSession,
        table: str,
        data: List[Dict[str, Any]]
    ):
        """Update em lote"""
        if not data:
            return
        logger.debug(f"Bulk update em {table}: {len(data)} registros")
        
    async def _bulk_delete(
        self,
        session: AsyncSession,
        table: str,
        data: List[Dict[str, Any]]
    ):
        """Delete em lote"""
        if not data:
            return
        logger.debug(f"Bulk delete em {table}: {len(data)} registros")
    
    async def force_flush_batch(self):
        """Força flush imediato do batch"""
        await self._flush_batch()
    
    # ==================== QUERY CACHE ====================
    
    def _generate_query_hash(self, query: str, params: tuple = None) -> str:
        """Gera hash única para uma query"""
        import hashlib
        content = f"{query}:{str(params)}"
        return hashlib.md5(content.encode()).hexdigest()
    
    async def execute_cached(
        self,
        query: str,
        params: Optional[tuple] = None,
        cache_ttl: Optional[int] = None,
        use_cache: bool = True
    ) -> Any:
        """Executa query com cache"""
        
        if not use_cache or not self.enable_cache:
            return await self._execute_raw(query, params)
        
        query_hash = self._generate_query_hash(query, params)
        
        # Verificar cache externo (CacheManager)
        if self.cache_manager and CACHE_AVAILABLE:
            cached = await self.cache_manager.get(f"db_query:{query_hash}")
            if cached:
                logger.debug(f"Cache hit para query: {query_hash[:8]}...")
                return cached
        
        # Verificar cache interno
        if query_hash in self._query_cache:
            entry = self._query_cache[query_hash]
            if not entry.is_expired():
                logger.debug(f"Cache interno hit para query: {query_hash[:8]}...")
                return entry.results
            else:
                del self._query_cache[query_hash]
        
        # Executar query
        results = await self._execute_raw(query, params)
        
        # Armazenar em cache
        ttl = cache_ttl or self.default_cache_ttl
        
        if self.cache_manager and CACHE_AVAILABLE:
            await self.cache_manager.set(f"db_query:{query_hash}", results, ttl)
        else:
            self._query_cache[query_hash] = QueryCacheEntry(
                query_hash=query_hash,
                results=results,
                ttl=ttl
            )
        
        return results
    
    async def _execute_raw(self, query: str, params: Optional[tuple] = None) -> Any:
        """Executa query raw no banco"""
        logger.debug(f"[DB QUERY] {query[:100]}... | params: {params}")
        async with self.get_session() as session:
            result = await session.execute(text(query), params)
            rows = result.fetchall()
            logger.debug(f"[DB QUERY] Retornou {len(rows)} linhas")
            return rows
    
    async def invalidate_cache(self, pattern: Optional[str] = None):
        """Invalida cache de queries"""
        if pattern:
            keys_to_remove = [
                k for k in self._query_cache.keys()
                if pattern in k
            ]
            for key in keys_to_remove:
                del self._query_cache[key]
                
            if self.cache_manager and CACHE_AVAILABLE:
                pass
        else:
            self._query_cache.clear()
            
            if self.cache_manager and CACHE_AVAILABLE:
                await self.cache_manager.clear()
    
    # ==================== UTILITIES ====================
    
    async def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do gerenciador"""
        stats = {
            "database_url": self.database_url.split('@')[-1] if '@' in self.database_url else "hidden",
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "batch_queue_size": len(self._batch_queue),
            "cache_enabled": self.enable_cache,
            "query_cache_size": len(self._query_cache),
            "max_retries": self.max_retries,
        }
        
        # Estatísticas do pool
        if self.engine:
            pool = self.engine.pool
            stats["pool"] = {
                "size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
            }
        
        return stats
    
    async def health_check(self) -> bool:
        """Verifica saúde da conexão"""
        try:
            async with self.get_session() as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar()
            logger.debug("[DB] Health check OK")
            return True
        except Exception as e:
            logger.error(f"[DB] Health check falhou: {e}")
            return False


# Instância global (será inicializada posteriormente)
db_manager: Optional[DatabaseManager] = None


async def init_database_manager(
    database_url: str,
    admin_url: Optional[str] = None,
    db_name: Optional[str] = None,
    cache_manager: Optional[Any] = None,
    **kwargs
) -> DatabaseManager:
    """Inicializa o gerenciador de banco de dados global"""
    global db_manager
    db_manager = DatabaseManager(
        database_url,
        admin_url=admin_url,
        db_name=db_name,
        cache_manager=cache_manager,
        **kwargs
    )
    await db_manager.start()
    return db_manager
