"""
Sistema de Cache
Gerencia cache de dados de candles e resultados de indicadores
"""
import asyncio
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import OrderedDict
import logging
from ..managers.log_manager import get_manager_logger

logger = get_manager_logger("cache_manager")


@dataclass
class CacheEntry:
    """Entrada de cache"""
    key: str
    value: Any
    created_at: datetime
    expires_at: datetime
    access_count: int = 0
    last_accessed: datetime = None


class CacheManager:
    """
    Gerenciador de cache LRU com expiração
    Otimizado para dados de candles e indicadores
    Limitado por uso de memória (MB)
    """
    
    def __init__(self, max_size_mb: int = 512, default_ttl: int = 60):
        self.max_size_mb = max_size_mb
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._current_size_bytes = 0
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Inicia o gerenciador de cache"""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info(f"CacheManager iniciado (max: {self.max_size_mb} MB, TTL: {self.default_ttl}s)")
        logger.info(f"[CACHE] Stats: 0 entradas, 0.00MB, hit_rate: 0%")
        
    async def stop(self):
        """Para o gerenciador de cache"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        self._cache.clear()
        logger.info("CacheManager parado")
        
    async def get(self, key: str) -> Optional[Any]:
        """Obtém valor do cache"""
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                
                # Verificar expiração
                if datetime.now() > entry.expires_at:
                    del self._cache[key]
                    self._misses += 1
                    logger.debug(f"[CACHE] EXPIRADO: {key}")
                    return None
                    
                # Atualizar estatísticas de acesso
                entry.access_count += 1
                entry.last_accessed = datetime.now()
                
                # Mover para o final (LRU)
                self._cache.move_to_end(key)
                
                self._hits += 1
                logger.debug(f"[CACHE] HIT: {key} (acessos: {entry.access_count})")
                return entry.value
                
            self._misses += 1
            logger.debug(f"[CACHE] MISS: {key}")
            return None
            
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Armazena valor no cache"""
        import sys
        async with self._lock:
            ttl = ttl or self.default_ttl
            
            # Estimar tamanho da entrada
            entry_size = sys.getsizeof(key) + sys.getsizeof(value) + 200  # overhead
            
            # Remover entradas antigas se necessário para liberar espaço
            evicted = 0
            while (self._current_size_bytes + entry_size > self.max_size_bytes and 
                   len(self._cache) > 0):
                removed_key, removed_entry = self._cache.popitem(last=False)
                removed_size = sys.getsizeof(removed_key) + sys.getsizeof(removed_entry.value) + 200
                self._current_size_bytes -= removed_size
                evicted += 1
                
            if evicted > 0:
                logger.info(f"[CACHE] EVICT: {evicted} entradas removidas (LRU) para liberar espaco")
                
            now = datetime.now()
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                expires_at=now + timedelta(seconds=ttl),
                last_accessed=now
            )
            
            # Atualizar tamanho se já existia
            if key in self._cache:
                old_entry = self._cache[key]
                old_size = sys.getsizeof(key) + sys.getsizeof(old_entry.value) + 200
                self._current_size_bytes -= old_size
            
            self._cache[key] = entry
            self._cache.move_to_end(key)
            self._current_size_bytes += entry_size
            
            logger.debug(f"[CACHE] SET: {key} (TTL: {ttl}s, tamanho: {entry_size} bytes)")
            # Log INFO a cada 10 sets
            if len(self._cache) % 10 == 0:
                logger.info(f"[CACHE] {len(self._cache)} entradas, {self._current_size_bytes / (1024*1024):.2f}MB")
            
    async def delete(self, key: str) -> bool:
        """Remove entrada do cache e atualiza tamanho"""
        import sys
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                # Calcular e subtrair tamanho
                entry_size = sys.getsizeof(key) + sys.getsizeof(entry.value) + 200
                self._current_size_bytes -= entry_size
                del self._cache[key]
                return True
            return False
            
    async def clear(self):
        """Limpa todo o cache"""
        async with self._lock:
            self._cache.clear()
            logger.info("Cache limpo")
            
    async def clear_user_cache(self, user_id: str):
        """Limpa cache de um usuário específico e atualiza tamanho"""
        import sys
        async with self._lock:
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{user_id}:")]
            for key in keys_to_remove:
                entry = self._cache[key]
                # Calcular e subtrair tamanho
                entry_size = sys.getsizeof(key) + sys.getsizeof(entry.value) + 200
                self._current_size_bytes -= entry_size
                del self._cache[key]
                
    async def _periodic_cleanup(self):
        """Limpa entradas expiradas periodicamente"""
        import sys
        while self._running:
            try:
                await asyncio.sleep(60)  # Log stats a cada 1 minuto
                
                async with self._lock:
                    now = datetime.now()
                    expired_keys = []
                    expired_size = 0
                    
                    for k, v in self._cache.items():
                        if now > v.expires_at:
                            expired_keys.append(k)
                            expired_size += sys.getsizeof(k) + sys.getsizeof(v.value) + 200
                    
                    for key in expired_keys:
                        del self._cache[key]
                    
                    # Atualizar tamanho total
                    self._current_size_bytes -= expired_size
                    
                    # Log de estatísticas periódicas
                    total_entries = len(self._cache)
                    hit_rate = (self._hits / (self._hits + self._misses) * 100) if (self._hits + self._misses) > 0 else 0
                    size_mb = self._current_size_bytes / (1024 * 1024)
                    
                    logger.info(f"[CACHE] Stats: {total_entries} entradas, {size_mb:.2f}MB, hit_rate: {hit_rate:.1f}%")
                    
                    if expired_keys:
                        logger.info(f"[CACHE] Cleanup: {len(expired_keys)} entradas expiradas removidas")
                        
            except Exception as e:
                logger.error(f"Erro na limpeza do cache: {e}")
                
    def get_stats(self) -> Dict:
        """Retorna estatísticas do cache"""
        total = len(self._cache)
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests) if total_requests > 0 else 0
        
        # Estatísticas de idade
        now = datetime.now()
        ages = [(now - entry.created_at).total_seconds() for entry in self._cache.values()]
        avg_age = sum(ages) / len(ages) if ages else 0
        
        # Uso de memória
        usage_mb = self._current_size_bytes / (1024 * 1024)
        
        return {
            "total_entries": total,
            "max_size_mb": self.max_size_mb,
            "current_size_mb": round(usage_mb, 2),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "usage_percentage": (self._current_size_bytes / self.max_size_bytes) * 100,
            "avg_entry_age_seconds": avg_age
        }
        
    def get_candles_key(self, asset: str, timeframe: int, count: int) -> str:
        """Gera chave de cache para candles"""
        return f"candles:{asset}:{timeframe}:{count}"
        
    def get_indicator_key(self, asset: str, timeframe: int, indicator: str, params: Dict) -> str:
        """Gera chave de cache para indicador"""
        params_str = '_'.join(f"{k}={v}" for k, v in sorted(params.items()))
        return f"indicator:{asset}:{timeframe}:{indicator}:{params_str}"
