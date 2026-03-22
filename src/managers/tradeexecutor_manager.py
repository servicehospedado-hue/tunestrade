"""
Trade Executor - Executa trades usando conexões gerenciadas pelo ConnectionManager
Simplificado: apenas executa trades, não gerencia conexões
"""
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

from ..managers.log_manager import get_manager_logger
from ..database import DatabaseManager
from ..managers.connection_manager import ConnectionManager
from ..pocketoption.models import OrderDirection, OrderStatus

logger = get_manager_logger("trade_executor")


@dataclass
class UserTradeState:
    """Estado de trade de um usuário (sem conexão - só config e cooldown)"""
    user_id: str
    config: Any  # AutotradeConfig ou AutotradeStatus
    last_trade_time: Optional[datetime] = None
    system_cooldown_seconds: Optional[int] = None
    user_cooldown_seconds: Optional[int] = None
    last_trade_time_by_strategy: Dict[str, datetime] = None

    # ── Estado dinâmico (carregado do banco, persistido após cada trade) ──
    amount_current: float = 0.0          # Valor atual (pode diferir do base)
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    martingale_level: int = 0
    soros_level: int = 0
    martingale_base_amount: float = 0.0  # Base do Martingale (preservada quando Soros reseta no loss)
    reduce_active: bool = False
    reduce_level: int = 0
    session_peak_balance: Optional[float] = None
    session_profit: float = 0.0
    session_trades: int = 0
    stop_triggered: bool = False
    stop_type: Optional[str] = None
    state_loaded: bool = False           # Flag: estado já foi carregado do banco

    def __post_init__(self):
        if self.last_trade_time_by_strategy is None:
            self.last_trade_time_by_strategy = {}


@dataclass
class ActiveOrder:
    """Ordem ativa sendo rastreada"""
    order_id: str
    user_id: str
    asset: str
    direction: str
    amount: float
    duration: int
    placed_at: datetime
    expires_at: datetime
    signal_id: Optional[str] = None
    result: Optional[str] = None  # 'win', 'loss', 'draw', None
    profit: Optional[float] = None
    processed_by_callback: bool = False  # Flag para evitar processamento duplo


