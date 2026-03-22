"""
Serviço de Autotrade - Lógica de negócio para autotrade
"""
from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import UUID
from decimal import Decimal

from ...database.models import AutotradeConfig
from ...managers.log_manager import get_manager_logger

logger = get_manager_logger("autotrade_service")


class AutotradeService:
    """Serviço para gerenciar configurações de autotrade"""
    
    def __init__(self, autotrade_manager=None, user_manager=None, autotrade_dao=None):
        self.autotrade_manager = autotrade_manager
        self.user_manager = user_manager
        self._autotrade_dao = autotrade_dao
        self._trade_executor = None
    
    def set_managers(self, autotrade_manager, user_manager, autotrade_dao=None, trade_executor=None):
        """Injeta os managers necessários"""
        self.autotrade_manager = autotrade_manager
        self.user_manager = user_manager
        if autotrade_dao:
            self._autotrade_dao = autotrade_dao
        if trade_executor:
            self._trade_executor = trade_executor
    
    def _get_autotrade_dao(self):
        """Obtém a instância do DAO"""
        # Se foi injetado, usar
        if self._autotrade_dao:
            return self._autotrade_dao
        
        # Caso contrário, tentar importar
        try:
            from ...database.autotrade_dao import autotrade_dao
            return autotrade_dao
        except Exception as e:
            logger.error(f"[DAO] Erro ao importar autotrade_dao: {e}")
            return None
    
    async def toggle_autotrade(
        self, 
        user_id: str, 
        enabled: bool, 
        strategy_id: str = "scalping_5s",
        execute: str = "signal"
    ) -> Tuple[bool, dict, Optional[str]]:
        """
        Liga/desliga autotrade para o usuário
        Returns: (success, data, error_message)
        """
        try:
            logger.info(f"[TOGGLE] User {user_id} -> enabled={enabled}, strategy={strategy_id}, execute={execute}")
            
            autotrade_dao = self._get_autotrade_dao()
            if not autotrade_dao:
                logger.error("[TOGGLE] AutotradeDAO não disponível - verificar inicialização do engine")
                return False, {}, "Sistema de autotrade não disponível. Aguarde a inicialização completa."
            
            # Converter enabled para int (1=ON, 0=OFF)
            autotrade_value = 1 if enabled else 0
            # Normalizar snake_case → PascalCase para consistência com _strategies dict
            _name_map = {
                'scalping_5s': 'Scalping5s',
                'trend_m1':    'TrendM1',
            }
            strategy_name = _name_map.get(strategy_id, strategy_id)
            
            # Tentar atualizar config existente
            updated = await autotrade_dao.update_config(
                user_id=user_id,
                autotrade=autotrade_value,
                strategy_name=strategy_name,
                execute=execute
            )
            
            # Se não existe, criar
            if not updated:
                await autotrade_dao.create_config(
                    user_id=user_id,
                    autotrade=autotrade_value,
                    strategy_name=strategy_name,
                    execute=execute
                )
            
            # Invalidar cache do AutotradeManager
            if self.autotrade_manager:
                await self.autotrade_manager.invalidate_user_cache(user_id)
                logger.info(f"[TOGGLE] Cache invalidado para user {user_id}")
            
            # Log no user_manager sobre ativação da estratégia (opcional)
            if self.user_manager:
                try:
                    await self.user_manager.on_strategy_activated(
                        user_id=user_id,
                        strategy_name=strategy_name,
                        enabled=enabled
                    )
                except Exception as e:
                    logger.debug(f"[TOGGLE] user_manager.on_strategy_activated falhou (não crítico): {e}")
            
            return True, {
                "enabled": enabled,
                "user_id": user_id,
                "strategy": strategy_name,
                "execute": execute
            }, None
            
        except Exception as e:
            logger.error(f"Erro ao toggle autotrade: {e}")
            return False, {}, str(e)
    
    async def get_status(self, user_id: str) -> Tuple[bool, dict, Optional[str]]:
        """
        Obtém status atual do autotrade do usuário
        Returns: (success, data, error_message)
        """
        try:
            logger.info(f"[STATUS] Buscando status autotrade para user {user_id}")
            
            autotrade_dao = self._get_autotrade_dao()
            if not autotrade_dao:
                logger.error("[STATUS] AutotradeDAO não disponível - verificar inicialização do engine")
                # Retornar padrão ao invés de erro para não quebrar o app
                return True, {
                    "enabled": False,
                    "amount": 1.0,
                    "strategy_name": "Scalping5s",
                    "cooldown": "60",
                    "execute": "signal",
                    "user_id": user_id
                }, None
            
            config = await autotrade_dao.get_config_by_user(user_id)
            
            if config:
                logger.info(f"[STATUS] Config encontrada: autotrade={config.autotrade}, strategy={config.strategy_name}, soros={config.soros_enabled}, mart={config.martingale_enabled}")
                return True, {
                    "enabled": config.autotrade == 1,
                    "amount": float(config.amount),
                    "strategy_name": config.strategy_name,
                    "cooldown": config.cooldown,
                    "execute": config.execute,
                    "user_id": user_id,
                    # Stops
                    "stop_loss_enabled": bool(config.stop_loss_enabled),
                    "stop_loss_value": float(config.stop_loss_value) if config.stop_loss_value else 0.0,
                    "stop_gain_enabled": bool(config.stop_gain_enabled),
                    "stop_gain_value": float(config.stop_gain_value) if config.stop_gain_value else 0.0,
                    "stop_soft_mode": bool(config.stop_soft_mode),
                    "stop_win_seq_enabled": bool(config.stop_win_seq_enabled),
                    "stop_win_seq": int(config.stop_win_seq) if config.stop_win_seq else 3,
                    "stop_loss_seq_enabled": bool(config.stop_loss_seq_enabled),
                    "stop_loss_seq": int(config.stop_loss_seq) if config.stop_loss_seq else 3,
                    "stop_seq_soft_mode": bool(config.stop_seq_soft_mode),
                    "stop_medium_enabled": bool(config.stop_medium_enabled),
                    "stop_medium_pct": float(config.stop_medium_pct) if config.stop_medium_pct else 50.0,
                    "stop_medium_soft_mode": bool(config.stop_medium_soft_mode),
                    # Redução
                    "reduce_enabled": bool(config.reduce_enabled),
                    "reduce_loss_trigger": int(config.reduce_loss_trigger) if config.reduce_loss_trigger else 3,
                    "reduce_win_exit": int(config.reduce_win_exit) if config.reduce_win_exit else 2,
                    "reduce_pct": float(config.reduce_pct) if config.reduce_pct else 50.0,
                    # Martingale
                    "martingale_enabled": bool(config.martingale_enabled),
                    "martingale_levels": int(config.martingale_levels) if config.martingale_levels else 3,
                    "martingale_multiplier": float(config.martingale_multiplier) if config.martingale_multiplier else 2.0,
                    # Soros
                    "soros_enabled": bool(config.soros_enabled),
                    "soros_levels": int(config.soros_levels) if config.soros_levels else 3,
                    "soros_pct": float(config.soros_pct) if config.soros_pct else 100.0,
                    # Estado de sessão
                    "stop_triggered": bool(config.stop_triggered),
                    "stop_type": config.stop_type or None,
                }, None
            
            logger.warning(f"[STATUS] Config NÃO encontrada para user {user_id}")
            return True, {
                "enabled": False,
                "amount": 1.0,
                "strategy_name": "Scalping5s",
                "cooldown": "60",
                "execute": "signal",
                "user_id": user_id,
                "stop_loss_enabled": False, "stop_loss_value": 0.0,
                "stop_gain_enabled": False, "stop_gain_value": 0.0,
                "stop_soft_mode": False,
                "stop_win_seq_enabled": False, "stop_win_seq": 3,
                "stop_loss_seq_enabled": False, "stop_loss_seq": 3,
                "stop_seq_soft_mode": False,
                "stop_medium_enabled": False, "stop_medium_pct": 50.0, "stop_medium_soft_mode": False,
                "reduce_enabled": False, "reduce_loss_trigger": 3, "reduce_win_exit": 2, "reduce_pct": 50.0,
                "martingale_enabled": False, "martingale_levels": 3, "martingale_multiplier": 2.0,
                "soros_enabled": False, "soros_levels": 3, "soros_pct": 100.0,
            }, None
            
        except Exception as e:
            logger.error(f"[STATUS] Erro ao buscar status: {e}")
            return False, {}, str(e)
    
    async def update_config(
        self,
        user_id: str,
        amount: Optional[float] = None,
        strategy_name: Optional[str] = None,
        cooldown: Optional[str] = None,
        execute: Optional[str] = None,
        # Stops
        stop_loss_enabled: Optional[bool] = None,
        stop_loss_value: Optional[float] = None,
        stop_gain_enabled: Optional[bool] = None,
        stop_gain_value: Optional[float] = None,
        stop_soft_mode: Optional[bool] = None,
        stop_win_seq_enabled: Optional[bool] = None,
        stop_win_seq: Optional[int] = None,
        stop_loss_seq_enabled: Optional[bool] = None,
        stop_loss_seq: Optional[int] = None,
        stop_seq_soft_mode: Optional[bool] = None,
        stop_medium_enabled: Optional[bool] = None,
        stop_medium_pct: Optional[float] = None,
        stop_medium_soft_mode: Optional[bool] = None,
        # Redução
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
    ) -> Tuple[bool, dict, Optional[str]]:
        """Atualiza configuração de autotrade (todos os campos)."""
        try:
            autotrade_dao = self._get_autotrade_dao()
            if not autotrade_dao:
                return False, {}, "AutotradeDAO não disponível"

            amount_decimal = Decimal(str(amount)) if amount else None

            updated = await autotrade_dao.update_config(
                user_id=user_id,
                amount=amount_decimal,
                strategy_name=strategy_name,
                cooldown=cooldown,
                execute=execute,
                stop_loss_enabled=stop_loss_enabled,
                stop_loss_value=stop_loss_value,
                stop_gain_enabled=stop_gain_enabled,
                stop_gain_value=stop_gain_value,
                stop_soft_mode=stop_soft_mode,
                stop_win_seq_enabled=stop_win_seq_enabled,
                stop_win_seq=stop_win_seq,
                stop_loss_seq_enabled=stop_loss_seq_enabled,
                stop_loss_seq=stop_loss_seq,
                stop_seq_soft_mode=stop_seq_soft_mode,
                stop_medium_enabled=stop_medium_enabled,
                stop_medium_pct=stop_medium_pct,
                stop_medium_soft_mode=stop_medium_soft_mode,
                reduce_enabled=reduce_enabled,
                reduce_loss_trigger=reduce_loss_trigger,
                reduce_win_exit=reduce_win_exit,
                reduce_pct=reduce_pct,
                martingale_enabled=martingale_enabled,
                martingale_levels=martingale_levels,
                martingale_multiplier=martingale_multiplier,
                soros_enabled=soros_enabled,
                soros_levels=soros_levels,
                soros_pct=soros_pct,
            )

            if not updated:
                await autotrade_dao.create_config(
                    user_id=user_id,
                    autotrade=0,
                    amount=amount_decimal or Decimal("1.00"),
                    strategy_name=strategy_name or "Scalping5s",
                    cooldown=cooldown or "60",
                    execute=execute or "signal"
                )

            # Invalidar cache do autotrade_manager E do trade_executor
            if self.autotrade_manager:
                await self.autotrade_manager.invalidate_user_cache(user_id)
            if self._trade_executor:
                self._trade_executor.invalidate_config_cache(user_id)
                # Se o amount base foi alterado, resetar estado de sessão
                # para aplicar o novo valor imediatamente (sem esperar loss/max level)
                if amount is not None:
                    await self._trade_executor.reset_session_state(user_id)
                    logger.info(f"[CONFIG UPDATE] Estado de sessão resetado para {user_id} (amount alterado)")

            return True, {"user_id": user_id, "updated": True}, None

        except Exception as e:
            logger.error(f"Erro ao atualizar config: {e}", exc_info=True)
            return False, {}, str(e)
    
    async def ensure_config_exists(self, user_id: str) -> bool:
        """Garante que o usuário tenha uma configuração de autotrade"""
        try:
            autotrade_dao = self._get_autotrade_dao()
            if not autotrade_dao:
                return False
            
            config = await autotrade_dao.get_config_by_user(user_id)
            if config:
                return True
            
            # Criar config padrão
            await autotrade_dao.create_config(
                user_id=user_id,
                autotrade=0,
                amount=Decimal("1.00"),
                strategy_name="Scalping5s",
                cooldown="60",
                execute="signal"
            )
            logger.info(f"Config padrão criada para user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao criar config padrão: {e}")
            return False


# Instância singleton (será configurada com managers em runtime)
autotrade_service = AutotradeService()
