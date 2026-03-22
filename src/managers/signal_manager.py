"""
Gerenciador de Sinais de Trading
Gerencia emissão, distribuição e processamento de sinais para múltiplos usuários
"""
import asyncio
import uuid
from typing import Dict, List, Callable, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
from ..managers.log_manager import get_manager_logger

logger = get_manager_logger("signal_manager")


class SignalType(Enum):
    """Tipos de sinais"""
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"
    STRONG_BUY = "strong_buy"
    STRONG_SELL = "strong_sell"


class SignalStatus(Enum):
    """Status do sinal"""
    PENDING = "pending"
    EXECUTED = "executed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class Signal:
    """Representa um sinal de trading"""
    id: str
    user_id: str
    asset: str
    signal_type: SignalType
    timeframe: int
    indicators: List[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0 a 1.0
    entry_price: Optional[float] = None
    expiration_time: Optional[datetime] = None
    status: SignalStatus = SignalStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    result: Optional[str] = None  # win, loss, draw
    profit_loss: Optional[float] = None


@dataclass
class SignalConfig:
    """Configuração de geração de sinais para um usuário"""
    user_id: str
    asset: str
    timeframe: int
    indicators: List[Dict[str, Any]]
    min_confidence: float = 0.7
    signal_types: List[SignalType] = field(default_factory=lambda: [SignalType.BUY, SignalType.SELL])
    enabled: bool = True
    max_concurrent_signals: int = 3
    cooldown_seconds: int = 60
    last_signal_time: Optional[datetime] = None


class SignalManager:
    """
    Gerenciador central de sinais
    Suporta emissão simultânea de sinais para múltiplos usuários
    """
    
    def __init__(self, max_signals_per_user: int = 100):
        self.max_signals_per_user = max_signals_per_user
        self.signals: Dict[str, Signal] = {}
        self.user_signals: Dict[str, List[str]] = {}  # user_id -> signal_ids
        self.user_configs: Dict[str, List[SignalConfig]] = {}  # user_id -> configs
        self._subscribers: Dict[str, List[Callable]] = {}  # event -> callbacks
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._trade_executor: Optional[Any] = None  # Engine reference (legacy support)
        self._autotrade_checker: Optional[Any] = None  # Engine reference (novo - engine gerencia autotrade)
        
    def set_trade_executor(self, trade_executor: Any):
        """Define o TradeExecutor para executar trades automaticamente (legacy)"""
        self._trade_executor = trade_executor
        
    def set_autotrade_checker(self, engine: Any):
        """Define a Engine para execução automática de trades (engine gerencia autotrade)"""
        self._autotrade_checker = engine
        logger.info("[SignalManager] Engine configurada para execução automática")
        
    async def start(self):
        """Inicia o gerenciador de sinais"""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_signals())
        logger.info("SignalManager iniciado")
        
    async def stop(self):
        """Para o gerenciador de sinais"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("SignalManager parado")
        
    async def add_user_config(self, config: SignalConfig):
        """Adiciona configuração de sinais para um usuário"""
        if config.user_id not in self.user_configs:
            self.user_configs[config.user_id] = []
        
        # Remover configuração anterior para o mesmo ativo/timeframe se existir
        self.user_configs[config.user_id] = [
            c for c in self.user_configs[config.user_id]
            if not (c.asset == config.asset and c.timeframe == config.timeframe)
        ]
        
        self.user_configs[config.user_id].append(config)
        logger.info(f"Configuração adicionada para usuário {config.user_id}: {config.asset}/{config.timeframe}")
        
    async def remove_user_config(self, user_id: str, asset: Optional[str] = None):
        """Remove configuração de sinais de um usuário"""
        if user_id in self.user_configs:
            if asset:
                self.user_configs[user_id] = [
                    c for c in self.user_configs[user_id] if c.asset != asset
                ]
            else:
                del self.user_configs[user_id]
                
    async def process_indicator_result(self, user_id: str, asset: str, timeframe: int, 
                                       indicator_result: Dict[str, Any]):
        """Processa resultado de indicador e gera sinal se necessário"""
        if user_id not in self.user_configs:
            return
            
        configs = [c for c in self.user_configs[user_id] 
                   if c.asset == asset and c.timeframe == timeframe and c.enabled]
        
        for config in configs:
            signal = await self._evaluate_signal(config, indicator_result)
            if signal and signal.confidence >= config.min_confidence:
                await self._emit_signal(signal)
                
    async def _evaluate_signal(self, config: SignalConfig, 
                               indicator_result: Dict[str, Any]) -> Optional[Signal]:
        """Avalia se deve gerar um sinal baseado no resultado do indicador"""
        # Verificar cooldown
        if config.last_signal_time:
            elapsed = (datetime.now() - config.last_signal_time).total_seconds()
            if elapsed < config.cooldown_seconds:
                return None
                
        # Verificar limite de sinais ativos
        active_signals = self._get_active_signals_count(config.user_id)
        if active_signals >= config.max_concurrent_signals:
            return None
            
        # Avaliar sinal baseado nos indicadores
        signal_type, confidence = self._calculate_signal_type(indicator_result)
        
        if signal_type not in config.signal_types or confidence < config.min_confidence:
            return None
            
        signal = Signal(
            id=str(uuid.uuid4()),
            user_id=config.user_id,
            asset=config.asset,
            signal_type=signal_type,
            timeframe=config.timeframe,
            indicators=list(indicator_result.keys()),
            confidence=confidence,
            metadata=indicator_result
        )
        
        config.last_signal_time = datetime.now()
        return signal
        
    def _calculate_signal_type(self, indicator_result: Dict[str, Any]) -> tuple:
        """Calcula o tipo de sinal e confiança baseado nos indicadores"""
        buy_signals = 0
        sell_signals = 0
        total_weight = 0
        
        weights = {
            'RSI': 1.0,
            'MACD': 1.2,
            'SMA': 0.8,
            'EMA': 0.8,
            'BB': 1.0,
            'Stochastic': 0.9
        }
        
        for indicator, data in indicator_result.items():
            weight = weights.get(indicator, 1.0)
            signal = data.get('signal', 'neutral')
            
            if signal in ['buy', 'strong_buy']:
                buy_signals += weight
                if signal == 'strong_buy':
                    buy_signals += weight * 0.5
            elif signal in ['sell', 'strong_sell']:
                sell_signals += weight
                if signal == 'strong_sell':
                    sell_signals += weight * 0.5
                    
            total_weight += weight
            
        if total_weight == 0:
            return SignalType.NEUTRAL, 0.0
            
        buy_ratio = buy_signals / total_weight
        sell_ratio = sell_signals / total_weight
        
        if buy_ratio > 0.7:
            return SignalType.STRONG_BUY, buy_ratio
        elif buy_ratio > 0.5:
            return SignalType.BUY, buy_ratio
        elif sell_ratio > 0.7:
            return SignalType.STRONG_SELL, sell_ratio
        elif sell_ratio > 0.5:
            return SignalType.SELL, sell_ratio
        else:
            return SignalType.NEUTRAL, max(buy_ratio, sell_ratio)
            
    async def _emit_signal(self, signal: Signal):
        """Emite um sinal para todos os subscribers"""
        self.signals[signal.id] = signal
        
        if signal.user_id not in self.user_signals:
            self.user_signals[signal.user_id] = []
        self.user_signals[signal.user_id].append(signal.id)
        
        # Notificar subscribers
        await self._notify_subscribers('signal_created', signal)
        
        logger.info(f"Sinal emitido: {signal.id} ({signal.signal_type.value}) para {signal.user_id}/{signal.asset}")
        
    async def _notify_subscribers(self, event: str, data: Any):
        """Notifica subscribers de um evento"""
        callbacks = self._subscribers.get(event, [])
        for callback in callbacks:
            try:
                await callback(data)
            except Exception as e:
                logger.error(f"Erro ao notificar subscriber: {e}")
                
    def subscribe(self, event: str, callback: Callable):
        """Subscreve a eventos de sinais"""
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(callback)
        
    def unsubscribe(self, event: str, callback: Callable):
        """Remove subscrição de eventos"""
        if event in self._subscribers and callback in self._subscribers[event]:
            self._subscribers[event].remove(callback)
            
    def _get_active_signals_count(self, user_id: str) -> int:
        """Conta sinais ativos de um usuário"""
        signal_ids = self.user_signals.get(user_id, [])
        return sum(
            1 for sid in signal_ids
            if sid in self.signals and self.signals[sid].status == SignalStatus.PENDING
        )
        
    async def _cleanup_expired_signals(self):
        """Remove sinais expirados periodicamente"""
        while self._running:
            try:
                await asyncio.sleep(300)  # Limpar a cada 5 minutos
                
                expired_signals = []
                for signal_id, signal in self.signals.items():
                    if signal.status == SignalStatus.PENDING:
                        # Verificar se expirou (mais de 10 minutos)
                        elapsed = (datetime.now() - signal.created_at).total_seconds()
                        if elapsed > 600:
                            signal.status = SignalStatus.EXPIRED
                            expired_signals.append(signal_id)
                            
                if expired_signals:
                    logger.info(f"{len(expired_signals)} sinais expirados removidos")
                    
            except Exception as e:
                logger.error(f"Erro na limpeza de sinais: {e}")
                
    def get_user_signals(self, user_id: str, status: Optional[SignalStatus] = None) -> List[Signal]:
        """Obtém sinais de um usuário"""
        signal_ids = self.user_signals.get(user_id, [])
        signals = [self.signals[sid] for sid in signal_ids if sid in self.signals]
        
        if status:
            signals = [s for s in signals if s.status == status]
            
        return sorted(signals, key=lambda x: x.created_at, reverse=True)
    
    async def setup_user_complete(self, user_id: str, config: "SignalConfig"):
        """Configura geração completa de sinais para um usuário
        
        Inclui:
        - Configura indicadores de análise
        - Registra usuário para receber sinais
        - Inicializa processamento de indicadores
        """
        logger.info(f"[SignalManager] Configurando sinais completos para {user_id}")
        
        # Registrar configuração do usuário
        self.user_configs[user_id] = config
        if user_id not in self.user_signals:
            self.user_signals[user_id] = []
        
        logger.info(f"[SignalManager] Sinais configurados para {user_id}")
        
    async def register_signal(self, signal: Signal) -> bool:
        """Registra um sinal externo (ex: de StrategyManager)"""
        self.signals[signal.id] = signal
        
        if signal.user_id not in self.user_signals:
            self.user_signals[signal.user_id] = []
        self.user_signals[signal.user_id].append(signal.id)
        
        # Notificar subscribers
        await self._notify_subscribers('signal_created', signal)
        
        # Log detalhado
        direction = "CALL" if signal.signal_type == SignalType.BUY else "PUT" if signal.signal_type == SignalType.SELL else "NEUTRAL"
        reason = signal.metadata.get("reason", "N/A")
        indicators = signal.metadata.get("indicators", {})
        strategy = signal.metadata.get("strategy", "N/A")
        
        logger.info(f"Sinal registrado: {signal.id[:8]}... | {signal.asset} | {direction} | Conf: {signal.confidence:.2f} | Estratégia: {strategy} | {reason}")
        logger.info(f"  Indicadores: {indicators}")
        logger.info(f"  Entry Price: {signal.entry_price}")
        
        # Executar trade automaticamente via Engine (que gerencia autotrade internamente)
        if self._autotrade_checker and signal.signal_type != SignalType.NEUTRAL:
            signal_data = {
                "signal_id": signal.id,
                "asset": signal.asset,
                "direction": direction,
                "confidence": signal.confidence,
                "entry_price": signal.entry_price,
                "strategy": signal.metadata.get("strategy", "Scalping5s"),
                "reason": reason,
                "indicators": indicators,
                "timeframe": signal.timeframe
            }
            
            try:
                # Executar via Engine (delega ao TradeExecutor interno)
                results = await self._autotrade_checker.execute_signal(signal_data)
                if results:
                    logger.info(f"[AUTO TRADE] {len(results)} trades executados para sinal {signal.id[:8]}")
            except Exception as e:
                logger.error(f"Erro ao executar trade via Engine: {e}")
        
        # Fallback direto para TradeExecutor (sem autotrade, apenas execução)
        elif self._trade_executor and signal.signal_type != SignalType.NEUTRAL:
            signal_data = {
                "signal_id": signal.id,
                "asset": signal.asset,
                "direction": direction,
                "confidence": signal.confidence,
                "entry_price": signal.entry_price,
                "strategy": signal.metadata.get("strategy", "Scalping5s"),
                "reason": reason,
                "indicators": indicators,
                "timeframe": signal.timeframe
            }
            
            try:
                results = await self._trade_executor.execute_signal(signal_data)
                if results:
                    logger.info(f"[AUTO TRADE] {len(results)} trades executados para sinal {signal.id[:8]}")
            except Exception as e:
                logger.error(f"Erro ao executar trade via TradeExecutor: {e}")
        
        return True
        
    def update_signal_result(self, signal_id: str, result: str, profit_loss: float):
        """Atualiza resultado de um sinal executado"""
        if signal_id in self.signals:
            signal = self.signals[signal_id]
            signal.status = SignalStatus.EXECUTED
            signal.result = result
            signal.profit_loss = profit_loss
            signal.executed_at = datetime.now()
            
    def get_stats(self) -> Dict:
        """Retorna estatísticas do gerenciador"""
        total = len(self.signals)
        pending = sum(1 for s in self.signals.values() if s.status == SignalStatus.PENDING)
        executed = sum(1 for s in self.signals.values() if s.status == SignalStatus.EXECUTED)
        expired = sum(1 for s in self.signals.values() if s.status == SignalStatus.EXPIRED)
        
        wins = sum(1 for s in self.signals.values() if s.result == "win")
        losses = sum(1 for s in self.signals.values() if s.result == "loss")
        
        return {
            "total_signals": total,
            "pending": pending,
            "executed": executed,
            "expired": expired,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / (wins + losses) if (wins + losses) > 0 else 0,
            "active_users": len(self.user_configs)
        }
