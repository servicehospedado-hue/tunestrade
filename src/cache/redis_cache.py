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
    
    def __init__(self, host: str = "redis", port: int = 6379, db: int = 0):
        self.host = host
        self.port = port
        self.db = db
        self._redis: Optional[Any] = None
        self._lock = asyncio.Lock()
        
    async def connect(self):
        """Conecta ao Redis com fallback para localhost"""
        logger.info("[REDIS] Conectando...")
        if not REDIS_AVAILABLE or Redis is None:
            logger.warning("[REDIS] aioredis não instalado - cache desativado")
            return False
        
        # Tentar hosts: primeiro o configurado, depois localhost como fallback
        hosts_to_try = [self.host]
        if self.host != "localhost" and self.host != "127.0.0.1":
            hosts_to_try.extend(["localhost", "127.0.0.1"])
        
        last_error = None
        for host in hosts_to_try:
            try:
                self._redis = Redis.from_url(
                    f"redis://{host}:{self.port}/{self.db}",
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
                return True
            except Exception as e:
                last_error = e
                logger.debug(f"[REDIS] Falha ao conectar em {host}: {e}")
                self._redis = None
                continue
        
        logger.error(f"[REDIS] Erro ao conectar em todos os hosts: {last_error}")
        return False
    
    async def disconnect(self):
        """Desconecta do Redis"""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("[REDIS] Desconectado")
    
    async def _ensure_connection(self) -> bool:
        """Verifica e reconecta ao Redis se necessário"""
        if not self._redis:
            return await self.connect()
        
        try:
            # Testa se a conexão ainda está ativa
            await self._redis.ping()
            return True
        except Exception:
            # Conexão perdida, tenta reconectar
            logger.warning("[REDIS] Conexão perdida, tentando reconectar...")
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


async def init_redis_cache(host: str = "redis", port: int = 6379) -> bool:
    """Inicializa o cache Redis global"""
    global redis_cache
    redis_cache = RedisCache(host=host, port=port)
    return await redis_cache.connect()


async def close_redis_cache():
    """Fecha conexão Redis global"""
    global redis_cache
    await redis_cache.disconnect()
