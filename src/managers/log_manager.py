"""
LogManager - Gerenciador central de logs do sistema
Responsabilidade única: gerenciar logs estruturados para todos os componentes
"""
import logging
import logging.handlers
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import sys
import uuid
import asyncio


class WSConnectionLogger:
    """
    Logger especializado para conexões WebSocket
    Formato estruturado para debug de conexões
    """
    
    def __init__(self, user_id: str, log_dir: Path, connection_type: str = "websocket"):
        self.user_id = user_id
        self.connection_type = connection_type
        self.log_dir = log_dir
        self.connection_id = f"{connection_type}_{uuid.uuid4().hex[:12]}"
        self.created_at = datetime.now()
        self.log_file = self.log_dir / f"{user_id}.log"
        
        # Estatísticas
        self.stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "reconnects": 0,
            "errors": 0,
            "bytes_sent": 0,
            "bytes_received": 0
        }
        
        # Abrir arquivo em modo append
        self._file = open(self.log_file, 'a', encoding='utf-8')
        
        # Buffer para escrita otimizada
        self._buffer: List[str] = []
        self._buffer_size = 10  # Escrever a cada 10 mensagens
        self._buffer_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._start_buffer_flush()
        
    def _start_buffer_flush(self):
        """Inicia task de flush periódico do buffer"""
        self._buffer_task = asyncio.create_task(self._periodic_flush())
        
    async def _periodic_flush(self):
        """Flush periódico a cada 1 segundo"""
        while True:
            try:
                await asyncio.sleep(1.0)
                await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception:
                pass
                
    async def _flush_buffer(self):
        """Escreve buffer no arquivo"""
        async with self._lock:
            if self._buffer:
                content = '\n'.join(self._buffer) + '\n'
                self._file.write(content)
                self._file.flush()
                self._buffer = []
        
    def _write(self, content: str):
        """Adiciona ao buffer (escrita otimizada)"""
        self._buffer.append(content)
        # Flush imediato se buffer grande
        if len(self._buffer) >= self._buffer_size:
            asyncio.create_task(self._flush_buffer())
        
    def _format_timestamp(self) -> str:
        """Retorna timestamp no formato ISO"""
        return datetime.now().isoformat()
        
    def log_header(self, ssid_preview: str = "", is_demo: bool = True, region: str = ""):
        """Loga o header da conexão"""
        header = f"""
================================================================================
WebSocket Connection Log
Connection ID: {self.connection_id}
Connection Type: {self.connection_type}
User: {self.user_id}
Created: {self.created_at.isoformat()}
Log File: {self.log_file.name}
================================================================================
"""
        self._write(header)
        
    def log_init(self, data: Dict[str, Any]):
        """Loga início da conexão"""
        self._write(f"[{self._format_timestamp()}] [INIT] Iniciando conexão")
        self._write(f"  Data: {json.dumps(data, ensure_ascii=False)}")
        
    def log_connected(self, url: str, region: str):
        """Loga conexão estabelecida"""
        self._write(f"[{self._format_timestamp()}] [CONNECTED] Conexão estabelecida em {region}")
        self._write(f"  Data: {json.dumps({'url': url, 'region': region, 'total_reconnects': self.stats['reconnects']}, ensure_ascii=False)}")
        
    def log_authenticated(self, data: Dict[str, Any]):
        """Loga autenticação bem-sucedida"""
        self._write(f"[{self._format_timestamp()}] [AUTH] Autenticação bem-sucedida")
        self._write(f"  Data: {json.dumps(data, ensure_ascii=False)}")
        
    def log_send(self, message: str):
        """Loga mensagem enviada"""
        size = len(message.encode('utf-8'))
        self.stats["messages_sent"] += 1
        self.stats["bytes_sent"] += size
        preview = message[:100] + "..." if len(message) > 100 else message
        self._write(f"[{self._format_timestamp()}] [SEND] Mensagem enviada ({size} bytes)")
        self._write(f"  Data: {json.dumps({'preview': preview, 'size': size}, ensure_ascii=False)}")
        
    def log_recv(self, message: str, prefix: str = "RECV"):
        """Loga mensagem recebida"""
        size = len(message.encode('utf-8')) if isinstance(message, str) else len(message)
        self.stats["messages_received"] += 1
        self.stats["bytes_received"] += size
        preview = str(message)[:100] + "..." if len(str(message)) > 100 else str(message)
        self._write(f"[{self._format_timestamp()}] [{prefix}] Mensagem recebida ({size} bytes)")
        self._write(f"  Data: {json.dumps({'preview': preview, 'size': size}, ensure_ascii=False)}")
        
    def log_recv_raw(self, message: str):
        """Loga mensagem recebida em formato raw"""
        size = len(message.encode('utf-8')) if isinstance(message, str) else len(message)
        preview = str(message)[:100] + "..." if len(str(message)) > 100 else str(message)
        self._write(f"[{self._format_timestamp()}] [RECV_RAW] Mensagem recebida ({size} bytes)")
        self._write(f"  Data: {json.dumps({'preview': preview, 'size': size}, ensure_ascii=False)}")
        
    def log_event(self, event: str, data: Any = None):
        """Loga evento genérico"""
        if data:
            self._write(f"[{self._format_timestamp()}] [{event}] {data}")
        else:
            self._write(f"[{self._format_timestamp()}] [{event}]")
            
    def log_disconnect(self, reason: str = ""):
        """Loga desconexão com sumário"""
        closed_at = datetime.now()
        self._write(f"[{self._format_timestamp()}] [DISCONNECT] Conexão encerrada: {reason}")
        
        summary = f"""
================================================================================
CONNECTION CLOSED - SUMMARY
================================================================================
Connection ID: {self.connection_id}
Total Messages Sent: {self.stats['messages_sent']}
Total Messages Received: {self.stats['messages_received']}
Total Bytes Sent: {self.stats['bytes_sent']}
Total Bytes Received: {self.stats['bytes_received']}
Total Reconnects: {self.stats['reconnects']}
Total Errors: {self.stats['errors']}
Closed At: {closed_at.isoformat()}
================================================================================
"""
        self._write(summary)
        
    def log_reconnect_session(self):
        """Loga início de sessão de reconexão"""
        self.stats["reconnects"] += 1
        session_started = datetime.now()
        self._write(f"""
================================================================================
RECONNECTION SESSION
================================================================================
Connection ID: {self.connection_id}
Session Started: {session_started.isoformat()}
================================================================================
""")
        
    def log_error(self, error: str, details: Any = None):
        """Loga erro"""
        self.stats["errors"] += 1
        if details:
            self._write(f"[{self._format_timestamp()}] [ERROR] {error}")
            self._write(f"  Data: {json.dumps({'error': str(details)}, ensure_ascii=False)}")
        else:
            self._write(f"[{self._format_timestamp()}] [ERROR] {error}")
            
    async def close(self):
        """Fecha o arquivo de log (esvazia buffer primeiro)"""
        if self._buffer_task:
            self._buffer_task.cancel()
            try:
                await self._buffer_task
            except asyncio.CancelledError:
                pass
        
        # Esvaziar buffer restante
        await self._flush_buffer()
        
        if self._file:
            self._file.close()
            self._file = None