class TradeExecutor:
    """
    Executor de trades - usa conexões do ConnectionManager.
    
    Responsabilidade única: executar trades quando solicitado.
    NÃO gerencia conexões (isso é do ConnectionManager).
    
    Agora rastreia ordens ativas e registra resultados.
    """
    
    def __init__(
        self,
        db_manager: DatabaseManager,
        connection_manager: ConnectionManager,
        cooldown_seconds: int = 60,
        default_duration: int = 60
    ):
        self.db_manager = db_manager
        self.connection_manager = connection_manager
        self.cooldown_seconds = cooldown_seconds
        self.default_duration = default_duration
        
        # Estado de cooldown por usuário: {user_id: UserTradeState}
        self._user_states: Dict[str, UserTradeState] = {}
        
        # Ordens ativas sendo rastreadas: {order_id: ActiveOrder}
        self._active_orders: Dict[str, ActiveOrder] = {}
        
        # Histórico de ordens finalizadas (últimas 100)
        self._completed_orders: List[ActiveOrder] = []
        
        # Mapeamento order_id -> user_id para sincronização
        self._order_to_user: Dict[str, str] = {}
        
        # Agendamento de trades oncandle: {(user_id, signal_id): scheduled_task}
        self._scheduled_trades: Dict[tuple, asyncio.Task] = {}
        
        # Cache de configuração por usuário: {user_id: (config, cached_at)}
        self._config_cache: Dict[str, tuple] = {}
        self._config_cache_ttl: int = 30  # segundos — recarrega config a cada 30s
        
        # Estado
        self._running = False

    # ── Persistência de estado de sessão ──────────────────────────────────

    async def _load_session_state(self, user_id: str) -> None:
        """Carrega estado de sessão do banco para memória (uma vez por sessão)"""
        state = self._user_states.get(user_id)
        if not state or state.state_loaded:
            return
        try:
            from sqlalchemy import select
            from ..database.models import AutotradeConfig
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(AutotradeConfig).where(AutotradeConfig.user_id == user_id)
                )
                row = result.scalar_one_or_none()
                cfg = state.config
                base_amount = float(getattr(cfg, 'amount', 1.0))
                
                if row:
                    state.amount_current = float(row.amount_current)
                    state.consecutive_wins = row.consecutive_wins
                    state.consecutive_losses = row.consecutive_losses
                    state.martingale_level = row.martingale_level
                    state.soros_level = row.soros_level
                    state.reduce_active = row.reduce_active
                    state.reduce_level = row.reduce_level
                    state.session_peak_balance = float(row.session_peak_balance) if row.session_peak_balance else None
                    state.session_profit = float(row.session_profit)
                    state.session_trades = row.session_trades
                    state.stop_triggered = row.stop_triggered
                    state.stop_type = row.stop_type
                    logger.info(f"[STATE] Estado carregado do banco para {user_id}: mart={state.martingale_level} soros={state.soros_level} reduce={state.reduce_active} amount={state.amount_current}")

                    # Se stop já estava ativo no banco, executar parada completa imediatamente
                    if state.stop_triggered:
                        logger.warning(f"[STATE] stop_triggered=True carregado do banco para {user_id} — executando parada completa")
                        state.state_loaded = True
                        asyncio.create_task(self._handle_stop_triggered(user_id, state.stop_type or "unknown"))
                        return
                    
                    # ── VALIDAÇÃO: Detectar dessincronia entre amount_current e base_amount ──
                    # Se amount_current está muito diferente do base (>50% ou <50%), provavelmente
                    # o usuário mudou o amount base mas o servidor foi reiniciado antes do reset.
                    # Nesse caso, resetar automaticamente para evitar trades com valor errado.
                    if state.amount_current > 0 and base_amount > 0:
                        ratio = state.amount_current / base_amount
                        # Se ratio > 2.0 (amount_current é mais que o dobro do base)
                        # OU ratio < 0.5 (amount_current é menos que metade do base)
                        # → resetar para o base
                        if ratio > 2.0 or ratio < 0.5:
                            logger.warning(
                                f"[STATE] Dessincronia detectada para {user_id}: "
                                f"amount_current=${state.amount_current} vs base=${base_amount} (ratio={ratio:.2f}) "
                                f"— resetando ao base (provável mudança de config)"
                            )
                            state.amount_current = base_amount
                            state.martingale_level = 0
                            state.soros_level = 0
                            state.reduce_active = False
                            state.reduce_level = 0
                            state.consecutive_wins = 0
                            state.consecutive_losses = 0
                            # Persistir reset no banco imediatamente
                            row.amount_current = base_amount
                            row.martingale_level = 0
                            row.soros_level = 0
                            row.reduce_active = False
                            row.reduce_level = 0
                            row.consecutive_wins = 0
                            row.consecutive_losses = 0
                            await session.commit()
                            logger.info(f"[STATE] Estado resetado e salvo no banco para {user_id}")
                else:
                    # Primeira vez — inicializar com amount base
                    state.amount_current = base_amount
                    logger.info(f"[STATE] Novo estado para {user_id}: amount_current={state.amount_current}")
            state.state_loaded = True
        except Exception as e:
            logger.error(f"[STATE] Erro ao carregar estado de {user_id}: {e}", exc_info=True)
            state.state_loaded = True  # Evitar loop de retry

    async def _save_session_state(self, user_id: str) -> None:
        """Persiste estado de sessão em memória para o banco"""
        state = self._user_states.get(user_id)
        if not state:
            return
        try:
            from sqlalchemy import select
            from ..database.models import AutotradeConfig
            from datetime import timezone
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(AutotradeConfig).where(AutotradeConfig.user_id == user_id)
                )
                row = result.scalar_one_or_none()
                now = datetime.now(timezone.utc)
                if row:
                    row.amount_current = state.amount_current
                    row.consecutive_wins = state.consecutive_wins
                    row.consecutive_losses = state.consecutive_losses
                    row.martingale_level = state.martingale_level
                    row.soros_level = state.soros_level
                    row.reduce_active = state.reduce_active
                    row.reduce_level = state.reduce_level
                    row.session_peak_balance = state.session_peak_balance
                    row.session_profit = state.session_profit
                    row.session_trades = state.session_trades
                    row.stop_triggered = state.stop_triggered
                    row.stop_type = state.stop_type
                    row.updated_at = now
                    await session.commit()
                    logger.debug(f"[STATE] Estado salvo no banco para {user_id}")
                else:
                    logger.warning(f"[STATE] Config não encontrada para {user_id} — não foi possível salvar estado")
        except Exception as e:
            logger.error(f"[STATE] Erro ao salvar estado de {user_id}: {e}", exc_info=True)

    async def reset_session_state(self, user_id: str) -> None:
        """Reseta estado de sessão (chamado quando usuário desliga/liga autotrade)"""
        state = self._user_states.get(user_id)
        cfg_amount = float(getattr(state.config, 'amount', 1.0)) if state else 1.0
        if state:
            state.amount_current = cfg_amount
            state.consecutive_wins = 0
            state.consecutive_losses = 0
            state.martingale_level = 0
            state.martingale_base_amount = 0.0
            state.soros_level = 0
            state.reduce_active = False
            state.reduce_level = 0
            state.session_peak_balance = None
            state.session_profit = 0.0
            state.session_trades = 0
            state.stop_triggered = False
            state.stop_type = None
        await self._save_session_state(user_id)
        # Invalidar cache de config ao resetar
        self._config_cache.pop(user_id, None)
        logger.info(f"[STATE] Estado de sessão resetado para {user_id}")

    def _compute_amount(self, state: 'UserTradeState', cfg: Any) -> float:
        """
        Calcula o valor da próxima operação.
        Prioridade: Reduce > Martingale > Soros > base
        Mínimo absoluto: $1.00 (limite da PocketOption)
        """
        base = float(getattr(cfg, 'amount', 1.0))
        MIN_AMOUNT = 1.0

        if state.amount_current <= 0:
            state.amount_current = base

        mart_on = getattr(cfg, 'martingale_enabled', False)
        soros_on = getattr(cfg, 'soros_enabled', False)
        reduce_on = getattr(cfg, 'reduce_enabled', False)

        logger.debug(
            f"[COMPUTE] reduce={reduce_on}(active={state.reduce_active}) "
            f"mart={mart_on}(level={state.martingale_level}) "
            f"soros={soros_on}(level={state.soros_level}) "
            f"amount_current=${state.amount_current} base=${base}"
        )

        # Reduce tem prioridade — quando ativo, ignora Martingale (são exclusivos)
        if reduce_on and not mart_on and state.reduce_active:
            amount = max(round(state.amount_current, 2), MIN_AMOUNT)
            if amount != round(state.amount_current, 2):
                logger.debug(f"[COMPUTE] Reduce: amount_current=${state.amount_current} < mínimo → clamp para ${MIN_AMOUNT}")
            else:
                logger.debug(f"[COMPUTE] Reduce ativo nível {state.reduce_level}: usando amount_current = ${amount}")
            return amount

        # Martingale: se há nível pendente, usa ele
        if mart_on and state.martingale_level > 0:
            mult = float(getattr(cfg, 'martingale_multiplier', 2.0))
            base_for_mart = state.martingale_base_amount if state.martingale_base_amount > 0 else base
            amount = max(round(base_for_mart * (mult ** state.martingale_level), 2), MIN_AMOUNT)
            logger.debug(f"[COMPUTE] Martingale nível {state.martingale_level}: ${base_for_mart} * {mult}^{state.martingale_level} = ${amount}")
            return amount

        # Soros: só entra se Martingale não tem nível pendente
        if soros_on and state.soros_level > 0:
            amount = max(round(state.amount_current, 2), MIN_AMOUNT)
            logger.debug(f"[COMPUTE] Soros nível {state.soros_level}: usando amount_current = ${amount}")
            return amount

        logger.debug(f"[COMPUTE] Usando amount base = ${base}")
        return max(base, MIN_AMOUNT)

    async def _process_trade_result(self, user_id: str, result: str, profit: float, client: Any) -> None:
        """
        Processa resultado de um trade (win/loss/draw) e atualiza estado de sessão.
        Aplica lógica de martingale, soros, redução inteligente e stops.
        """
        logger.info(f"[STATE] Processando resultado para {user_id}: {result} | profit=${profit:.2f}")
        state = self._user_states.get(user_id)
        if not state:
            logger.warning(f"[STATE] Estado não encontrado para {user_id} — ignorando resultado")
            return

        cfg = state.config
        base_amount = float(getattr(cfg, 'amount', 1.0))
        
        # Log de configurações ativas
        soros_enabled = getattr(cfg, 'soros_enabled', False)
        mart_enabled = getattr(cfg, 'martingale_enabled', False)
        reduce_enabled = getattr(cfg, 'reduce_enabled', False)
        logger.debug(f"[STATE] Config para {user_id}: soros={soros_enabled} mart={mart_enabled} reduce={reduce_enabled} | result={result}")

        # Atualizar contadores de sessão
        state.session_trades += 1
        state.session_profit += profit
        logger.info(
            f"[SESSÃO] {user_id}: trade #{state.session_trades} | "
            f"resultado={result} profit=${profit:.2f} | "
            f"profit_acumulado=${state.session_profit:.2f}"
        )

        # Atualizar pico de saldo (para stop médio) — só atualiza se saldo subiu
        try:
            balance = await client.get_balance()
            current_balance = float(balance.balance)
            if state.session_peak_balance is None:
                state.session_peak_balance = current_balance
                logger.info(f"[STOP MÉDIO] Pico inicial (pós-trade) para {user_id}: ${current_balance:.2f}")
            elif current_balance > state.session_peak_balance:
                logger.info(f"[STOP MÉDIO] Novo pico para {user_id}: ${state.session_peak_balance:.2f} → ${current_balance:.2f}")
                state.session_peak_balance = current_balance
        except Exception:
            current_balance = None

        # ── Atualizar sequências (draw não altera contadores) ─────────────
        if result == 'win':
            state.consecutive_wins += 1
            state.consecutive_losses = 0
            logger.debug(f"[STATE] Win registrado: consecutive_wins={state.consecutive_wins}")
        elif result == 'loss':
            state.consecutive_losses += 1
            state.consecutive_wins = 0
            logger.debug(f"[STATE] Loss registrado: consecutive_losses={state.consecutive_losses}")
        else:  # draw
            logger.debug(f"[STATE] Draw registrado: contadores mantidos (wins={state.consecutive_wins}, losses={state.consecutive_losses})")
            if soros_enabled or mart_enabled:
                logger.warning(f"[STATE] ATENÇÃO: Soros/Martingale ativados mas resultado é DRAW — gestão de banca NÃO será aplicada (normal em demo)")

        # ── Verificar Stops (ANTES de gestão de banca resetar contadores) ─
        if not state.stop_triggered:
            stop_hit = None

            # Stop Loss ($)
            if getattr(cfg, 'stop_loss_enabled', False):
                sl_val = float(getattr(cfg, 'stop_loss_value', 0) or 0)
                if sl_val > 0 and state.session_profit <= -sl_val:
                    stop_hit = 'loss'
                    logger.info(f"[STOP LOSS] {user_id}: atingido | sessão=${state.session_profit:.2f} <= -${sl_val:.2f}")
                else:
                    logger.debug(f"[STOP LOSS] {user_id}: ok | sessão=${state.session_profit:.2f} / limite=-${sl_val:.2f}")

            # Stop Gain ($)
            if not stop_hit and getattr(cfg, 'stop_gain_enabled', False):
                sg_val = float(getattr(cfg, 'stop_gain_value', 0) or 0)
                if sg_val > 0 and state.session_profit >= sg_val:
                    stop_hit = 'gain'
                    logger.info(f"[STOP GAIN] {user_id}: atingido | sessão=${state.session_profit:.2f} >= ${sg_val:.2f}")
                else:
                    logger.debug(f"[STOP GAIN] {user_id}: ok | sessão=${state.session_profit:.2f} / alvo=${sg_val:.2f}")

            # Stop por sequência de losses — verificado AQUI antes do Martingale/Reduce resetar
            if not stop_hit and getattr(cfg, 'stop_loss_seq_enabled', False):
                seq = int(getattr(cfg, 'stop_loss_seq', 0) or 0)
                if seq > 0 and state.consecutive_losses >= seq:
                    stop_hit = 'seq_loss'
                    logger.debug(f"[STOP] {user_id}: stop_loss_seq atingido | {state.consecutive_losses} losses consecutivos >= {seq}")

            # Stop por sequência de wins — verificado AQUI antes do Soros/Reduce resetar
            if not stop_hit and getattr(cfg, 'stop_win_seq_enabled', False):
                seq = int(getattr(cfg, 'stop_win_seq', 0) or 0)
                if seq > 0 and state.consecutive_wins >= seq:
                    stop_hit = 'seq_win'
                    logger.debug(f"[STOP] {user_id}: stop_win_seq atingido | {state.consecutive_wins} wins consecutivos >= {seq}")

            # Stop Médio (drawdown do pico)
            if not stop_hit and getattr(cfg, 'stop_medium_enabled', False) and state.session_peak_balance and current_balance:
                pct = float(getattr(cfg, 'stop_medium_pct', 50.0) or 50.0) / 100.0
                threshold = state.session_peak_balance * (1 - pct)
                logger.debug(
                    f"[STOP MÉDIO] {user_id}: pico=${state.session_peak_balance:.2f} "
                    f"threshold=${threshold:.2f} ({pct*100:.0f}%) atual=${current_balance:.2f}"
                )
                if current_balance <= threshold:
                    stop_hit = 'medium'

            if stop_hit:
                soft_map = {
                    'loss': 'stop_soft_mode', 'gain': 'stop_soft_mode',
                    'seq_loss': 'stop_seq_soft_mode', 'seq_win': 'stop_seq_soft_mode',
                    'medium': 'stop_medium_soft_mode',
                }
                soft_field = soft_map.get(stop_hit, 'stop_soft_mode')
                is_soft = getattr(cfg, soft_field, False)

                if is_soft:
                    logger.warning(f"[STOP ALERTA] {user_id}: stop '{stop_hit}' atingido (modo alerta — autotrade continua)")
                else:
                    state.stop_triggered = True
                    state.stop_type = stop_hit
                    logger.warning(f"[STOP] {user_id}: stop '{stop_hit}' atingido — autotrade será pausado")
                    asyncio.create_task(self._handle_stop_triggered(user_id, stop_hit))

        # ── Martingale ────────────────────────────────────────────────────
        # Flag: indica se o win veio de um ciclo de Martingale (para bloquear Soros nesse win)
        win_was_martingale_recovery = False

        if getattr(cfg, 'martingale_enabled', False) and not state.reduce_active:
            max_levels = int(getattr(cfg, 'martingale_levels', 3))
            if result == 'loss':
                if state.martingale_level < max_levels:
                    state.martingale_level += 1
                    # Se não há base do Soros preservada, garantir que está zerado (usa base puro)
                    if state.martingale_base_amount <= 0:
                        state.martingale_base_amount = 0.0
                    logger.info(f"[MARTINGALE] {user_id}: loss → nível {state.martingale_level}/{max_levels} | base_mart=${state.martingale_base_amount if state.martingale_base_amount > 0 else 'base'}")
                else:
                    # Atingiu nível máximo — reseta
                    state.martingale_level = 0
                    state.martingale_base_amount = 0.0
                    logger.info(f"[MARTINGALE] {user_id}: nível máximo atingido → reset")
            elif result == 'win':
                if state.martingale_level > 0:
                    # Win veio de um ciclo de Martingale — reseta e bloqueia Soros neste win
                    win_was_martingale_recovery = True
                    logger.info(f"[MARTINGALE] {user_id}: win após nível {state.martingale_level} → reset ao base (Soros bloqueado neste win)")
                state.martingale_level = 0
                state.martingale_base_amount = 0.0

        # ── Soros ─────────────────────────────────────────────────────────
        if getattr(cfg, 'soros_enabled', False) and not state.reduce_active:
            max_levels = int(getattr(cfg, 'soros_levels', 3))
            pct = float(getattr(cfg, 'soros_pct', 100.0)) / 100.0
            logger.debug(f"[SOROS] Config: max_levels={max_levels}, pct={pct*100}%, current_level={state.soros_level}, result={result}")

            if result == 'win':
                if win_was_martingale_recovery:
                    # Win veio do Martingale — reseta tudo ao base, Soros não acumula
                    state.soros_level = 0
                    state.amount_current = base_amount
                    logger.info(f"[SOROS] {user_id}: win de recuperação Martingale → Soros resetado, próximo trade = base ${base_amount}")
                else:
                    # Win normal — Soros acumula
                    state.soros_level += 1
                    if state.soros_level <= max_levels:
                        old_amount = state.amount_current
                        state.amount_current = round(state.amount_current + abs(profit) * pct, 2)
                        logger.info(f"[SOROS] {user_id}: win → nível {state.soros_level}/{max_levels} | ${old_amount} + (${abs(profit)} * {pct*100}%) = ${state.amount_current}")
                    else:
                        state.soros_level = 0
                        state.amount_current = base_amount
                        logger.info(f"[SOROS] {user_id}: ultrapassou nível máximo ({max_levels}) → reset ao base ${base_amount}")
            elif result == 'loss':
                if state.soros_level > 0:
                    # Preservar amount_current para o Martingale usar como base
                    # Ex: Soros estava em $1.92 → Martingale deve fazer $1.92 * 2 = $3.84
                    if getattr(cfg, 'martingale_enabled', False):
                        state.martingale_base_amount = state.amount_current
                        logger.info(f"[SOROS] {user_id}: loss no nível {state.soros_level} → reset ao base ${base_amount} | martingale_base preservado = ${state.martingale_base_amount}")
                    else:
                        logger.info(f"[SOROS] {user_id}: loss no nível {state.soros_level} → reset ao base ${base_amount}")
                state.soros_level = 0
                state.amount_current = base_amount
            else:  # draw
                logger.debug(f"[SOROS] Draw: nível mantido em {state.soros_level}, amount mantido em ${state.amount_current}")

        # ── Redução Inteligente ───────────────────────────────────────────
        # Funciona junto com Soros. Mutuamente exclusivo com Martingale.
        # Se Martingale estiver ativo, Reduce é ignorado (frontend já garante isso,
        # mas mantemos a verificação aqui como segurança).
        if getattr(cfg, 'reduce_enabled', False) and not getattr(cfg, 'martingale_enabled', False):
            loss_trigger = int(getattr(cfg, 'reduce_loss_trigger', 3))
            win_exit = int(getattr(cfg, 'reduce_win_exit', 2))
            reduce_pct = float(getattr(cfg, 'reduce_pct', 50.0)) / 100.0

            if not state.reduce_active:
                if state.consecutive_losses >= loss_trigger:
                    state.reduce_active = True
                    state.reduce_level += 1
                    # Reduz sobre o valor atual (pode ser base, Martingale ou Soros)
                    valor_atual = self._compute_amount(state, cfg)
                    state.amount_current = round(valor_atual * (1 - reduce_pct), 2)
                    # Pausar Martingale e Soros: resetar níveis
                    state.martingale_level = 0
                    state.martingale_base_amount = 0.0
                    state.soros_level = 0
                    state.consecutive_losses = 0
                    state.consecutive_wins = 0
                    logger.info(
                        f"[REDUCE] {user_id}: ativado nível {state.reduce_level} "
                        f"| valor_base=${valor_atual} → reduzido=${state.amount_current} "
                        f"(Martingale e Soros pausados)"
                    )
            else:
                # Já em redução — operar com amount_current reduzido
                if result == 'win' and state.consecutive_wins >= win_exit:
                    # Saiu da redução — retomar fluxo normal do zero
                    state.reduce_active = False
                    state.reduce_level = 0
                    state.consecutive_wins = 0
                    state.consecutive_losses = 0
                    state.amount_current = base_amount
                    state.martingale_level = 0
                    state.martingale_base_amount = 0.0
                    state.soros_level = 0
                    logger.info(f"[REDUCE] {user_id}: saiu da redução após {win_exit} wins → base ${base_amount} (Martingale/Soros retomados do zero)")
                elif result == 'loss' and state.consecutive_losses >= loss_trigger:
                    # Reduz de novo sobre o valor atual
                    state.reduce_level += 1
                    state.consecutive_losses = 0
                    state.amount_current = round(state.amount_current * (1 - reduce_pct), 2)
                    logger.info(f"[REDUCE] {user_id}: redução adicional nível {state.reduce_level} | amount: ${state.amount_current}")

        # Persistir estado no banco
        logger.info(f"[STATE] Salvando estado para {user_id}: wins={state.consecutive_wins} losses={state.consecutive_losses} mart={state.martingale_level} soros={state.soros_level} reduce={state.reduce_active} amount={state.amount_current}")
        await self._save_session_state(user_id)
    
    def _get_user_cooldown(self, user_id: str, user_config: Any) -> int:
        """
        Obtém o cooldown individual do usuário (configurado no banco).
        Suporta formato fixo ('60') ou intervalo ('60-120' para valor aleatório).
        Este cooldown é ADICIONAL ao cooldown do sistema (timeframe da estratégia).
        """
        import random
        
        cooldown_str = getattr(user_config, 'cooldown', None)
        
        if not cooldown_str:
            return self.cooldown_seconds
        
        try:
            if '-' in str(cooldown_str):
                parts = cooldown_str.split('-')
                min_val = int(parts[0].strip())
                max_val = int(parts[1].strip())
                return random.randint(min_val, max_val)
            else:
                return int(cooldown_str)
        except (ValueError, AttributeError):
            logger.warning(f"[TRADE] Cooldown inválido para {user_id}: {cooldown_str}, usando default {self.cooldown_seconds}s")
            return self.cooldown_seconds

    def _get_system_cooldown(self, signal: Dict[str, Any]) -> int:
        """
        Cooldown do sistema baseado no timeframe da estratégia.
        Impede dois trades no mesmo candle.
        Scalping5s (tf=5s) → 5s, TrendM1 (tf=60s) → 60s
        """
        timeframe = signal.get("timeframe", self.default_duration)
        if timeframe and timeframe > 0:
            return int(timeframe)
        return self.default_duration
            
    async def start(self):
        """Inicia o executor de trades"""
        logger.info("TradeExecutor iniciado (usando ConnectionManager)")
        self._running = True
        
    async def stop(self):
        """Para o executor"""
        logger.info("Parando TradeExecutor...")
        self._running = False
        self._user_states.clear()
        logger.info("TradeExecutor parado")
            
    async def execute_signal(
        self, 
        signal: Dict[str, Any], 
        active_users: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Executa um sinal para usuários ativos usando conexões do ConnectionManager.
        
        Args:
            signal: Dicionário com dados do sinal
            active_users: Dict {user_id: config} dos usuários com autotrade ativo
            
        Returns:
            Lista de resultados de execução por usuário
        """
        logger.info(f"[TRADE EXECUTOR] Recebido sinal: {signal.get('asset')} | {signal.get('direction')} | conf: {signal.get('confidence')}")
        logger.info(f"[TRADE EXECUTOR] Usuários ativos recebidos: {list(active_users.keys())}")
        
        results = []
        
        asset = signal.get("asset")
        direction = signal.get("direction")
        confidence = signal.get("confidence", 0)
        
        if not asset or direction == "NEUTRAL":
            logger.info(f"[TRADE EXECUTOR] Sinal ignorado: asset={asset}, direction={direction}")
            return results

        # Ativos não-OTC só suportam trades com timeframe >= 60s (M1 ou superior).
        # Se o sinal for de um timeframe menor que 60s em ativo não-OTC, ignorar.
        is_otc = asset.lower().endswith("_otc")
        signal_timeframe = signal.get("timeframe", 60)
        if not is_otc and signal_timeframe < 60:
            logger.info(
                f"[TRADE EXECUTOR] Sinal ignorado: ativo não-OTC '{asset}' não suporta "
                f"timeframe {signal_timeframe}s (mínimo 60s/M1)"
            )
            return results
            
        # Mapear direção
        order_direction = OrderDirection.CALL if direction == "CALL" else OrderDirection.PUT
        
        # Executar para cada usuário ativo que usa essa estratégia
        signal_strategy = signal.get("strategy", "Scalping5s")
        logger.info(f"[TRADE EXECUTOR] Estratégia do sinal: {signal_strategy}")
        
        for user_id, user_config in active_users.items():
            user_strategy = getattr(user_config, 'strategy_name', None)
            user_execute = getattr(user_config, 'execute', 'signal')
            logger.info(f"[TRADE EXECUTOR] Usuário {user_id} | estratégia configurada: {user_strategy} | sinal de: {signal_strategy} | execução: {user_execute}")

            # Filtrar: só executar se a estratégia do usuário bate com a do sinal
            if user_strategy and user_strategy != signal_strategy:
                logger.info(f"[TRADE EXECUTOR] Usuário {user_id} ignorado: estratégia {user_strategy} != sinal {signal_strategy}")
                continue

            # Verificar modo de execução
            if user_execute == 'oncandle':
                # Agendar execução para o início da próxima vela
                result = await self._schedule_trade_for_next_candle(user_id, user_config, signal, order_direction)
            else:
                # Executar imediatamente (modo signal)
                result = await self._execute_for_user(user_id, user_config, signal, order_direction)
            
            if result:
                results.append(result)
                
        logger.info(f"[TRADE EXECUTOR] Total de trades executados: {len(results)}")
        return results
        
    async def _schedule_trade_for_next_candle(
        self,
        user_id: str,
        user_config: Any,
        signal: Dict[str, Any],
        direction: OrderDirection
    ) -> Optional[Dict[str, Any]]:
        """
        Agenda um trade para ser executado no início da próxima vela.
        
        Usa o timestamp do sinal como âncora para calcular o alinhamento das velas,
        garantindo sincronização correta mesmo quando sinais chegam com atraso.
        
        Se restar menos de MIN_LEAD_TIME segundos para a próxima vela, pula para
        a vela seguinte — evita executar no meio de uma vela por atraso de processamento.
        """
        try:
            import time
            timeframe = signal.get("timeframe", self.default_duration)
            
            # Threshold mínimo: precisamos de pelo menos este tempo antes da vela
            # para garantir que a ordem seja colocada no início (não no meio)
            MIN_LEAD_TIME = max(1.0, timeframe * 0.10)  # 10% do timeframe, mínimo 1s

            now_ts = time.time()

            # Usar o timestamp do sinal como âncora para calcular o alinhamento das velas.
            # Isso garante que mesmo com atraso de processamento, calculamos corretamente
            # em relação à grade de velas real (epoch-aligned).
            signal_ts = signal.get("timestamp")
            if signal_ts:
                try:
                    if isinstance(signal_ts, str):
                        from datetime import timezone
                        anchor_ts = datetime.fromisoformat(signal_ts).replace(tzinfo=timezone.utc).timestamp()
                    else:
                        anchor_ts = float(signal_ts)
                except Exception:
                    anchor_ts = now_ts
            else:
                anchor_ts = now_ts

            # Calcular o início da vela atual baseado no anchor (timestamp do sinal)
            candle_start_ts = anchor_ts - (anchor_ts % timeframe)
            
            # Próxima vela começa em:
            next_candle_ts = candle_start_ts + timeframe

            # Se a próxima vela já passou (sinal muito atrasado), avançar
            while next_candle_ts <= now_ts:
                next_candle_ts += timeframe

            # Calcular quanto tempo falta para a próxima vela a partir de agora
            seconds_to_next = next_candle_ts - now_ts

            # Se restar menos que MIN_LEAD_TIME, pular para a vela seguinte
            # (evita executar no meio de uma vela por atraso)
            if seconds_to_next < MIN_LEAD_TIME:
                next_candle_ts += timeframe
                seconds_to_next = next_candle_ts - now_ts
                logger.info(
                    f"[TRADE SCHEDULE] {user_id}: apenas {seconds_to_next - timeframe:.2f}s para próxima vela "
                    f"(< {MIN_LEAD_TIME:.1f}s mínimo) → pulando para vela seguinte em {seconds_to_next:.2f}s"
                )

            execute_timestamp = next_candle_ts + 0.05  # 50ms de margem após abertura
            execute_at = datetime.fromtimestamp(execute_timestamp)

            signal_id = signal.get("signal_id", f"{signal.get('asset')}_{anchor_ts}")
            schedule_key = (user_id, signal_id)

            # Cancelar agendamento anterior se existir
            if schedule_key in self._scheduled_trades:
                old_task = self._scheduled_trades[schedule_key]
                old_task.cancel()
                logger.info(f"[TRADE SCHEDULE] Cancelado agendamento anterior para {user_id}")

            async def _execute_at_scheduled_time():
                try:
                    # Aguardar com precisão de 10ms
                    while True:
                        remaining = execute_timestamp - time.time()
                        if remaining <= 0:
                            break
                        await asyncio.sleep(min(remaining, 0.01))

                    actual_time = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    logger.info(f"[TRADE SCHEDULE] Executando trade agendado para {user_id} | hora={actual_time}")
                    result = await self._execute_for_user(user_id, user_config, signal, direction)

                    if result:
                        logger.info(f"[TRADE SCHEDULE] Trade agendado executado: {result.get('order_id')}")
                    else:
                        logger.warning(f"[TRADE SCHEDULE] Falha ao executar trade agendado para {user_id}")

                except asyncio.CancelledError:
                    logger.info(f"[TRADE SCHEDULE] Agendamento cancelado para {user_id}")
                except Exception as e:
                    logger.error(f"[TRADE SCHEDULE] Erro ao executar trade agendado: {e}")
                finally:
                    if schedule_key in self._scheduled_trades:
                        del self._scheduled_trades[schedule_key]

            task = asyncio.create_task(_execute_at_scheduled_time())
            self._scheduled_trades[schedule_key] = task

            logger.info(
                f"[TRADE SCHEDULE] {user_id}: {signal.get('asset')} agendado para "
                f"{execute_at.strftime('%H:%M:%S.%f')[:-3]} | "
                f"aguardando {seconds_to_next:.3f}s | "
                f"anchor={datetime.fromtimestamp(anchor_ts).strftime('%H:%M:%S.%f')[:-3]}"
            )

            return {
                "user_id": user_id,
                "asset": signal.get("asset"),
                "direction": direction.value,
                "scheduled": True,
                "execute_at": execute_at.isoformat(),
                "execute_timestamp": execute_timestamp,
                "wait_seconds": seconds_to_next,
                "signal_id": signal_id,
                "mode": "oncandle",
                "message": f"Trade agendado para {execute_at.strftime('%H:%M:%S.%f')[:-3]}"
            }

        except Exception as e:
            logger.error(f"[TRADE SCHEDULE] Erro ao agendar trade: {e}")
            return None

    async def _load_fresh_config(self, user_id: str) -> Optional[Any]:
        """Busca config atualizada diretamente do banco (ignora cache do autotrade_manager)."""
        try:
            from sqlalchemy import select
            from ..database.models import AutotradeConfig
            async with self.db_manager.get_session() as session:
                import uuid as _uuid
                result = await session.execute(
                    select(AutotradeConfig).where(AutotradeConfig.user_id == _uuid.UUID(user_id))
                )
                row = result.scalar_one_or_none()
                if row:
                    logger.debug(
                        f"[CONFIG] Config fresca do banco para {user_id}: "
                        f"mart={row.martingale_enabled} soros={row.soros_enabled} "
                        f"reduce={row.reduce_enabled} amount={row.amount}"
                    )
                return row
        except Exception as e:
            logger.error(f"[CONFIG] Erro ao buscar config fresca para {user_id}: {e}")
            return None

    async def _execute_for_user(
        self,
        user_id: str,
        user_config: Any,
        signal: Dict[str, Any],
        direction: OrderDirection
    ) -> Optional[Dict[str, Any]]:
        """Executa trade para um usuário específico usando ConnectionManager"""

        # Garantir que o estado foi registrado
        if user_id not in self._user_states:
            self._user_states[user_id] = UserTradeState(user_id=user_id, config=user_config)

        # Carregar estado persistido do banco (apenas na primeira vez)
        await self._load_session_state(user_id)

        state = self._user_states[user_id]
        # Atualizar config com cache: evita recarregar a cada sinal
        import time as _time
        now_ts = _time.time()
        cached = self._config_cache.get(user_id)
        if not cached or (now_ts - cached[1]) > self._config_cache_ttl:
            # Cache expirado ou invalidado — buscar config fresca do banco
            fresh_config = await self._load_fresh_config(user_id)
            if fresh_config:
                self._config_cache[user_id] = (fresh_config, now_ts)
                state.config = fresh_config
                logger.debug(f"[CONFIG] Config recarregada do banco para {user_id}: mart={getattr(fresh_config,'martingale_enabled',False)} soros={getattr(fresh_config,'soros_enabled',False)}")
                # Limpar estado inconsistente: se soros/martingale foi desativado, resetar níveis
                cfg = fresh_config
                if not getattr(cfg, 'soros_enabled', False) and state.soros_level > 0:
                    logger.info(f"[CONFIG] Soros desativado — resetando soros_level={state.soros_level} e amount_current para base")
                    state.soros_level = 0
                    state.amount_current = float(getattr(cfg, 'amount', 1.0))
                if not getattr(cfg, 'martingale_enabled', False) and state.martingale_level > 0:
                    logger.info(f"[CONFIG] Martingale desativado — resetando martingale_level={state.martingale_level}")
                    state.martingale_level = 0
                    state.amount_current = float(getattr(cfg, 'amount', 1.0))
            else:
                # Fallback: usar config passada pelo autotrade_manager
                self._config_cache[user_id] = (user_config, now_ts)
                state.config = user_config
        else:
            state.config = cached[0]

        # Verificar se stop foi atingido (modo hard)
        if state.stop_triggered:
            logger.info(f"[TRADE] {user_id}: stop '{state.stop_type}' ativo — executando parada completa")
            asyncio.create_task(self._handle_stop_triggered(user_id, state.stop_type or "unknown"))
            return None

        if state.last_trade_time:
            elapsed = (datetime.now() - state.last_trade_time).total_seconds()
            
            # Cooldown do sistema (timeframe da estratégia) — por estratégia, independente
            signal_strategy = signal.get("strategy", "")
            sys_cd = self._get_system_cooldown(signal)
            if signal_strategy and state.last_trade_time_by_strategy:
                last_for_strategy = state.last_trade_time_by_strategy.get(signal_strategy)
                if last_for_strategy:
                    elapsed_strategy = (datetime.now() - last_for_strategy).total_seconds()
                    if elapsed_strategy < sys_cd:
                        logger.info(f"[TRADE] Cooldown sistema ativo para {user_id} ({elapsed_strategy:.0f}s < {sys_cd}s | estratégia={signal_strategy})")
                        return None
            
            # Cooldown do usuário (configurado no banco) — intervalo mínimo entre trades (qualquer estratégia)
            usr_cd = state.user_cooldown_seconds or 0
            if elapsed < usr_cd:
                logger.info(f"[TRADE] Cooldown usuário ativo para {user_id} ({elapsed:.0f}s < {usr_cd}s)")
                return None
        
        # Verificar se usuário está conectado via ConnectionManager
        if not self.connection_manager.is_connected(user_id):
            logger.warning(f"[TRADE] Usuário {user_id} não está conectado")
            return None
        
        # Obter cliente do ConnectionManager
        client = self.connection_manager.get_client(user_id)
        if not client or not hasattr(client, 'is_connected') or not client.is_connected:
            logger.warning(f"[TRADE] Cliente não disponível para {user_id}")
            return None
        
        # Verificar saldo do usuário
        try:
            balance = await client.get_balance()
            user_operator = getattr(user_config, 'operator', 'demo')  # demo ou real
            
            # Verificar se saldo corresponde ao modo selecionado
            if balance.is_demo and user_operator == 'real':
                logger.warning(f"[TRADE] Usuário {user_id} em modo REAL mas conectado em DEMO")
                return None
            elif not balance.is_demo and user_operator == 'demo':
                logger.warning(f"[TRADE] Usuário {user_id} em modo DEMO mas conectado em REAL")
                return None
            
            # Verificar saldo suficiente
            if balance.balance <= 0:
                logger.warning(
                    f"[TRADE] Saldo insuficiente para {user_id} | "
                    f"Saldo: ${balance.balance:.2f} | Modo: {user_operator}"
                )
                return None

            # Inicializar pico de saldo para Stop Médio (captura saldo antes do primeiro trade)
            if state.session_peak_balance is None:
                state.session_peak_balance = float(balance.balance)
                logger.info(f"[STOP MÉDIO] Pico inicial registrado para {user_id}: ${state.session_peak_balance:.2f}")

            logger.debug(
                f"[TRADE] Saldo OK para {user_id}: ${balance.balance:.2f} | Modo: {user_operator}"
            )
            
        except Exception as e:
            logger.warning(f"[TRADE] Erro ao verificar saldo de {user_id}: {e}")
            # Continua mesmo sem verificar saldo (fallback)
        
        try:
            asset = signal.get("asset")
            # Calcular amount dinâmico (martingale / soros / reduce / base)
            # Usar state.config (já atualizado com config fresca do banco)
            amount = self._compute_amount(state, state.config)
            if amount <= 0:
                amount = float(getattr(user_config, 'amount', 1.0))
            # Duration vem do timeframe da estratégia (scalping = 5s)
            duration = signal.get("timeframe", self.default_duration)
            if duration <= 0:
                duration = self.default_duration
            
            if amount <= 0:
                logger.warning(f"[TRADE] Valor inválido para {user_id}: {amount}")
                return None
            
            logger.info(
                f"[TRADE] Executando para {user_id}: "
                f"{asset} | {direction.value} | ${amount} | {duration}s"
            )
            
            # Executar ordem via cliente do ConnectionManager
            order_result = await client.place_order(
                asset=asset,
                amount=amount,
                direction=direction,
                duration=duration
            )
            
            # Registrar ordem ativa para rastreamento
            placed_at = datetime.now()
            expires_at = placed_at + timedelta(seconds=duration)
            
            active_order = ActiveOrder(
                order_id=order_result.order_id,
                user_id=user_id,
                asset=asset,
                direction=direction.value,
                amount=amount,
                duration=duration,
                placed_at=placed_at,
                expires_at=expires_at,
                signal_id=signal.get("signal_id")
            )
            self._active_orders[order_result.order_id] = active_order
            self._order_to_user[order_result.order_id] = user_id
            
            # Registrar callback no cliente para receber notificação de ordem fechada
            # Usamos uma referência nomeada para poder remover depois
            _cb_ref = None
            async def _make_callback(data, oid=order_result.order_id):
                await self._on_order_closed_callback(oid, data, client, _cb_ref)
            _cb_ref = _make_callback

            client.add_event_callback('order_closed', _make_callback)
            
            # Iniciar task em background para verificar resultado
            asyncio.create_task(self._track_order_result(client, order_result.order_id, duration))
            
            # Atualizar estado de cooldown
            system_cooldown = self._get_system_cooldown(signal)
            user_cooldown = self._get_user_cooldown(user_id, user_config)
            
            now = datetime.now()
            strategy_name = signal.get("strategy", "")
            state.last_trade_time = now
            state.system_cooldown_seconds = system_cooldown
            state.user_cooldown_seconds = user_cooldown
            if strategy_name:
                state.last_trade_time_by_strategy[strategy_name] = now
            
            strategy = signal.get("strategy", "?")
            logger.info(f"[TRADE] Cooldown definido para {user_id}: sistema={system_cooldown}s (tf={signal.get('timeframe')}s/{strategy}) | usuário={user_cooldown}s")
            
            result = {
                "user_id": user_id,
                "asset": asset,
                "direction": direction.value,
                "amount": amount,
                "duration": duration,
                "order_id": order_result.order_id,
                "status": order_result.status.value,
                "confidence": signal.get("confidence"),
                "signal_id": signal.get("signal_id"),
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(
                f"[TRADE] Ordem executada: {order_result.order_id} | "
                f"Status: {order_result.status.value} | Expira em: {duration}s"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[TRADE] Erro ao executar trade para {user_id}: {e}")
            return None
    
    def register_user(self, user_id: str, config: Any):
        """Registra um usuário para execução de trades (apenas estado, não conecta)"""
        if user_id not in self._user_states:
            self._user_states[user_id] = UserTradeState(user_id=user_id, config=config)
            logger.debug(f"[TradeExecutor] Usuário {user_id} registrado")

    def invalidate_config_cache(self, user_id: str):
        """Invalida cache de config de um usuário (chamado após update de config)"""
        self._config_cache.pop(user_id, None)
        logger.debug(f"[TradeExecutor] Cache de config invalidado para {user_id}")
        logger.debug(f"[TradeExecutor] Cache de config invalidado para {user_id}")
    
    def unregister_user(self, user_id: str):
        """Remove um usuário do executor"""
        if user_id in self._user_states:
            del self._user_states[user_id]
            self._config_cache.pop(user_id, None)
            logger.debug(f"[TradeExecutor] Usuário {user_id} removido")

    async def _handle_stop_triggered(self, user_id: str, stop_type: str) -> None:
        """
        Ação completa ao atingir um stop hard:
        1. Desliga autotrade=0 no banco
        2. Invalida cache da estratégia no strategy_manager
        3. Desconecta o WebSocket do usuário da corretora
        4. Remove estado em memória do executor
        """
        logger.warning(f"[STOP] {user_id}: executando parada completa (stop='{stop_type}')")

        # 1. Desligar autotrade no banco
        try:
            from ..database.autotrade_dao import autotrade_dao as _atdao
            await _atdao.update_config(user_id=user_id, autotrade=0)
            logger.info(f"[STOP] autotrade=0 salvo no banco para {user_id}")
        except Exception as e:
            logger.error(f"[STOP] Erro ao desligar autotrade no banco para {user_id}: {e}")

        # 2. Invalidar cache da estratégia
        try:
            from ..core.engine import engine as _engine
            if _engine and _engine.strategy_manager:
                _engine.strategy_manager.invalidate_user_strategy_cache(user_id)
        except Exception:
            pass

        # 3. Desconectar WebSocket da corretora
        try:
            if self.connection_manager and self.connection_manager.is_connected(user_id):
                await self.connection_manager.disconnect(user_id)
                logger.info(f"[STOP] WebSocket desconectado para {user_id}")
        except Exception as e:
            logger.error(f"[STOP] Erro ao desconectar WS para {user_id}: {e}")

        # 4. Remover estado em memória
        self.unregister_user(user_id)
        self._config_cache.pop(user_id, None)
    
    async def _on_order_closed_callback(self, order_id: str, data: Any, client=None, callback_ref=None):
        """
        Callback chamado quando o cliente WS recebe notificação de ordem fechada.
        Remove o próprio callback após processar para evitar memory leak.
        """
        try:
            # Verificar se ainda estamos rastreando esta ordem
            if order_id not in self._active_orders:
                logger.debug(f"[TRADE] Ordem {order_id} já processada ou não rastreada")
                # Remover callback mesmo assim para evitar memory leak
                if client is not None and callback_ref is not None:
                    client.remove_event_callback('order_closed', callback_ref)
                return
            
            active_order = self._active_orders[order_id]
            
            # Ignorar placeholders do websocket (resultado real vem depois via OrderResult)
            if isinstance(data, dict) and data.get('_placeholder'):
                logger.debug(f"[RESULT] Ordem {order_id}: placeholder ignorado, aguardando OrderResult real")
                # NÃO remover callback — resultado real ainda vai chegar
                # NÃO marcar como processado
                return

            # Auto-remover o callback agora que temos dados reais
            if client is not None and callback_ref is not None:
                client.remove_event_callback('order_closed', callback_ref)

            # Marcar como processado pelo callback para evitar processamento duplo
            active_order.processed_by_callback = True

            # Extrair profit — data pode ser OrderResult object ou dict
            if isinstance(data, dict):
                profit = float(data.get('profit', 0))
            elif hasattr(data, 'profit') and data.profit is not None:
                profit = float(data.profit)
            else:
                profit = 0.0

            # Verificar se a ordem fechada corresponde a esta ordem (pelo order_id do OrderResult)
            if hasattr(data, 'order_id') and data.order_id != order_id:
                # Ordem diferente — não processar
                return
            
            # Log completo do data para diagnóstico
            logger.info(f"[RESULT RAW] Ordem {order_id}: type={type(data).__name__} data={data}")
            
            # Determinar resultado — usar status do OrderResult se disponível
            # (mais confiável que profit, pois PocketOption retorna profit=0 em losses demo)
            if hasattr(data, 'status') and data.status is not None:
                from ..pocketoption.models import OrderStatus
                if data.status == OrderStatus.WIN:
                    result = 'win'
                    # Em wins demo, profit pode vir como 0 — calcular pelo payout se necessário
                    if profit <= 0 and hasattr(data, 'profit') and data.profit:
                        profit = float(data.profit)
                    # Se ainda <= 0, não temos como calcular o lucro exato — manter 0 (não afeta stop gain negativamente)
                elif data.status == OrderStatus.LOSE:
                    result = 'loss'
                    # Em losses, profit pode ser 0 ou negativo — normalizar para negativo
                    if profit >= 0:
                        profit = -active_order.amount
                else:
                    result = 'draw'
            elif isinstance(data, dict) and 'result' in data:
                result = data['result']  # 'win', 'loss', 'draw'
            elif isinstance(data, dict):
                # Dict bruto do successcloseOrder — verificar campos conhecidos da PocketOption
                # A PocketOption usa: profit > 0 = win, profit < 0 = loss, profit == 0 = loss (não draw)
                win_amount = data.get('win', data.get('win_amount', None))
                if win_amount is not None:
                    # Campo 'win' presente: > 0 = win, 0 = loss
                    if float(win_amount) > 0:
                        result = 'win'
                        profit = float(win_amount) - active_order.amount  # lucro líquido
                    else:
                        result = 'loss'
                        profit = -active_order.amount
                elif profit > 0:
                    result = 'win'
                elif profit < 0:
                    result = 'loss'
                else:
                    # profit == 0 em demo = loss (PocketOption não retorna negativo em demo)
                    result = 'loss'
                    profit = -active_order.amount
            else:
                # Fallback: usar profit
                if profit > 0:
                    result = 'win'
                elif profit < 0:
                    result = 'loss'
                else:
                    result = 'draw'
            
            logger.debug(f"[RESULT] Ordem {order_id}: status={getattr(data,'status',None)} profit={profit:.2f} → result={result}")
            
            # Atualizar ordem
            active_order.result = result
            active_order.profit = profit
            
            # Mover para histórico
            self._completed_orders.append(active_order)
            if len(self._completed_orders) > 100:
                self._completed_orders = self._completed_orders[-100:]
            
            del self._active_orders[order_id]
            if order_id in self._order_to_user:
                del self._order_to_user[order_id]
            
            logger.info(
                f"[TRADE RESULT] Ordem {order_id} finalizada via callback: "
                f"{result} | Profit: ${profit:.2f} | Ativo: {active_order.asset}"
            )
            
            # Processar lógica de gestão de banca (martingale/soros/reduce/stops)
            user_id_for_result = active_order.user_id
            if user_id_for_result and client:
                asyncio.create_task(self._process_trade_result(user_id_for_result, result, profit, client))
            
        except Exception as e:
            logger.error(f"[TRADE] Erro ao processar callback de ordem fechada: {e}")
    
    async def sync_pending_orders(self, user_id: str, client: Any):
        """
        Sincroniza ordens pendentes após reconexão.
        Consulta o histórico do cliente para obter resultados de ordens ativas.
        
        Args:
            user_id: ID do usuário que reconectou
            client: Cliente PocketOption reconectado
        """
        try:
            # Verificar ordens ativas deste usuário
            user_orders = [
                (oid, order) for oid, order in self._active_orders.items()
                if self._order_to_user.get(oid) == user_id
            ]
            
            if not user_orders:
                logger.debug(f"[TRADE SYNC] Nenhuma ordem pendente para {user_id}")
                return
            
            logger.info(f"[TRADE SYNC] Sincronizando {len(user_orders)} ordens pendentes para {user_id}")
            
            # Obter histórico de ordens fechadas do cliente
            # O cliente armazena em _order_results
            for order_id, active_order in user_orders:
                # Verificar se o cliente tem o resultado
                if hasattr(client, '_order_results') and order_id in client._order_results:
                    result = client._order_results[order_id]
                    
                    # Determinar resultado
                    profit = result.profit if result.profit else 0
                    if profit > 0:
                        status = 'win'
                    elif profit < 0:
                        status = 'loss'
                    else:
                        status = 'draw'
                    
                    # Atualizar ordem
                    active_order.result = status
                    active_order.profit = profit
                    
                    # Mover para histórico
                    self._completed_orders.append(active_order)
                    if len(self._completed_orders) > 100:
                        self._completed_orders = self._completed_orders[-100:]
                    
                    del self._active_orders[order_id]
                    if order_id in self._order_to_user:
                        del self._order_to_user[order_id]
                    
                    logger.info(
                        f"[TRADE SYNC] Ordem {order_id} sincronizada: "
                        f"{status} | Profit: ${profit:.2f} | Ativo: {active_order.asset}"
                    )
                else:
                    # Ordem ainda não tem resultado - manter ativa
                    logger.debug(f"[TRADE SYNC] Ordem {order_id} ainda sem resultado no cliente")
                    
        except Exception as e:
            logger.error(f"[TRADE SYNC] Erro ao sincronizar ordens de {user_id}: {e}")
    
    async def _track_order_result(self, client, order_id: str, duration: int):
        """
        Rastreia o resultado de uma ordem após a expiração.
        Aguarda o tempo de expiração + margem e consulta o resultado.
        Pula se já foi processada pelo callback.
        """
        try:
            # Aguardar expiração do trade + 2 segundos de margem
            wait_time = duration + 2
            logger.debug(f"[TRADE TRACK] Aguardando {wait_time}s para verificar ordem {order_id}")
            await asyncio.sleep(wait_time)
            
            # Verificar se já foi processada pelo callback
            if order_id not in self._active_orders:
                logger.debug(f"[TRADE TRACK] Ordem {order_id} já foi processada (provavelmente pelo callback)")
                return
            
            active_order = self._active_orders[order_id]
            
            # Se já foi processada pelo callback, pular
            if active_order.processed_by_callback:
                logger.debug(f"[TRADE TRACK] Ordem {order_id} já processada pelo callback, pulando polling")
                return
            
            # Verificar resultado usando check_win do cliente
            result = await client.check_win(order_id, max_wait_time=30.0)
            
            if result and result.get("completed"):
                # Atualizar ordem ativa
                if order_id in self._active_orders:
                    active_order = self._active_orders[order_id]
                    active_order.result = result.get("result", "unknown")
                    active_order.profit = result.get("profit", 0)
                    
                    # Mover para histórico de completadas
                    self._completed_orders.append(active_order)
                    if len(self._completed_orders) > 100:
                        self._completed_orders = self._completed_orders[-100:]
                    
                    del self._active_orders[order_id]
                    
                    logger.info(
                        f"[TRADE RESULT] Ordem {order_id} finalizada via polling: "
                        f"{active_order.result} | Profit: ${active_order.profit:.2f} | "
                        f"Ativo: {active_order.asset} | Direção: {active_order.direction}"
                    )
                    
                    # Processar lógica de gestão de banca
                    user_id_for_result = active_order.user_id
                    if user_id_for_result:
                        asyncio.create_task(self._process_trade_result(
                            user_id_for_result, active_order.result, active_order.profit or 0.0, client
                        ))
                    
            else:
                logger.warning(f"[TRADE TRACK] Timeout ou erro ao verificar ordem {order_id}")
                # Manter em ativas por mais tempo para tentar novamente depois
                
        except Exception as e:
            logger.error(f"[TRADE TRACK] Erro ao rastrear ordem {order_id}: {e}")
    
    def get_active_orders(self) -> List[ActiveOrder]:
        """Retorna lista de ordens ativas"""
        return list(self._active_orders.values())
    
    def get_completed_orders(self) -> List[ActiveOrder]:
        """Retorna histórico de ordens finalizadas"""
        return self._completed_orders.copy()
    
    def get_order(self, order_id: str) -> Optional[ActiveOrder]:
        """Retorna uma ordem específica (ativa ou completada)"""
        if order_id in self._active_orders:
            return self._active_orders[order_id]
        
        for order in self._completed_orders:
            if order.order_id == order_id:
                return order
        
        return None
    
    def get_active_users(self) -> List[str]:
        """Retorna lista de IDs de usuários registrados"""
        return list(self._user_states.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do executor"""
        # Calcular estatísticas de win/loss
        wins = sum(1 for o in self._completed_orders if o.result == "win")
        losses = sum(1 for o in self._completed_orders if o.result == "loss")
        draws = sum(1 for o in self._completed_orders if o.result == "draw")
        total_profit = sum(o.profit or 0 for o in self._completed_orders)
        
        return {
            "registered_users": len(self._user_states),
            "running": self._running,
            "has_connection_manager": self.connection_manager is not None,
            "active_orders": len(self._active_orders),
            "completed_orders": len(self._completed_orders),
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "total_profit": total_profit,
            "win_rate": wins / (wins + losses) if (wins + losses) > 0 else 0
        }
