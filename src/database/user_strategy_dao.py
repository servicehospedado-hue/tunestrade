"""
UserStrategyDAO - CRUD para estratégias personalizadas dos usuários
"""
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging

from sqlalchemy import select, update, delete

from .models import UserStrategy

logger = logging.getLogger("user_strategy_dao")


class UserStrategyDAO:
    def __init__(self, db_manager):
        self.db_manager = db_manager

    async def create(self, user_id: str, name: str, description: str, indicators: list) -> Optional[UserStrategy]:
        try:
            async with self.db_manager.get_session() as session:
                strategy = UserStrategy(
                    user_id=uuid.UUID(user_id),
                    name=name,
                    description=description or "",
                    indicators=indicators,
                    is_active=False,
                )
                session.add(strategy)
                await session.flush()
                await session.refresh(strategy)
                logger.info(f"[DAO] Estratégia criada: {strategy.id} para user {user_id}")
                return strategy
        except Exception as e:
            logger.error(f"[DAO] Erro ao criar estratégia: {e}")
            return None

    async def get_by_user(self, user_id: str) -> List[UserStrategy]:
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(UserStrategy)
                    .where(UserStrategy.user_id == uuid.UUID(user_id))
                    .order_by(UserStrategy.created_at.desc())
                )
                return result.scalars().all()
        except Exception as e:
            logger.error(f"[DAO] Erro ao listar estratégias: {e}")
            return []

    async def get_by_id(self, strategy_id: str, user_id: str) -> Optional[UserStrategy]:
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(UserStrategy).where(
                        UserStrategy.id == uuid.UUID(strategy_id),
                        UserStrategy.user_id == uuid.UUID(user_id),
                    )
                )
                return result.scalars().first()
        except Exception as e:
            logger.error(f"[DAO] Erro ao buscar estratégia {strategy_id}: {e}")
            return None

    async def update(self, strategy_id: str, user_id: str, name: str, description: str, indicators: list) -> bool:
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    update(UserStrategy)
                    .where(
                        UserStrategy.id == uuid.UUID(strategy_id),
                        UserStrategy.user_id == uuid.UUID(user_id),
                    )
                    .values(
                        name=name,
                        description=description or "",
                        indicators=indicators,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"[DAO] Erro ao atualizar estratégia {strategy_id}: {e}")
            return False

    async def delete(self, strategy_id: str, user_id: str) -> bool:
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    delete(UserStrategy).where(
                        UserStrategy.id == uuid.UUID(strategy_id),
                        UserStrategy.user_id == uuid.UUID(user_id),
                    )
                )
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"[DAO] Erro ao deletar estratégia {strategy_id}: {e}")
            return False

    async def set_active(self, strategy_id: str, user_id: str, is_active: bool) -> bool:
        """Ativa/desativa uma estratégia. Se ativando, desativa todas as outras do usuário."""
        try:
            async with self.db_manager.get_session() as session:
                if is_active:
                    # Desativar todas as outras
                    await session.execute(
                        update(UserStrategy)
                        .where(UserStrategy.user_id == uuid.UUID(user_id))
                        .values(is_active=False, updated_at=datetime.now(timezone.utc))
                    )
                result = await session.execute(
                    update(UserStrategy)
                    .where(
                        UserStrategy.id == uuid.UUID(strategy_id),
                        UserStrategy.user_id == uuid.UUID(user_id),
                    )
                    .values(is_active=is_active, updated_at=datetime.now(timezone.utc))
                )
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"[DAO] Erro ao set_active estratégia {strategy_id}: {e}")
            return False


# Singleton
_user_strategy_dao: Optional[UserStrategyDAO] = None


def init_user_strategy_dao(db_manager) -> UserStrategyDAO:
    global _user_strategy_dao
    _user_strategy_dao = UserStrategyDAO(db_manager)
    return _user_strategy_dao


def get_user_strategy_dao() -> Optional[UserStrategyDAO]:
    return _user_strategy_dao
