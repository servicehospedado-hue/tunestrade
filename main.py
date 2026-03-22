"""
Ponto de entrada principal do sistema de trading
"""
import asyncio
import logging
import signal
import sys
import io
from contextlib import asynccontextmanager

# Carregar .env ANTES de qualquer outro import para garantir que
# os módulos que leem os.getenv() no nível do módulo (ex: auth.py)
# já encontrem as variáveis definidas
from dotenv import load_dotenv
load_dotenv()

import os
from loguru import logger as _loguru_logger

# Configurar loguru com o LOG_LEVEL do .env ANTES de qualquer import que use loguru
_log_level = os.getenv("LOG_LEVEL", "info").upper()
_loguru_logger.remove()
_loguru_logger.add(sys.stderr, level=_log_level, colorize=False,
                   format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}")

import uvicorn

# IMPORTANTE: Importar LogManager ANTES do basicConfig para garantir
# que os handlers de warning/error sejam configurados corretamente
from src.managers import LogManager, log_manager

from src.core.engine import TradingEngine
# NOVA ESTRUTURA: Usar factory de rotas modularizada
# from src.api.routes import create_app  # LEGADO
from src.api.routes.factory import create_app  # NOVO
from src.config.settings import Settings

# Configurar stdout/stderr para UTF-8 (evita erros de encoding no Windows)
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Configuração de logging básica (complementar ao LogManager)
_stdlib_level = getattr(logging, os.getenv("LOG_LEVEL", "info").upper(), logging.INFO)
logging.basicConfig(
    level=_stdlib_level,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    encoding='utf-8',
    errors='replace'
)

# Desabilitar debug logging da biblioteca websockets para evitar erros de Unicode
logging.getLogger('websockets').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class TradingSystem:
    """Sistema de trading principal"""
    
    def __init__(self):
        self.settings = Settings.from_env()
        self.engine = TradingEngine(self.settings)
        self.app = create_app(self.engine)
        self._shutdown_event = asyncio.Event()
        self._stopping = False  # Flag para evitar chamada dupla do stop
        
    async def start(self):
        """Inicia o sistema completo"""
        logger.info("=" * 60)
        logger.info("Iniciando Sistema de Trading PocketOption")
        logger.info("=" * 60)
        
        # Configurar handlers de sinal
        self._setup_signal_handlers()
        
        # Iniciar engine
        try:
            logger.info("Chamando engine.start()...")
            await self.engine.start()
            logger.info("[OK] Engine iniciado com sucesso")
            
            # Injetar UserManager na NOVA estrutura de auth
            if self.engine.user_manager:
                from src.api.services.auth_service import set_user_manager
                set_user_manager(self.engine.user_manager)
                logger.info("[OK] UserManager injetado (nova estrutura)")
        except Exception as e:
            logger.exception(f"[ERRO] Falha ao iniciar engine: {e}")
            raise
        
        # Configurar lifespan da API
        @asynccontextmanager
        async def lifespan(app):
            logger.info("API iniciada")
            yield
            logger.info("API finalizada")
        
        self.app.router.lifespan_context = lifespan
        
        # Iniciar servidor API
        config = uvicorn.Config(
            self.app,
            host=self.settings.api.host,
            port=self.settings.api.port,
            log_level=self.settings.api.log_level,
            reload=self.settings.api.reload
        )
        
        server = uvicorn.Server(config)
        
        # Aguardar sinal de desligamento
        shutdown_task = asyncio.create_task(self._wait_for_shutdown())
        server_task = asyncio.create_task(server.serve())
        
        logger.info(f"API disponível em http://{self.settings.api.host}:{self.settings.api.port}")
        logger.info("Pressione Ctrl+C para parar o sistema")
        
        try:
            await asyncio.gather(shutdown_task, server_task)
        except asyncio.CancelledError:
            pass
            
    async def stop(self):
        """Para o sistema"""
        # Proteção contra chamada dupla
        if self._stopping:
            logger.debug("Stop já em andamento, ignorando...")
            return
        
        self._stopping = True
        
        logger.info("\n" + "=" * 60)
        logger.info("Parando Sistema de Trading...")
        logger.info("=" * 60)
        
        try:
            await self.engine.stop()
        except Exception as e:
            logger.error(f"Erro ao parar engine: {e}")
        finally:
            self._shutdown_event.set()
        
        logger.info("Sistema parado com sucesso")
        
    def _setup_signal_handlers(self):
        """Configura handlers para sinais de sistema"""
        def signal_handler(sig, frame):
            logger.info(f"Sinal {sig} recebido, iniciando desligamento...")
            # Ignorar sinais subsequentes
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            asyncio.create_task(self.stop())
            
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
    async def _wait_for_shutdown(self):
        """Aguarda evento de desligamento"""
        await self._shutdown_event.wait()


async def main():
    """Função principal"""
    system = TradingSystem()
    
    try:
        await system.start()
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
