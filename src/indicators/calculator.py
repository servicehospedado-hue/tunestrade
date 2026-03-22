"""
Calculadora de Indicadores Técnicos
Usa Factory Pattern para criar indicadores
Integrada com DataCollectorManager para dados reais
"""
import pandas as pd
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta

from .base import IndicatorResult
from .indicators.factory import IndicatorFactory

logger = logging.getLogger(__name__)


@dataclass
class CalculationResult:
    """Resultado completo de cálculo"""
    indicator: str
    asset: str
    timeframe: int
    params: Dict[str, Any]
    current_value: Optional[float]
    previous_value: Optional[float]
    signal: str
    data_points: int
    timestamp: str
    metadata: Optional[Dict] = None
    error: Optional[str] = None


class IndicatorCalculator:
    """
    Calculadora de indicadores usando Factory Pattern
    
    Features:
    - Usa dados reais do DataCollectorManager
    - Executada em threads pelo TaskManager
    - Cache de resultados para performance
    """
    
    def __init__(self, data_collector=None):
        self._data_collector = data_collector
        self._cache: Dict[str, Any] = {}
        
    def set_data_collector(self, data_collector):
        """Define o DataCollectorManager para obter dados reais"""
        self._data_collector = data_collector
        
    def set_asset_storage(self, asset_storage):
        """DEPRECATED: Use set_data_collector"""
        self._data_collector = asset_storage
        
    def calculate(self, indicator_type: str, asset: str, timeframe: int,
                  params: Dict[str, Any], candles_data: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Calcula um indicador técnico usando Factory Pattern
        
        Args:
            indicator_type: Tipo do indicador (sma, ema, rsi, etc)
            asset: Ativo (ex: EURUSD_otc)
            timeframe: Timeframe em segundos
            params: Parâmetros do indicador
            candles_data: Dados de candles opcionais (se não fornecido, usa AssetStorage)
            
        Returns:
            Dicionário com resultados
        """
        try:
            # Obter dados de candles
            if candles_data:
                df = self._candles_to_dataframe(candles_data)
            else:
                df = self._get_candles_data(asset, timeframe, params)
            
            if df.empty:
                return {"error": "No data available", "indicator": indicator_type, "asset": asset}
            
            # Criar indicador via Factory
            indicator = IndicatorFactory.create(indicator_type, params)
            
            # Calcular
            result = indicator.calculate(df)
            
            return CalculationResult(
                indicator=indicator_type,
                asset=asset,
                timeframe=timeframe,
                params=params,
                current_value=result.current_value,
                previous_value=result.previous_value,
                signal=result.signal,
                data_points=len(result.values),
                timestamp=df.index[-1].isoformat() if hasattr(df.index[-1], 'isoformat') else str(df.index[-1]),
                metadata=result.metadata
            ).__dict__
            
        except Exception as e:
            logger.error(f"[Calculator] Erro ao calcular {indicator_type} para {asset}: {e}")
            return {"error": str(e), "indicator": indicator_type, "asset": asset}
    
    def _get_candles_data(self, asset: str, timeframe: int, 
                          params: Dict[str, Any]) -> pd.DataFrame:
        """
        Obtém dados de candles do DataCollectorManager
        
        Se não houver dados reais disponíveis, retorna DataFrame vazio
        para evitar cálculos com dados falsos.
        """
        # Tentar obter dados reais do DataCollectorManager
        if self._data_collector:
            try:
                # Obter ticks do asset
                ticks = self._get_ticks_sync(asset, limit=params.get('period', 14) + 100)
                
                if ticks and len(ticks) > 0:
                    # Converter ticks para DataFrame
                    df = self._ticks_to_dataframe(ticks, timeframe)
                    if not df.empty:
                        logger.debug(f"[Calculator] Usando {len(df)} candles reais para {asset}")
                        return df
            except Exception as e:
                logger.warning(f"[Calculator] Erro ao obter dados reais para {asset}: {e}")
        
        # Sem dados disponíveis - retornar DataFrame vazio
        logger.warning(f"[Calculator] Sem dados reais disponíveis para {asset}")
        return pd.DataFrame()
    
    def _get_ticks_sync(self, asset: str, limit: int = 200) -> List[Dict]:
        """Obtém ticks de forma síncrona (para uso em threads)"""
        import asyncio
        try:
            # Se estiver em um contexto async, usar run_until_complete
            try:
                loop = asyncio.get_running_loop()
                # Já estamos em um loop async - criar uma task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._data_collector.get_asset_data(asset, limit=limit)
                    )
                    return future.result()
            except RuntimeError:
                # Não estamos em um loop async
                return asyncio.run(self._data_collector.get_asset_data(asset, limit=limit))
        except Exception as e:
            logger.error(f"[Calculator] Erro ao obter ticks: {e}")
            return []
    
    def _ticks_to_dataframe(self, ticks: List[Dict], timeframe: int) -> pd.DataFrame:
        """
        Converte ticks (timestamp, price) para DataFrame de candles
        
        Args:
            ticks: Lista de dicts com 'timestamp' e 'price'
            timeframe: Timeframe em segundos para agrupar candles
            
        Returns:
            DataFrame com colunas: open, high, low, close, volume
        """
        if not ticks:
            return pd.DataFrame()
        
        data = []
        ticks_sorted = sorted(ticks, key=lambda x: x['timestamp'])
        
        # Agrupar ticks por timeframe
        current_candle = None
        for tick in ticks_sorted:
            ts = tick['timestamp']
            price = tick['price']
            
            # Calcular o início do candle
            candle_time = (ts // timeframe) * timeframe
            
            if current_candle is None or current_candle['timestamp'] != candle_time:
                # Salvar candle anterior
                if current_candle:
                    data.append(current_candle)
                # Iniciar novo candle
                current_candle = {
                    'timestamp': datetime.fromtimestamp(candle_time),
                    'open': price,
                    'high': price,
                    'low': price,
                    'close': price,
                    'volume': 1
                }
            else:
                # Atualizar candle atual
                current_candle['high'] = max(current_candle['high'], price)
                current_candle['low'] = min(current_candle['low'], price)
                current_candle['close'] = price
                current_candle['volume'] += 1
        
        # Adicionar último candle
        if current_candle:
            data.append(current_candle)
        
        if not data:
            return pd.DataFrame()
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        return df
    
    def _candles_to_dataframe(self, candles: List[Dict]) -> pd.DataFrame:
        """
        Converte lista de candles para DataFrame
        
        Args:
            candles: Lista de dicts com timestamp/time, open, high, low, close, volume
            
        Returns:
            DataFrame indexado por timestamp
        """
        if not candles:
            return pd.DataFrame()
        
        data = []
        for candle in candles:
            ts = candle.get('timestamp') or candle.get('time')
            if ts is None:
                continue
                
            # Converter timestamp para datetime se necessário
            if isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(ts)
            elif isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            
            data.append({
                'timestamp': ts,
                'open': float(candle.get('open', 0)),
                'high': float(candle.get('high', 0)),
                'low': float(candle.get('low', 0)),
                'close': float(candle.get('close', 0)),
                'volume': float(candle.get('volume', 0))
            })
        
        if not data:
            return pd.DataFrame()
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        return df
    
    def calculate_from_dataframe(self, indicator_type: str, df: pd.DataFrame,
                                  params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calcula indicador diretamente de um DataFrame
        
        Útil quando os dados já estão disponíveis
        """
        try:
            if df.empty:
                return {"error": "No data available", "indicator": indicator_type}
            
            indicator = IndicatorFactory.create(indicator_type, params)
            result = indicator.calculate(df)
            
            return CalculationResult(
                indicator=indicator_type,
                asset="",
                timeframe=0,
                params=params,
                current_value=result.current_value,
                previous_value=result.previous_value,
                signal=result.signal,
                data_points=len(result.values),
                timestamp=df.index[-1].isoformat() if hasattr(df.index[-1], 'isoformat') else str(df.index[-1]),
                metadata=result.metadata
            ).__dict__
        except Exception as e:
            logger.error(f"[Calculator] Erro ao calcular {indicator_type}: {e}")
            return {"error": str(e), "indicator": indicator_type}
