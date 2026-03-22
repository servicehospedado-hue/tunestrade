"""
Gerenciador de Conexões WSS - Revisado e Otimizado
Gerencia pool de conexões WebSocket com PocketOption
Com tratamento robusto de erros, reconexão inteligente e monitoramento
"""
import asyncio
import random
from typing import Dict, Optional, Set, Callable, Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..config.settings import ConnectionManagerConfig
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from ..managers.log_manager import get_manager_logger, log_manager

logger = get_manager_logger("connection_manager")


class ConnectionState(Enum):
    """Estados da conexão"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    CLOSING = "closing"


@dataclass
class Connection:
    """Representa uma conexão WSS"""
    user_id: str
    ssid: str
    is_demo: bool = True
    client: Any = None
    state: ConnectionState = ConnectionState.DISCONNECTED
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    last_ping: Optional[datetime] = None
    reconnect_count: int = 0
    max_reconnects: int = 5
    reconnect_delay: int = 5  # segundos base
    reconnect_max_delay: int = 60  # delay máximo
    heartbeat_interval: int = 20  # segundos
    heartbeat_timeout: int = 30  # segundos
    connection_timeout: int = 30  # segundos
    _heartbeat_task: Optional[asyncio.Task] = None
    _message_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    _callbacks: Dict[str, list] = field(default_factory=dict)
    _ping_count: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    intentional_disconnect: bool = False  # Flag para desconexão intencional


class ConnectionError(Exception):
    """Erro de conexão"""
    pass


class ConnectionManager:
    """
    Gerenciador central de conexões WSS
    Suporta múltiplas conexões simultâneas com reconexão automática robusta
    """
    
    def __init__(self, config: Optional['ConnectionManagerConfig'] = None):
        self._data_collector = None  # DataCollectorManager para processar ticks
        # Configurações
        if config:
            self.max_connections = config.max_connections
            self.heartbeat_interval = config.heartbeat_interval
            self.heartbeat_timeout = config.heartbeat_timeout
            self.max_reconnects = config.max_reconnects
            self.reconnect_delay = config.reconnect_delay
            self.reconnect_max_delay = config.reconnect_max_delay
            self.reconnect_jitter = config.reconnect_jitter
            self.connection_timeout = config.connection_timeout
            self.ping_max_missed = config.ping_max_missed
            self.cleanup_interval = config.cleanup_interval
            self.stale_timeout = config.stale_timeout
            self.payout_reconnect_interval = getattr(config, 'payout_reconnect_interval', 300)  # 5 min default
        else:
            # Valores padrão
            self.max_connections = 1000
            self.heartbeat_interval = 20
            self.heartbeat_timeout = 30
            self.max_reconnects = 5
            self.reconnect_delay = 5
            self.reconnect_max_delay = 60
            self.reconnect_jitter = 0.3
            self.connection_timeout = 30
            self.ping_max_missed = 3
            self.cleanup_interval = 60
            self.stale_timeout = 300
            self.payout_reconnect_interval = 300  # 5 minutos
        self.connections: Dict[str, Connection] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._payout_reconnect_task: Optional[asyncio.Task] = None  # Task para reconexão periódica do payout
        self._global_callbacks: Dict[str, list] = {}
        self._stats = {
            "total_connections": 0,
            "successful_connections": 0,
            "failed_connections": 0,
            "reconnections": 0,
            "errors": 0
        }
        
    async def start(self):
        """Inicia o gerenciador de conexões"""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_connections())
        self._cleanup_task = asyncio.create_task(self._cleanup_stale_connections())
        self._payout_reconnect_task = asyncio.create_task(self._payout_reconnect_loop())
        logger.info(f"ConnectionManager iniciado (max: {self.max_connections}, payout_reconnect: {self.payout_reconnect_interval}s)")
        
    async def stop(self):
        """Para o gerenciador e desconecta todas as conexões de forma segura"""
        self._running = False
        
        # Cancelar tarefas
        tasks_to_cancel = [self._monitor_task, self._cleanup_task, self._payout_reconnect_task]
        for task in tasks_to_cancel:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Desconectar todos com timeout
        if self.connections:
            logger.info(f"Desconectando {len(self.connections)} conexões...")
            disconnect_tasks = []
            for user_id in list(self.connections.keys()):
                task = self._disconnect_with_timeout(user_id, timeout=5.0)
                disconnect_tasks.append(task)
            
            if disconnect_tasks:
                results = await asyncio.gather(*disconnect_tasks, return_exceptions=True)
                success_count = sum(1 for r in results if r is True)
                logger.info(f"{success_count}/{len(disconnect_tasks)} conexões fechadas com sucesso")
        
        self.connections.clear()
        logger.info("ConnectionManager parado")
        
    async def connect(self, user_id: str, ssid: str, is_demo: bool = True) -> Tuple[bool, str]:
        """
        Estabelece nova conexão WSS
        
        Returns:
            Tuple[bool, str]: (sucesso, mensagem de erro se falhou)
        """
        async with self._lock:
            # Verificar limite
            if len(self.connections) >= self.max_connections:
                msg = f"Limite de conexões atingido: {self.max_connections}"
                logger.error(msg)
                return False, msg
            
            # Se já existe, desconectar primeiro
            if user_id in self.connections:
                old_conn = self.connections[user_id]
                if old_conn.state in [ConnectionState.CONNECTED, ConnectionState.CONNECTING]:
                    logger.warning(f"Usuário {user_id} já tem conexão ativa, desconectando...")
                    await self._disconnect_internal_unsafe(user_id)
            
            # Criar nova conexão
            conn = Connection(
                user_id=user_id,
                ssid=ssid,
                is_demo=is_demo
            )
            conn.state = ConnectionState.CONNECTING
            self.connections[user_id] = conn
        
        # Tentar conectar fora do lock
        client = None
        try:
            from ..pocketoption import AsyncPocketOptionClient
            
            client = AsyncPocketOptionClient(
                ssid=ssid,
                is_demo=is_demo,
                enable_logging=True,
                user_id=user_id,
                data_collector=self._data_collector
            )
            
            # Configurar callback de payout ANTES de conectar (updateAssets chega durante conexão)
            client.on_payout_update = lambda data: asyncio.create_task(
                self._handle_payout_update(user_id, data)
            )
            
            # Conectar com timeout
            connected = await asyncio.wait_for(
                client.connect(),
                timeout=conn.connection_timeout
            )
            
            if not connected:
                raise ConnectionError("Cliente retornou não conectado")
            
            # Verificar se ainda existe (pode ter sido removida)
            async with self._lock:
                if user_id not in self.connections:
                    # Conexão foi cancelada, limpar
                    try:
                        await asyncio.wait_for(client.disconnect(), timeout=3.0)
                    except:
                        pass
                    return False, "Conexão cancelada durante handshake"
                
                conn = self.connections[user_id]
                conn.client = client
                conn.state = ConnectionState.CONNECTED
                conn.last_activity = datetime.now()
                conn.reconnect_count = 0
                
                # Iniciar heartbeat
                if conn._heartbeat_task:
                    conn._heartbeat_task.cancel()
                conn._heartbeat_task = asyncio.create_task(
                    self._heartbeat(user_id)
                )
                
                # Configurar callbacks
                self._setup_client_callbacks(conn)
            
            self._stats["successful_connections"] += 1
            logger.info(f"Usuário {user_id} conectado com sucesso")
            await self._emit_event("connected", {"user_id": user_id, "conn": conn})
            return True, ""
            
        except asyncio.TimeoutError:
            self._stats["failed_connections"] += 1
            await self._set_connection_error(user_id, "Timeout na conexão")
            return False, "Timeout ao conectar (30s)"
            
        except ConnectionError as e:
            self._stats["failed_connections"] += 1
            await self._set_connection_error(user_id, str(e))
            return False, str(e)
            
        except Exception as e:
            self._stats["failed_connections"] += 1
            logger.exception(f"Erro inesperado ao conectar {user_id}: {e}")
            await self._set_connection_error(user_id, f"Erro interno: {str(e)}")
            return False, f"Erro interno: {str(e)}"
        
        finally:
            # Limpar cliente se falhou
            if client and user_id in self.connections:
                conn = self.connections[user_id]
                if conn.state != ConnectionState.CONNECTED:
                    try:
                        await asyncio.wait_for(client.disconnect(), timeout=2.0)
                    except:
                        pass
                    
    async def disconnect(self, user_id: str) -> bool:
        """Desconecta um usuário com timeout de segurança"""
        return await self._disconnect_with_timeout(user_id, timeout=10.0)
        
    async def _disconnect_with_timeout(self, user_id: str, timeout: float) -> bool:
        """Desconecta com timeout para evitar travamentos"""
        try:
            return await asyncio.wait_for(
                self._disconnect_internal(user_id),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout ao desconectar {user_id}")
            # Forçar remoção
            async with self._lock:
                if user_id in self.connections:
                    del self.connections[user_id]
            return False
        except Exception as e:
            logger.error(f"Erro ao desconectar {user_id}: {e}")
            return False
            
    async def _disconnect_internal(self, user_id: str) -> bool:
        """Desconexão thread-safe"""
        async with self._lock:
            return await self._disconnect_internal_unsafe(user_id)
            
    async def _disconnect_internal_unsafe(self, user_id: str, intentional: bool = True) -> bool:
        """Desconexão (deve estar sob lock)"""
        if user_id not in self.connections:
            return False
            
        conn = self.connections[user_id]
        
        # Marcar como intencional para evitar reconexão automática
        conn.intentional_disconnect = intentional
        
        # Marcar como fechando
        old_state = conn.state
        conn.state = ConnectionState.CLOSING
        
        # Parar heartbeat
        if conn._heartbeat_task:
            conn._heartbeat_task.cancel()
            try:
                await asyncio.wait_for(conn._heartbeat_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            conn._heartbeat_task = None
        
        # Desconectar cliente com timeout
        if conn.client:
            try:
                await asyncio.wait_for(conn.client.disconnect(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout ao desconectar cliente {user_id}")
            except Exception as e:
                logger.error(f"Erro ao desconectar cliente {user_id}: {e}")
            finally:
                conn.client = None
        
        conn.state = ConnectionState.DISCONNECTED
        
        # Remover do dicionário
        del self.connections[user_id]
        
        logger.info(f"Usuário {user_id} desconectado (estado anterior: {old_state.value})")
        await log_manager.close_ws_logger(user_id)
        await self._emit_event("disconnected", {"user_id": user_id, "previous_state": old_state.value})
        return True
        
    async def reconnect(self, user_id: str) -> Tuple[bool, str]:
        """
        Força reconexão de um usuário com backoff exponencial + jitter
        
        Returns:
            Tuple[bool, str]: (sucesso, mensagem)
        """
        async with self._lock:
            if user_id not in self.connections:
                return False, "Usuário não encontrado"
                
            conn = self.connections[user_id]
            
            # Verificar se foi desconexão intencional
            if conn.intentional_disconnect:
                logger.info(f"[ConnectionManager] Reconexão cancelada para {user_id} - desconexão foi intencional")
                return False, "Desconexão intencional"
            
            if conn.reconnect_count >= conn.max_reconnects:
                msg = f"Máximo de reconexões ({conn.max_reconnects}) atingido"
                logger.error(f"{msg} para {user_id}")
                # Desconectar permanentemente
                await self._disconnect_internal_unsafe(user_id)
                return False, msg
            
            # Incrementar contador
            conn.reconnect_count += 1
            conn.state = ConnectionState.RECONNECTING
        
        # Calcular delay com jitter (evitar thundering herd)
        base_delay = min(
            conn.reconnect_delay * (2 ** (conn.reconnect_count - 1)),
            conn.reconnect_max_delay
        )
        jitter = random.uniform(0, base_delay * 0.3)  # 30% jitter
        delay = base_delay + jitter
        
        logger.info(f"Reconectando {user_id} (tentativa {conn.reconnect_count}/{conn.max_reconnects}, delay: {delay:.1f}s)")
        
        await asyncio.sleep(delay)
        
        # Guardar SSID antes de desconectar
        ssid = conn.ssid
        is_demo = conn.is_demo
        
        # Desconectar antiga
        await self._disconnect_internal(user_id)
        
        # Tentar nova conexão
        success, msg = await self.connect(user_id, ssid, is_demo)
        
        if success:
            self._stats["reconnections"] += 1
            logger.info(f"Reconexão bem-sucedida para {user_id}")
            
            # Emitir evento de reconexão para sincronização
            await self._emit_event("reconnected", {"user_id": user_id, "client": conn.client if user_id in self.connections else None})
            
            return True, "Reconectado com sucesso"
        else:
            logger.error(f"Reconexão falhou para {user_id}: {msg}")
            return False, msg
        
    async def _set_connection_error(self, user_id: str, error_msg: str):
        """Define estado de erro e agenda limpeza"""
        async with self._lock:
            if user_id in self.connections:
                conn = self.connections[user_id]
                conn.state = ConnectionState.ERROR
                logger.error(f"Erro na conexão {user_id}: {error_msg}")
                
        self._stats["errors"] += 1
        await self._emit_event("error", {"user_id": user_id, "error": error_msg})
        
    def set_data_collector(self, data_collector):
        """Define o DataCollectorManager para processar ticks dos clientes"""
        self._data_collector = data_collector
        logger.info("[ConnectionManager] DataCollector configurado")
        
        # Atualizar clientes existentes
        for conn in self.connections.values():
            if conn.client and hasattr(conn.client, '_data_collector'):
                conn.client._data_collector = data_collector
                
    def get_connection(self, user_id: str) -> Optional[Connection]:
        """Obtém informações de uma conexão"""
        return self.connections.get(user_id)
        
    def get_client(self, user_id: str) -> Optional[Any]:
        """Obtém cliente de uma conexão ativa"""
        conn = self.connections.get(user_id)
        if conn and conn.state == ConnectionState.CONNECTED:
            return conn.client
        return None
        
    def is_connected(self, user_id: str) -> bool:
        """Verifica se usuário está conectado"""
        conn = self.connections.get(user_id)
        return conn is not None and conn.state == ConnectionState.CONNECTED
        
    def is_connecting(self, user_id: str) -> bool:
        """Verifica se está em processo de conexão"""
        conn = self.connections.get(user_id)
        return conn is not None and conn.state == ConnectionState.CONNECTING
        
    async def send_message(self, user_id: str, message: str) -> Tuple[bool, str]:
        """
        Envia mensagem via WebSocket
        
        Returns:
            Tuple[bool, str]: (sucesso, erro se houver)
        """
        conn = self.connections.get(user_id)
        if not conn:
            return False, "Usuário não conectado"
            
        if conn.state != ConnectionState.CONNECTED:
            return False, f"Estado inválido: {conn.state.value}"
            
        if not conn.client:
            return False, "Cliente não inicializado"
            
        try:
            # Verificar se cliente tem método send
            if hasattr(conn.client, 'send'):
                log_manager.log_ws_event(user_id, "SEND", message)
                await asyncio.wait_for(conn.client.send(message), timeout=10.0)
                conn.last_activity = datetime.now()
                return True, ""
            else:
                return False, "Cliente não suporta envio de mensagens"
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout ao enviar mensagem para {user_id}")
            # Marcar para reconexão
            asyncio.create_task(self._mark_for_reconnect(user_id))
            return False, "Timeout"
            
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem para {user_id}: {e}")
            # Marcar para reconexão
            asyncio.create_task(self._mark_for_reconnect(user_id))
            return False, str(e)
            
    async def _mark_for_reconnect(self, user_id: str):
        """Marca conexão para reconexão"""
        async with self._lock:
            if user_id in self.connections:
                conn = self.connections[user_id]
                # Não marcar para reconexão se foi intencional
                if conn.intentional_disconnect:
                    logger.debug(f"_mark_for_reconnect: {user_id} - desconexão intencional, ignorando")
                    return
                conn.state = ConnectionState.ERROR
                if conn.state == ConnectionState.CONNECTED:
                    conn.state = ConnectionState.ERROR
                    
    def subscribe(self, event: str, callback: Callable):
        """Subscreve a eventos globais de conexão"""
        if event not in self._global_callbacks:
            self._global_callbacks[event] = []
        self._global_callbacks[event].append(callback)
        
    def unsubscribe(self, event: str, callback: Callable):
        """Remove subscrição de eventos"""
        if event in self._global_callbacks and callback in self._global_callbacks[event]:
            self._global_callbacks[event].remove(callback)
            
    async def _emit_event(self, event: str, data: Any):
        """Emite evento para subscribers com tratamento de erro"""
        callbacks = self._global_callbacks.get(event, [])
        if not callbacks:
            return
            
        tasks = []
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    tasks.append(asyncio.create_task(callback(data)))
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Erro no callback de evento {event}: {e}")
        
        # Aguardar callbacks async com timeout
        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"Timeout aguardando callbacks do evento {event}")
                
    def _setup_client_callbacks(self, conn: Connection):
        """Configura callbacks no cliente PocketOption"""
        if not conn.client:
            return
            
        try:
            # Configurar callback de desconexão
            if hasattr(conn.client, 'on_disconnect'):
                conn.client.on_disconnect = lambda: asyncio.create_task(
                    self._handle_client_disconnect(conn.user_id)
                )
                
            # Configurar callback de mensagens
            if hasattr(conn.client, 'on_message'):
                conn.client.on_message = lambda msg: asyncio.create_task(
                    self._handle_client_message(conn.user_id, msg)
                )
            
            # Configurar callback de payout update
            if hasattr(conn.client, 'on_payout_update'):
                conn.client.on_payout_update = lambda data: asyncio.create_task(
                    self._handle_payout_update(conn.user_id, data)
                )
                
        except Exception as e:
            logger.error(f"Erro ao configurar callbacks para {conn.user_id}: {e}")
            
    async def _handle_client_disconnect(self, user_id: str):
        """Handler para desconexão do cliente"""
        conn = self.connections.get(user_id)
        
        # Verificar se foi desconexão intencional (autotrade desabilitado)
        if conn and conn.intentional_disconnect:
            logger.info(f"[ConnectionManager] Cliente {user_id} desconectou intencionalmente (ignorando reconexão)")
            return
        
        # Desconexão imprevista - tentar reconectar
        logger.warning(f"[ConnectionManager] Cliente {user_id} desconectou inesperadamente - tentando reconectar")
        if conn and conn.state == ConnectionState.CONNECTED:
            conn.state = ConnectionState.ERROR
            # Tentar reconexão
            asyncio.create_task(self.reconnect(user_id))
            
    async def _handle_client_message(self, user_id: str, message: Any):
        """Handler para mensagens do cliente"""
        conn = self.connections.get(user_id)
        if conn:
            conn.last_activity = datetime.now()
            log_manager.log_ws_event(user_id, "RECV", message)
            await self._emit_event("message", {"user_id": user_id, "message": message})
            
    async def _handle_payout_update(self, user_id: str, data: Any):
        """Handler para atualizações de payout"""
        conn = self.connections.get(user_id)
        if conn:
            conn.last_activity = datetime.now()
            await self._emit_event("payout_update", {"user_id": user_id, "data": data})
            
    async def _on_candle(self, user_id: str, data: Any):
        """Callback quando recebe candle"""
        conn = self.connections.get(user_id)
        if conn:
            conn.last_activity = datetime.now()
            await self._emit_event("candle", {"user_id": user_id, "data": data})
            
    async def _heartbeat(self, user_id: str):
        """Mantém conexão viva com ping periódico e detecção de timeout"""
        missed_pings = 0
        max_missed_pings = 3
        
        while self._running:
            try:
                # Verificar se conexão ainda existe
                if user_id not in self.connections:
                    logger.debug(f"Heartbeat: conexão {user_id} não existe mais")
                    break
                    
                conn = self.connections[user_id]
                
                if conn.state != ConnectionState.CONNECTED:
                    break
                
                async with conn._lock:
                    # Verificar timeout de atividade
                    elapsed = (datetime.now() - conn.last_activity).total_seconds()
                    
                    if elapsed > self.stale_timeout:
                        logger.warning(f"Conexão {user_id} inativa por {elapsed}s, forçando reconexão")
                        missed_pings = max_missed_pings  # Forçar reconexão
                        
                    # Enviar ping se disponível
                    if hasattr(conn.client, 'ping'):
                        try:
                            await asyncio.wait_for(conn.client.ping(), timeout=5.0)
                            conn.last_ping = datetime.now()
                            conn._ping_count += 1
                            missed_pings = 0
                        except asyncio.TimeoutError:
                            missed_pings += 1
                            logger.warning(f"Ping timeout para {user_id} ({missed_pings}/{max_missed_pings})")
                        except Exception as e:
                            missed_pings += 1
                            logger.warning(f"Erro no ping {user_id}: {e}")
                            
                        if missed_pings >= max_missed_pings:
                            # Verificar se não foi desconexão intencional
                            if not conn.intentional_disconnect:
                                logger.error(f"Muitos pings perdidos para {user_id}, reconectando...")
                                conn.state = ConnectionState.ERROR
                                asyncio.create_task(self.reconnect(user_id))
                            break
                    else:
                        # Sem ping disponível, apenas atualizar atividade
                        conn.last_activity = datetime.now()
                
                await asyncio.sleep(self.heartbeat_interval)
                
            except asyncio.CancelledError:
                logger.debug(f"Heartbeat cancelado para {user_id}")
                break
            except Exception as e:
                logger.error(f"Erro no heartbeat de {user_id}: {e}")
                await asyncio.sleep(5)
                
    async def _cleanup_stale_connections(self):
        """Limpa conexões em estado ERROR ou DISCONNECTED antigas"""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                now = datetime.now()
                to_remove = []
                
                async with self._lock:
                    for user_id, conn in list(self.connections.items()):
                        # Remover conexões em ERROR há mais de 5 minutos
                        if conn.state == ConnectionState.ERROR:
                            elapsed = (now - conn.last_activity).total_seconds()
                            if elapsed > self.stale_timeout:
                                to_remove.append(user_id)
                                
                        # Remover conexões DISCONNECTED
                        if conn.state == ConnectionState.DISCONNECTED:
                            to_remove.append(user_id)
                
                # Remover fora do lock
                for user_id in to_remove:
                    await self._disconnect_internal(user_id)
                    logger.info(f"Conexão stale removida: {user_id}")
                    
            except Exception as e:
                logger.error(f"Erro na limpeza de conexões: {e}")
                
    async def _monitor_connections(self):
        """Monitora saúde das conexões e reconecta se necessário"""
        while self._running:
            try:
                await asyncio.sleep(30)  # Verificar a cada 30s
                
                now = datetime.now()
                to_reconnect = []
                
                for user_id, conn in self.connections.items():
                    # Verificar conexões inativas
                    elapsed = (now - conn.last_activity).total_seconds()
                    
                    # Conexão inativa por muito tempo
                    if conn.state == ConnectionState.CONNECTED and elapsed > self.stale_timeout * 2:
                        logger.warning(f"Conexão {user_id} muito inativa ({elapsed}s)")
                        to_reconnect.append(user_id)
                        
                    # Conexões em erro
                    elif conn.state == ConnectionState.ERROR:
                        to_reconnect.append(user_id)
                        
                    # Conexões presas em CONNECTING
                    elif conn.state == ConnectionState.CONNECTING:
                        elapsed_connecting = (now - conn.created_at).total_seconds()
                        if elapsed_connecting > 60:  # 1 minuto tentando conectar
                            logger.warning(f"Conexão {user_id} presa em CONNECTING")
                            to_reconnect.append(user_id)
                
                # Reconectar em paralelo
                if to_reconnect:
                    logger.info(f"Reconectando {len(to_reconnect)} conexões...")
                    results = await asyncio.gather(
                        *[self.reconnect(uid) for uid in to_reconnect],
                        return_exceptions=True
                    )
                    success = sum(1 for r in results if isinstance(r, tuple) and r[0] is True)
                    logger.info(f"Reconexões: {success}/{len(to_reconnect)} sucesso")
                    
            except Exception as e:
                logger.error(f"Erro no monitoramento: {e}")
                
    async def _payout_reconnect_loop(self):
        """Loop de reconexão periódica para contas payout (atualiza payout dos ativos)"""
        while self._running:
            try:
                await asyncio.sleep(self.payout_reconnect_interval)
                
                if not self._running:
                    break
                
                # Encontrar conexões payout
                payout_connections = []
                for user_id, conn in self.connections.items():
                    if "payout" in user_id.lower() and conn.state == ConnectionState.CONNECTED:
                        payout_connections.append(user_id)
                
                if payout_connections:
                    logger.info(f"[PAYOUT] Reconectando {len(payout_connections)} conta(s) payout para atualizar cache (intervalo: {self.payout_reconnect_interval}s)")
                    
                    for user_id in payout_connections:
                        try:
                            # Reconectar para obter payout atualizado
                            success, msg = await self.reconnect(user_id)
                            if success:
                                logger.info(f"[PAYOUT] {user_id} reconectado com sucesso - cache atualizado")
                            else:
                                logger.error(f"[PAYOUT] Falha ao reconectar {user_id}: {msg}")
                        except Exception as e:
                            logger.error(f"[PAYOUT] Erro ao reconectar {user_id}: {e}")
                            
            except asyncio.CancelledError:
                logger.debug("Payout reconnect loop cancelado")
                break
            except Exception as e:
                logger.error(f"Erro no payout reconnect loop: {e}")
                await asyncio.sleep(5)
                
    def get_stats(self) -> Dict:
        """Retorna estatísticas detalhadas de conexões"""
        total = len(self.connections)
        states = {state.value: 0 for state in ConnectionState}
        
        for conn in self.connections.values():
            states[conn.state.value] += 1
            
        return {
            "total_connections": total,
            "by_state": states,
            "max_connections": self.max_connections,
            "usage_percentage": (total / self.max_connections) * 100 if self.max_connections > 0 else 0,
            "lifetime_stats": self._stats,
            "avg_reconnects": sum(c.reconnect_count for c in self.connections.values()) / total if total > 0 else 0
        }
