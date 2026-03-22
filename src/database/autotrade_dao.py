"""
AutotradeDAO - Data Access Object para configurações de autotrade
Gerencia operações CRUD para configurações de autotrade no banco de dados
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
import logging
import uuid

from sqlalchemy import select, update, delete

from .models import AutotradeConfig, User

logger = logging.getLogger("autotrade_dao")


class AutotradeDAO:
    """
    DAO para gerenciar configurações de autotrade.
    
    Fornece métodos para:
    - Criar configurações de autotrade
    - Buscar configurações por usuário
    - Atualizar configurações
    - Remover configurações
    - Listar todas as configurações ativas
    """
    
    def __init__(self, db_manager):
        """
        Inicializa o DAO com o DatabaseManager
        
        Args:
            db_manager: Instância do DatabaseManager
        """
        self.db_manager = db_manager
    
    async def create_config(
        self,
        user_id: str,
        autotrade: int = 0,
        amount: float = 1.00,
        strategy_name: str = "Scalping5s",
        cooldown: str = "60",
        execute: str = "signal"
    ) -> Optional[AutotradeConfig]:
        """
        Cria uma nova configuração de autotrade para um usuário.
        
        Args:
            user_id: ID do usuário
            autotrade: 1 = ligado, 0 = desligado
            amount: Valor da operação em USD
            strategy_name: Nome da estratégia (padrão: Scalping5s)
            cooldown: Tempo entre trades - '60' (fixo) ou '60-120' (intervalo)
            execute: Modo de execução - 'signal' (imediato) ou 'oncandle' (próxima vela)
            
        Returns:
            AutotradeConfig criada ou None se erro
        """
        try:
            async with self.db_manager.get_session() as session:
                # Verificar se o usuário existe (evita ForeignKeyViolationError)
                user_result = await session.execute(
                    select(User).where(User.id == uuid.UUID(user_id))
                )
                user = user_result.scalars().first()
                if not user:
                    logger.warning(f"Usuário {user_id} não encontrado - não é possível criar config de autotrade")
                    return None
                
                # Verificar se já existe config para o usuário
                result = await session.execute(
                    select(AutotradeConfig).where(
                        AutotradeConfig.user_id == uuid.UUID(user_id)
                    )
                )
                existing = result.scalars().first()
                
                if existing:
                    logger.warning(f"Config de autotrade já existe para usuário {user_id}")
                    return existing
                
                # Criar nova config
                config = AutotradeConfig(
                    user_id=uuid.UUID(user_id),
                    autotrade=autotrade,
                    amount=Decimal(str(amount)),
                    strategy_name=strategy_name,
                    cooldown=cooldown,
                    execute=execute
                )
                
                session.add(config)
                await session.flush()
                
                logger.info(
                    f"[AUTOTRADE DAO] Config criada para user {user_id}: "
                    f"strategy={strategy_name}, amount={amount}, autotrade={autotrade}, cooldown={cooldown}, execute={execute}"
                )
                
                return config
                
        except Exception as e:
            logger.error(f"Erro ao criar config de autotrade: {e}")
            return None
    
    async def get_config_by_user(self, user_id: str) -> Optional[AutotradeConfig]:
        """
        Busca configuração de autotrade por ID do usuário.
        
        Args:
            user_id: ID do usuário
            
        Returns:
            AutotradeConfig ou None se não encontrada
        """
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(AutotradeConfig).where(
                        AutotradeConfig.user_id == uuid.UUID(user_id)
                    )
                )
                return result.scalars().first()
                
        except Exception as e:
            logger.error(f"Erro ao buscar config de autotrade: {e}")
            return None
    
    async def update_config(
        self,
        user_id: str,
        autotrade: Optional[int] = None,
        amount: Optional[float] = None,
        strategy_name: Optional[str] = None,
        cooldown: Optional[str] = None,
        execute: Optional[str] = None,
        # Stop Loss / Gain
        stop_loss_enabled: Optional[bool] = None,
        stop_loss_value: Optional[float] = None,
        stop_gain_enabled: Optional[bool] = None,
        stop_gain_value: Optional[float] = None,
        stop_soft_mode: Optional[bool] = None,
        # Stop por Sequência
        stop_win_seq_enabled: Optional[bool] = None,
        stop_win_seq: Optional[int] = None,
        stop_loss_seq_enabled: Optional[bool] = None,
        stop_loss_seq: Optional[int] = None,
        stop_seq_soft_mode: Optional[bool] = None,
        # Stop Médio
        stop_medium_enabled: Optional[bool] = None,
        stop_medium_pct: Optional[float] = None,
        stop_medium_soft_mode: Optional[bool] = None,
        # Redução Inteligente
        reduce_enabled: Optional[bool] = None,
        reduce_loss_trigger: Optional[int] = None,
        reduce_win_exit: Optional[int] = None,
        reduce_pct: Optional[float] = None,
        # Martingale
        martingale_enabled: Optional[bool] = None,
        martingale_levels: Optional[int] = None,
        martingale_multiplier: Optional[float] = None,
        # Soros
        soros_enabled: Optional[bool] = None,
        soros_levels: Optional[int] = None,
        soros_pct: Optional[float] = None,
    ) -> bool:
        """Atualiza configuração de autotrade do usuário (todos os campos)."""
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(AutotradeConfig).where(
                        AutotradeConfig.user_id == uuid.UUID(user_id)
                    )
                )
                config = result.scalars().first()
                if not config:
                    logger.warning(f"Config de autotrade não encontrada para user {user_id}")
                    return False

                # Campos básicos
                if autotrade is not None:       config.autotrade = autotrade
                if amount is not None:          config.amount = Decimal(str(amount))
                if strategy_name is not None:   config.strategy_name = strategy_name
                if cooldown is not None:        config.cooldown = cooldown
                if execute is not None:         config.execute = execute
                # Stops
                if stop_loss_enabled is not None:   config.stop_loss_enabled = stop_loss_enabled
                if stop_loss_value is not None:     config.stop_loss_value = Decimal(str(stop_loss_value))
                if stop_gain_enabled is not None:   config.stop_gain_enabled = stop_gain_enabled
                if stop_gain_value is not None:     config.stop_gain_value = Decimal(str(stop_gain_value))
                if stop_soft_mode is not None:      config.stop_soft_mode = stop_soft_mode
                if stop_win_seq_enabled is not None:  config.stop_win_seq_enabled = stop_win_seq_enabled
                if stop_win_seq is not None:          config.stop_win_seq = stop_win_seq
                if stop_loss_seq_enabled is not None: config.stop_loss_seq_enabled = stop_loss_seq_enabled
                if stop_loss_seq is not None:         config.stop_loss_seq = stop_loss_seq
                if stop_seq_soft_mode is not None:    config.stop_seq_soft_mode = stop_seq_soft_mode
                if stop_medium_enabled is not None:   config.stop_medium_enabled = stop_medium_enabled
                if stop_medium_pct is not None:       config.stop_medium_pct = Decimal(str(stop_medium_pct))
                if stop_medium_soft_mode is not None: config.stop_medium_soft_mode = stop_medium_soft_mode
                # Redução
                if reduce_enabled is not None:      config.reduce_enabled = reduce_enabled
                if reduce_loss_trigger is not None: config.reduce_loss_trigger = reduce_loss_trigger
                if reduce_win_exit is not None:     config.reduce_win_exit = reduce_win_exit
                if reduce_pct is not None:          config.reduce_pct = Decimal(str(reduce_pct))
                # Martingale
                if martingale_enabled is not None:    config.martingale_enabled = martingale_enabled
                if martingale_levels is not None:     config.martingale_levels = martingale_levels
                if martingale_multiplier is not None: config.martingale_multiplier = Decimal(str(martingale_multiplier))
                # Soros
                if soros_enabled is not None:   config.soros_enabled = soros_enabled
                if soros_levels is not None:    config.soros_levels = soros_levels
                if soros_pct is not None:       config.soros_pct = Decimal(str(soros_pct))

                config.updated_at = datetime.utcnow()
                await session.commit()

                logger.info(
                    f"[AUTOTRADE DAO] Config atualizada para {user_id}: "
                    f"soros={config.soros_enabled} mart={config.martingale_enabled} "
                    f"reduce={config.reduce_enabled} amount={config.amount}"
                )
                return True

        except Exception as e:
            logger.error(f"Erro ao atualizar config de autotrade: {e}", exc_info=True)
            return False
    
    async def delete_config(self, user_id: str) -> bool:
        """
        Remove configuração de autotrade do usuário.
        
        Args:
            user_id: ID do usuário
            
        Returns:
            True se removido com sucesso, False caso contrário
        """
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    delete(AutotradeConfig).where(
                        AutotradeConfig.user_id == uuid.UUID(user_id)
                    )
                )
                
                if result.rowcount > 0:
                    logger.info(f"[AUTOTRADE DAO] Config removida para user {user_id}")
                    return True
                else:
                    logger.warning(f"Config não encontrada para remoção: {user_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"Erro ao remover config de autotrade: {e}")
            return False
    
    async def list_active_configs(self) -> List[AutotradeConfig]:
        """
        Lista todas as configurações de autotrade ativas (autotrade=1).
        
        Returns:
            Lista de AutotradeConfig ativas
        """
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(AutotradeConfig).where(
                        AutotradeConfig.autotrade == 1
                    )
                )
                return result.scalars().all()
                
        except Exception as e:
            logger.error(f"Erro ao listar configs ativas: {e}")
            return []
    
    async def list_all_configs(self) -> List[AutotradeConfig]:
        """
        Lista todas as configurações de autotrade.
        
        Returns:
            Lista de todas as AutotradeConfig
        """
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(select(AutotradeConfig))
                return result.scalars().all()
                
        except Exception as e:
            logger.error(f"Erro ao listar todas configs: {e}")
            return []
    
    async def get_config_with_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca configuração de autotrade com dados do usuário.
        
        Args:
            user_id: ID do usuário
            
        Returns:
            Dicionário com config e dados do usuário ou None
        """
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(AutotradeConfig, User)
                    .join(User, AutotradeConfig.user_id == User.id)
                    .where(AutotradeConfig.user_id == UUID(user_id))
                )
                row = result.first()
                
                if not row:
                    return None
                
                config, user = row
                return {
                    "config": config,
                    "user": user,
                    "user_id": str(user.id),
                    "email": user.email,
                    "role": user.role,
                    "operator": user.operator
                }
                
        except Exception as e:
            logger.error(f"Erro ao buscar config com usuário: {e}")
            return None
    
    async def ensure_admin_config(self) -> Optional[AutotradeConfig]:
        """
        Garante que o admin tenha uma configuração de autotrade
        vinculada à estratégia Scalping5s.
        
        Returns:
            AutotradeConfig do admin ou None se erro
        """
        try:
            async with self.db_manager.get_session() as session:
                # Buscar usuário admin
                result = await session.execute(
                    select(User).where(User.email == "admin@gmail.com")
                )
                admin = result.scalars().first()
                
                if not admin:
                    logger.error("Usuário admin não encontrado")
                    return None
                
                # Verificar se já tem config
                result = await session.execute(
                    select(AutotradeConfig).where(
                        AutotradeConfig.user_id == admin.id
                    )
                )
                config = result.scalars().first()
                
                if config:
                    # Config já existe — não sobrescrever escolha do usuário
                    logger.info(
                        f"[AUTOTRADE DAO] Config do admin já existe com estratégia '{config.strategy_name}' — sem alterações"
                    )
                    return config
                
                # Criar nova config para admin com estratégia scalping
                config = AutotradeConfig(
                    user_id=admin.id,
                    autotrade=1,  # Ligado por padrão
                    amount=Decimal("1.00"),
                    strategy_name="Scalping5s"  # Estratégia scalping
                )
                
                session.add(config)
                
                logger.info(
                    f"[AUTOTRADE DAO] Config de autotrade criada para admin "
                    f"({admin.email}) com estratégia Scalping5s"
                )
                
                return config
                
        except Exception as e:
            logger.error(f"Erro ao garantir config do admin: {e}")
            return None
    
    async def get_admin_config(self) -> Optional[AutotradeConfig]:
        """
        Busca configuração de autotrade do admin.
        
        Returns:
            AutotradeConfig do admin ou None
        """
        try:
            async with self.db_manager.get_session() as session:
                # Buscar usuário admin
                result = await session.execute(
                    select(User).where(User.email == "admin@gmail.com")
                )
                admin = result.scalars().first()
                
                if not admin:
                    return None
                
                # Buscar config
                result = await session.execute(
                    select(AutotradeConfig).where(
                        AutotradeConfig.user_id == admin.id
                    )
                )
                return result.scalars().first()
                
        except Exception as e:
            logger.error(f"Erro ao buscar config do admin: {e}")
            return None


# Instância global (será inicializada posteriormente)
autotrade_dao: Optional[AutotradeDAO] = None


async def init_autotrade_dao(db_manager) -> AutotradeDAO:
    """Inicializa o DAO de autotrade global"""
    global autotrade_dao
    autotrade_dao = AutotradeDAO(db_manager)
    
    # Garantir que admin tenha config com estratégia scalping
    await autotrade_dao.ensure_admin_config()
    
    logger.info("[OK] AutotradeDAO inicializado")
    return autotrade_dao