class LogManager:
    """
    Gerenciador central de logs do sistema
    
    Features:
    - Logs separados por componente/manager
    - Logs WebSocket por usuário
    - Logs centralizados de warnings e errors
    - Rotação automática de arquivos
    - Integração com Loguru (opcional)
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        log_dir: str = "logs",
        app_name: str = "pocketoption_trading",
        auto_clean: bool = True,
        max_file_size_mb: int = 50
    ):
        if LogManager._initialized:
            return
            
        self.log_dir = Path(log_dir)
        self.app_name = app_name
        self.ws_log_dir = self.log_dir / "ws"
        self.auto_clean = auto_clean
        self.max_file_size_mb = max_file_size_mb
        
        # Estado
        self._running = False
        self._loggers: Dict[str, logging.Logger] = {}
        self._ws_loggers: Dict[str, WSConnectionLogger] = {}
        
        # Criar diretórios
        self._create_directories()
        
        # Configurar logging
        self._setup_logging()
        
        LogManager._initialized = True
        
        self.logger = logging.getLogger("log_manager")
        self.logger.info("[LogManager] Inicializado")
    
    def _create_directories(self):
        """Cria estrutura de diretórios de logs"""
        # Limpar arquivos antigos APENAS se auto_clean=True
        if self.auto_clean:
            self._clean_old_logs()
        
        # Criar diretórios
        self.log_dir.mkdir(exist_ok=True)
        self.ws_log_dir.mkdir(exist_ok=True)
    
    def _clean_old_logs(self):
        """Limpa arquivos de log antigos (apenas se auto_clean=True)"""
        if self.log_dir.exists():
            for log_file in self.log_dir.glob("*.log"):
                try:
                    log_file.unlink()
                except Exception:
                    pass
        
        if self.ws_log_dir.exists():
            for ws_file in self.ws_log_dir.glob("*.log"):
                try:
                    ws_file.unlink()
                except Exception:
                    pass
        
        # Limpar arquivos de ativos (data/actives)
        data_actives_dir = Path("data/actives")
        if data_actives_dir.exists():
            for asset_file in data_actives_dir.glob("*.txt"):
                try:
                    asset_file.unlink()
                except Exception:
                    pass
    
    def _setup_logging(self):
        """Configura o sistema de logging"""
        
        # Formato padrão
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler para console
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        
        # Configurar logger raiz
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(console_handler)
        
        # Criar handlers de nível (WARNING e ERROR)
        warning_handler = self._create_file_handler("warnings.log", formatter, logging.WARNING)
        error_handler = self._create_file_handler("errors.log", formatter, logging.ERROR)
        
        # Criar handler para app.log (captura todos os logs)
        app_handler = self._create_file_handler("app.log", formatter, logging.DEBUG)
        
        # Adicionar ao root logger
        root_logger.addHandler(warning_handler)
        root_logger.addHandler(error_handler)
        root_logger.addHandler(app_handler)
        
        # Criar loggers para cada manager
        self._setup_manager_loggers(formatter, console_handler, warning_handler, error_handler, app_handler)
        
        # Criar loggers específicos de nível
        self._setup_level_loggers(warning_handler, error_handler)
    
    def _create_file_handler(
        self,
        filename: str,
        formatter: logging.Formatter,
        level: int
    ) -> logging.handlers.RotatingFileHandler:
        """Cria um handler de arquivo com rotação"""
        handler = logging.handlers.RotatingFileHandler(
            self.log_dir / filename,
            maxBytes=self.max_file_size_mb * 1024 * 1024,
            backupCount=0
        )
        handler.setFormatter(formatter)
        handler.setLevel(level)
        return handler
    
    def _setup_manager_loggers(
        self,
        formatter: logging.Formatter,
        console_handler: logging.Handler,
        warning_handler: logging.Handler,
        error_handler: logging.Handler,
        app_handler: logging.Handler
    ):
        """Configura loggers individuais para cada manager"""
        
        # Lista atualizada de managers
        managers = [
            "signal_manager",
            "user_manager",
            "indicator_manager",
            "connection_manager",
            "cache_manager",
            "engine",
            "trade_executor",
            "data_collector",
            "autotrade_manager",
            "system_health",
            "strategy_manager",
            "database",
            "log_manager",
        ]
        
        for manager_name in managers:
            logger = logging.getLogger(manager_name)
            logger.setLevel(logging.DEBUG)
            logger.propagate = False
            
            # Handler para arquivo individual
            file_handler = self._create_file_handler(
                f"{manager_name}.log",
                formatter,
                logging.DEBUG
            )
            
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
            logger.addHandler(warning_handler)
            logger.addHandler(error_handler)
            logger.addHandler(app_handler)  # Adiciona app.log para capturar todos os logs
            
            self._loggers[manager_name] = logger
    
    def _setup_level_loggers(
        self,
        warning_handler: logging.Handler,
        error_handler: logging.Handler
    ):
        """Configura loggers específicos para WARNING e ERROR"""
        
        warning_logger = logging.getLogger("warnings")
        warning_logger.setLevel(logging.WARNING)
        warning_logger.propagate = False
        warning_logger.addHandler(warning_handler)
        self._loggers["warnings"] = warning_logger
        
        error_logger = logging.getLogger("errors")
        error_logger.setLevel(logging.ERROR)
        error_logger.propagate = False
        error_logger.addHandler(error_handler)
        self._loggers["errors"] = error_logger
    
    async def start(self):
        """Inicia o LogManager (para compatibilidade com outros managers)"""
        self._running = True
        self.logger.info("[LogManager] Iniciado")
    
    async def stop(self):
        """Para o LogManager e fecha todos os handlers"""
        self._running = False
        
        # Fechar todos os WS loggers
        for ws_logger in self._ws_loggers.values():
            await ws_logger.close()
        
        # Fechar todos os handlers
        for logger in self._loggers.values():
            for handler in logger.handlers[:]:
                handler.close()
        
        self.logger.info("[LogManager] Parado")
    
    def get_logger(self, name: str) -> logging.Logger:
        """Obtém um logger pelo nome"""
        if name in self._loggers:
            return self._loggers[name]
        return logging.getLogger(name)
    
    def get_manager_logger(self, manager_name: str) -> logging.Logger:
        """Obtém logger específico de um manager"""
        return self.get_logger(manager_name)
    
    def get_ws_logger(self, user_id: str) -> logging.Logger:
        """Obtém ou cria logger específico para conexão WebSocket de um usuário"""
        logger_name = f"ws_{user_id}"
        
        if logger_name in self._loggers:
            return self._loggers[logger_name]
        
        # Criar novo logger para esta conexão WS
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        
        # Formato específico para WS
        ws_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler para arquivo individual
        ws_file_handler = logging.handlers.RotatingFileHandler(
            self.ws_log_dir / f"{user_id}.log",
            maxBytes=self.max_file_size_mb * 1024 * 1024,
            backupCount=0
        )
        ws_file_handler.setFormatter(ws_formatter)
        ws_file_handler.setLevel(logging.DEBUG)
        
        # Handler para console
        ws_console_handler = logging.StreamHandler(sys.stdout)
        ws_console_handler.setFormatter(ws_formatter)
        ws_console_handler.setLevel(logging.INFO)
        
        logger.addHandler(ws_file_handler)
        logger.addHandler(ws_console_handler)
        self._loggers[logger_name] = logger
        
        return logger
    
    def create_ws_connection_logger(self, user_id: str, connection_type: str = "websocket") -> WSConnectionLogger:
        """Cria um WSConnectionLogger para uma conexão específica"""
        ws_logger = WSConnectionLogger(user_id, self.ws_log_dir, connection_type)
        self._ws_loggers[user_id] = ws_logger
        return ws_logger
    
    async def close_ws_logger(self, user_id: str):
        """Fecha logger de uma conexão WebSocket"""
        logger_name = f"ws_{user_id}"
        
        # Fechar WSConnectionLogger se existir
        if user_id in self._ws_loggers:
            await self._ws_loggers[user_id].close()
            del self._ws_loggers[user_id]
        
        # Fechar logger padrão se existir
        if logger_name in self._loggers:
            logger = self._loggers[logger_name]
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)
            del self._loggers[logger_name]
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do LogManager"""
        stats = {
            "running": self._running,
            "log_dir": str(self.log_dir),
            "ws_log_dir": str(self.ws_log_dir),
            "active_loggers": len(self._loggers),
            "active_ws_loggers": len(self._ws_loggers),
            "auto_clean": self.auto_clean,
            "max_file_size_mb": self.max_file_size_mb,
            "log_files": []
        }
        
        # Listar arquivos de log
        if self.log_dir.exists():
            for file in self.log_dir.iterdir():
                if file.suffix == '.log':
                    stats["log_files"].append({
                        "name": file.name,
                        "size_mb": round(file.stat().st_size / (1024*1024), 2)
                    })
        
        # Contar logs WS
        if self.ws_log_dir.exists():
            ws_count = sum(1 for _ in self.ws_log_dir.iterdir() if _.suffix == '.log')
            stats["ws_log_count"] = ws_count
        
        return stats
    
    def clear_logs(self) -> Dict[str, int]:
        """Limpa todos os arquivos de log"""
        removed = {"main_logs": 0, "ws_logs": 0}
        
        if self.log_dir.exists():
            for log_file in self.log_dir.glob("*.log"):
                try:
                    log_file.unlink()
                    removed["main_logs"] += 1
                except Exception:
                    pass
        
        if self.ws_log_dir.exists():
            for ws_file in self.ws_log_dir.glob("*.log"):
                try:
                    ws_file.unlink()
                    removed["ws_logs"] += 1
                except Exception:
                    pass
        
        return removed


# Instância global
log_manager = LogManager()

# Funções de conveniência
def get_logger(name: str) -> logging.Logger:
    """Obtém um logger pelo nome"""
    return log_manager.get_logger(name)

def get_manager_logger(manager_name: str) -> logging.Logger:
    """Obtém logger de um manager"""
    return log_manager.get_manager_logger(manager_name)

def get_ws_logger(user_id: str) -> logging.Logger:
    """Obtém logger de uma conexão WebSocket"""
    return log_manager.get_ws_logger(user_id)

def get_warning_logger() -> logging.Logger:
    """Obtém logger de warnings"""
    return log_manager.get_logger("warnings")

def get_error_logger() -> logging.Logger:
    """Obtém logger de errors"""
    return log_manager.get_logger("errors")

def get_app_logger() -> logging.Logger:
    """Obtém logger do app.log (captura todos os logs do sistema)"""
    return logging.getLogger("app")

def clear_logs() -> Dict[str, int]:
    """Limpa todos os logs"""
    return log_manager.clear_logs()
