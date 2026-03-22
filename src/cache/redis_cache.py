"""
Redis Cache Integration
Cache distribuído para dados de payout e ativos
"""
import asyncio
import json
from typing import Any, Optional, Dict
from datetime import timedelta

try:
    from redis.asyncio import Redis
    from redis.exceptions import RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    Redis = None
    RedisError = Exception

import logging

from ..managers.log_manager import get_manager_logger

logger = get_manager_logger("redis_cache")


class RedisCache:
    """Cache Redis para dados de payout e ativos"""
    
    def __init__(self, host: str = "redis", port: int = 6379, db: int = 0, password: str = None):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self._redis: Optional[Any] = None
        self._lock = asyncio.Lock()
        # Backoff para evitar flood de reconexão
        self._last_connect_attempt: float = 0.0
        self._connect_backoff: float = 5.0   # segundos iniciais
        self._connect_backoff_max: float = 60.0  # máximo 60s entre tentativas
        self._connect_failed: bool = False
        
    async def connect(self):
        """Conecta ao Redis com fallback para localhost"""
        import time
        logger.info("[REDIS] Conectando...")
        if not REDIS_AVAILABLE or Redis is None:
            logger.warning("[REDIS] aioredis não instalado - cache desativado")
            return False
        
        # Tentar hosts: primeiro o configurado, depois localhost como fallback
        hosts_to_try = [self.host]
        if self.host not in ("localhost", "127.0.0.1"):
            hosts_to_try.extend(["localhost", "127.0.0.1"])
        
        last_error = None
        for host in hosts_to_try:
            try:
                url = f"redis://{host}:{self.port}/{self.db}"
                if self.password:
                    url = f"redis://:{self.password}@{host}:{self.port}/{self.db}"
                self._redis = Redis.from_url(
                    url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                    health_check_interval=30
                )
                await self._redis.ping()
                if host != self.host:
                    logger.info(f"[REDIS] Conectado via fallback: {host}:{self.port}/{self.db}")
                else:
                    logger.info(f"[REDIS] Conectado: {host}:{self.port}/{self.db}")
                self._connect_failed = False
                self._connect_backoff = 5.0
                return True
            except Exception as e:
                last_error = e
                logger.debug(f"[REDIS] Falha ao conectar em {host}: {e}")
                self._redis = None
                continue
        
        logger.error(f"[REDIS] Erro ao conectar em todos os hosts: {last_error}")
        self._connect_failed = True
        self._last_connect_attempt = time.monotonic()
        return False
    
    async def disconnect(self):
        """Desconecta do Redis"""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("[REDIS] Desconectado")
    
    async def _ensure_connection(self) -> bool:
        """Verifica e reconecta ao Redis se necessário, com backoff exponencial"""
        import time
        if not self._redis:
            # Se falhou recentemente, aguardar backoff antes de tentar de novo
            if self._connect_failed:
                elapsed = time.monotonic() - self._last_connect_attempt
                if elapsed < self._connect_backoff:
                    return False
                # Aumentar backoff exponencialmente até o máximo
                self._connect_backoff = min(self._connect_backoff * 2, self._connect_backoff_max)
            return await self.connect()
        
        try:
            await self._redis.ping()
            return True
        except Exception:
            logger.warning("[REDIS] Conexão perdida, tentando reconectar...")
            self._redis = None
            return await self.connect()
    
    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Armazena valor no Redis com TTL em segundos"""
        async with self._lock:
            # Garante conexão antes de operar
            if not await self._ensure_connection():
                return False
                
            try:
                # Verificação extra de None dentro do lock
                if self._redis is None:
                    return False
                serialized = json.dumps(value, default=str)
                await self._redis.setex(key, ttl, serialized)
                logger.debug(f"[REDIS] SET {key} (ttl: {ttl}s)")
                return True
            except Exception as e:
                logger.error(f"[REDIS] Erro SET {key}: {e}")
                # Invalida conexão para forçar reconexão na próxima
                self._redis = None
                return False
    
    async def get(self, key: str) -> Optional[Any]:
        """Obtém valor do Redis"""
        async with self._lock:
            # Garante conexão antes de operar
            if not await self._ensure_connection():
                return None
                
            try:
                # Verificação extra de None dentro do lock
                if self._redis is None:
                    return None
                data = await self._redis.get(key)
                if data:
                    logger.debug(f"[REDIS] GET {key} (hit)")
                    return json.loads(data)
                logger.debug(f"[REDIS] GET {key} (miss)")
                return None
            except Exception as e:
                logger.error(f"[REDIS] Erro GET {key}: {e}")
                # Invalida conexão para forçar reconexão na próxima
                self._redis = None
                return None
    
    async def delete(self, key: str) -> bool:
        """Remove chave do Redis"""
        async with self._lock:
            # Garante conexão antes de operar
            if not await self._ensure_connection():
                return False
                
            try:
                # Verificação extra de None dentro do lock
                if self._redis is None:
                    return False
                await self._redis.delete(key)
                logger.debug(f"[REDIS] DEL {key}")
                return True
            except Exception as e:
                logger.error(f"[REDIS] Erro DEL {key}: {e}")
                # Invalida conexão para forçar reconexão na próxima
                self._redis = None
                return False
    
    async def set_payout(self, asset: str, payout: float, ttl: int = 300):
        """Armazena payout de um ativo (TTL padrão: 5 minutos)"""
        key = f"payout:{asset}"
        return await self.set(key, {"asset": asset, "payout": payout, "source": "pocketoption"}, ttl)
    
    async def get_payout(self, asset: str) -> Optional[Dict]:
        """Obtém payout de um ativo"""
        key = f"payout:{asset}"
        return await self.get(key)
    
    async def set_assets_data(self, assets_data: Dict[str, Any], ttl: int = 300):
        """Armazena dados completos dos ativos"""
        key = "assets:all"
        return await self.set(key, assets_data, ttl)
    
    async def get_assets_data(self) -> Optional[Dict]:
        """Obtém dados completos dos ativos"""
        key = "assets:all"
        return await self.get(key)
    
    async def health_check(self) -> bool:
        """Verifica saúde da conexão Redis"""
        # Usa ensure_connection para reconectar se necessário
        is_healthy = await self._ensure_connection()
        if is_healthy:
            logger.debug("[REDIS] Health check: OK")
        else:
            logger.debug("[REDIS] Health check: falhou")
        return is_healthy


# Instância global
redis_cache = RedisCache()


async def init_redis_cache(host: str = "redis", port: int = 6379, password: str = None) -> bool:
    """Inicializa o cache Redis global"""
    global redis_cache
    redis_cache = RedisCache(host=host, port=port, password=password)
    return await redis_cache.connect()


async def close_redis_cache():
    """Fecha conexão Redis global"""
    global redis_cache
    await redis_cache.disconnect()
