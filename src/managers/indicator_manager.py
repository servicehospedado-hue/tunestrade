"""
Gerenciador de Indicadores
Coordena cálculos de indicadores técnicos para múltiplos usuários
"""
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from ..managers.log_manager import get_manager_logger

logger = get_manager_logger("indicator_manager")


@dataclass
class IndicatorRequest:
    """Requisição de cálculo de indicador"""
    user_id: str
    asset: str
    timeframe: int
    indicator_type: str
    params: Dict[str, Any]
    priority: int = 1  # 1 = alta, 2 = média, 3 = baixa


class IndicatorManager:
    """
    Gerenciador central de indicadores
    Coordena cálculos e cache de indicadores técnicos
    """
    
    def __init__(self, cache_manager):
        self.cache = cache_manager
        self._indicator_registry: Dict[str, Any] = {}
        self._user_indicator_configs: Dict[str, List[Dict]] = {}
        self._running = False
        
    async def start(self):
        """Inicia o gerenciador de indicadores"""
        self._running = True
        self._register_default_indicators()
        logger.info("IndicatorManager iniciado")
        logger.info(f"Indicadores disponíveis: {list(self._indicator_registry.keys())}")
        # Iniciar loop de status periódico
        asyncio.create_task(self._status_loop())
        
    async def _status_loop(self):
        """Loga status periódico do sistema de indicadores"""
        await asyncio.sleep(30)  # Aguardar sistema inicializar
        while self._running:
            try:
                stats = self.get_stats()
                logger.info(
                    f"[STATUS] Indicadores registrados: {stats['registered_indicators']} | "
                    f"Usuários configurados: {stats['configured_users']} | "
                    f"Disponíveis: {stats['available_indicators']}"
                )
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no loop de status: {e}")
                await asyncio.sleep(60)
        
    async def stop(self):
        """Para o gerenciador de indicadores"""
        self._running = False
        logger.info("IndicatorManager parado")
        
    def _register_default_indicators(self):
        """Registra indicadores padrão disponíveis"""
        self._indicator_registry = {
            'sma': {'name': 'SMA', 'description': 'Média Móvel Simples', 'params': ['period']},
            'ema': {'name': 'EMA', 'description': 'Média Móvel Exponencial', 'params': ['period']},
            'rsi': {'name': 'RSI', 'description': 'Índice de Força Relativa', 'params': ['period']},
            'macd': {'name': 'MACD', 'description': 'MACD', 'params': ['fast', 'slow', 'signal']},
            'bb': {'name': 'Bollinger Bands', 'description': 'Bandas de Bollinger', 'params': ['period', 'std_dev']},
            'atr': {'name': 'ATR', 'description': 'Average True Range', 'params': ['period']},
            'stochastic': {'name': 'Stochastic', 'description': 'Oscilador Estocástico', 'params': ['k_period', 'd_period']},
        }
        
    async def calculate_indicator(self, request: IndicatorRequest,
                                  callback: Optional[Any] = None) -> str:
        """
        Submete requisição de cálculo de indicador.
        Verifica cache primeiro; se não encontrado, retorna "pending" (cálculo é feito
        diretamente pelas estratégias via DynamicStrategy/ScalpingStrategy).
        """
        cache_key = self._generate_cache_key(request)
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit para {request.asset}/{request.indicator_type}")
            if callback:
                await callback(cached_result)
            return "cached"
        return "pending"
        
    async def calculate_multiple(self, user_id: str, asset: str, timeframe: int,
                                  indicators: List[Dict[str, Any]]) -> List[str]:
        """Calcula múltiplos indicadores simultaneamente"""
        task_ids = []
        
        for ind_config in indicators:
            request = IndicatorRequest(
                user_id=user_id,
                asset=asset,
                timeframe=timeframe,
                indicator_type=ind_config.get('type', 'sma'),
                params=ind_config.get('params', {})
            )
            
            task_id = await self.calculate_indicator(request)
            task_ids.append(task_id)
            
        return task_ids
        
    def _generate_cache_key(self, request: IndicatorRequest) -> str:
        """Gera chave de cache para uma requisição"""
        params_str = '_'.join(f"{k}={v}" for k, v in sorted(request.params.items()))
        return f"{request.asset}:{request.timeframe}:{request.indicator_type}:{params_str}"
        
    async def cache_result(self, request: IndicatorRequest, result: Any, ttl: int = 60):
        """Armazena resultado em cache"""
        cache_key = self._generate_cache_key(request)
        await self.cache.set(cache_key, result, ttl)
        
    def get_available_indicators(self) -> Dict[str, Any]:
        """Retorna indicadores disponíveis"""
        return self._indicator_registry
        
    def validate_indicator_config(self, indicator_type: str, params: Dict[str, Any]) -> bool:
        """Valida configuração de um indicador"""
        if indicator_type not in self._indicator_registry:
            return False
            
        # Validações básicas de parâmetros
        if indicator_type == 'sma' or indicator_type == 'ema':
            return 'period' in params and isinstance(params['period'], int) and params['period'] > 0
        elif indicator_type == 'rsi':
            return 'period' in params and isinstance(params['period'], int) and 2 <= params['period'] <= 100
        elif indicator_type == 'macd':
            return all(p in params for p in ['fast', 'slow', 'signal'])
            
        return True
        
    async def set_user_indicators(self, user_id: str, indicators: List[Dict[str, Any]]):
        """Define indicadores ativos para um usuário"""
        # Validar configurações
        valid_indicators = []
        for ind in indicators:
            ind_type = ind.get('type', '')
            params = ind.get('params', {})
            
            if self.validate_indicator_config(ind_type, params):
                valid_indicators.append(ind)
            else:
                logger.warning(f"Configuração inválida ignorada: {ind_type}")
                
        self._user_indicator_configs[user_id] = valid_indicators
        logger.info(f"Usuário {user_id} configurou {len(valid_indicators)} indicadores")
        
    def get_user_indicators(self, user_id: str) -> List[Dict[str, Any]]:
        """Retorna indicadores configurados de um usuário"""
        return self._user_indicator_configs.get(user_id, [])
        
    async def warmup_cache(self, asset: str, timeframe: int, indicators: List[Dict[str, Any]]):
        """Pré-calcula indicadores para cache quente"""
        # Implementação para warmup de cache
        pass
        
    def get_stats(self) -> Dict:
        """Retorna estatísticas do gerenciador"""
        return {
            "registered_indicators": len(self._indicator_registry),
            "configured_users": len(self._user_indicator_configs),
            "available_indicators": list(self._indicator_registry.keys())
        }
