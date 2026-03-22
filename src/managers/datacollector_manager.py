"""
DataCollectorManager - Gerenciador de coleta e armazenamento de dados
Responsabilidade: coletar dados de mercado da PocketOption e armazenar em arquivos
"""
import asyncio
import os
from typing import Dict, Optional, Callable, Any, List
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict
import logging

from ..database import DatabaseManager
from ..managers.connection_manager import ConnectionManager

logger = logging.getLogger("data_collector")


@dataclass
class MonitoredAsset:
    """Representa um ativo sendo monitorado"""
    symbol: str
    payout: float
    added_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    file_created: bool = False  # Track if file was successfully created
    subscribed: bool = False    # Track if subscribed to WebSocket
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "payout": self.payout,
            "added_at": self.added_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_active": self.is_active,
            "file_created": self.file_created,
            "subscribed": self.subscribed
        }


class DataCollectorManager:
    """
    Gerenciador de coleta de dados da corretora.
    
    Responsabilidade única: coletar dados de mercado (ativos, payouts, histórico).
    NÃO executa trades (isso é do TradeExecutor).
    NÃO gerencia autotrade (isso é do AutotradeManager).
    
    Features:
    - Conectar contas de monitoramento (actives, payout)
    - Coletar dados de ativos e payouts
    - Salvar dados em arquivos
    - Notificar callbacks quando dados mudam
    """
    
    def __init__(
        self,
        db_manager: DatabaseManager,
        connection_manager: ConnectionManager,
        max_assets: int = 100,
        min_payout: float = 70.0,
    ):
        self.db_manager = db_manager
        self.connection_manager = connection_manager
        
        # Configuração de monitoramento
        self.max_assets = max_assets
        self.min_payout = min_payout
        
        # Estado
        self._running = False
        self._monitoring_accounts: List[str] = []
        
        # Gerenciamento de ativos (movido do active_asset_monitor)
        self._monitored_assets: Dict[str, MonitoredAsset] = {}
        self._all_available_assets: Dict[str, float] = {}  # symbol -> payout
        self._lock = asyncio.Lock()
        self._callbacks: List[Callable] = []
        
        # Callbacks para notificar quando dados mudam
        self._on_asset_added: Optional[Callable[[MonitoredAsset], None]] = None
        self._on_asset_removed: Optional[Callable[[str], None]] = None
        self._on_payout_updated: Optional[Callable[[str, float, float], None]] = None
        
        # Configuração de armazenamento (unificado do AssetStorageManager)
        self.data_dir = Path("data/actives")
        self._storage_buffers: Dict[str, List[str]] = defaultdict(list)
        self._storage_seen_timestamps: Dict[str, set] = defaultdict(set)
        self._storage_last_timestamp: Dict[str, float] = {}
        self._storage_flush_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._ensure_storage_directory()
        
        # Métricas de rebalanceamento
        self._rebalance_count: int = 0
        self._last_rebalance_time: Optional[datetime] = None
        self._failed_unsubscribes: int = 0
        
        logger.info(f"[DataCollector] Configurado (max: {max_assets}, min_payout: {min_payout}%)")
        
    async def start(self):
        """Inicia o coletor de dados"""
        logger.info("[DataCollector] Iniciando...")
        self._running = True
        
        # Limpar arquivos órfãos antes de iniciar
        await self._cleanup_orphan_files()
        
        # Iniciar task de flush periódico (salvar ticks no disco)
        self._storage_flush_task = asyncio.create_task(self._storage_periodic_flush())
        logger.info("[DataCollector] Storage flush task iniciado")
        
        # Iniciar task de cleanup periódico (a cada 5 minutos)
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info("[DataCollector] Periodic cleanup task iniciado")
        
        # Conectar contas de monitoramento em background
        asyncio.create_task(self._connect_monitoring_accounts_background())
        
        logger.info("[DataCollector] Iniciado")
        
    async def stop(self):
        """Para o coletor"""
        logger.info("[DataCollector] Parando...")
        self._running = False
        
        # Cancelar task de flush
        if self._storage_flush_task:
            self._storage_flush_task.cancel()
            try:
                await self._storage_flush_task
            except asyncio.CancelledError:
                pass
        
        # Cancelar task de cleanup
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Flush final antes de parar
        await self._storage_flush_all()
        logger.info("[DataCollector] Flush final concluído")
        
        # Desconectar todas as contas de monitoramento
        for account_id in self._monitoring_accounts:
            try:
                await self.connection_manager.disconnect(account_id)
                logger.info(f"[DataCollector] Conta {account_id} desconectada")
            except Exception as e:
                logger.warning(f"[DataCollector] Erro ao desconectar {account_id}: {e}")
        
        self._monitoring_accounts.clear()
        logger.info("[DataCollector] Parado")
    
    def on_asset_added(self, callback: Callable[[MonitoredAsset], None]):
        """Registra callback para quando ativo é adicionado"""
        self._on_asset_added = callback
        
    def on_asset_removed(self, callback: Callable[[str], None]):
        """Registra callback para quando ativo é removido"""
        self._on_asset_removed = callback
        
    def on_payout_updated(self, callback: Callable[[str, float, float], None]):
        """Registra callback para quando payout é atualizado"""
        self._on_payout_updated = callback
    
    async def _connect_monitoring_accounts_background(self):
        """Conecta contas de monitoramento em background"""
        try:
            # Aguardar um pouco para API iniciar primeiro
            await asyncio.sleep(2)
            logger.info("[DataCollector] Iniciando conexão de contas de monitoramento...")
            await self._connect_monitoring_accounts()
        except Exception as e:
            logger.warning(f"[DataCollector] Erro ao conectar contas: {e}")
    
    async def _connect_monitoring_accounts(self):
        """Lê contas de monitoramento do banco e conecta à corretora"""
        try:
            if not self.db_manager or not self.connection_manager:
                logger.warning("[DataCollector] DatabaseManager ou ConnectionManager não disponível")
                return
            
            # Importar modelo
            from ..database.models import AccountMonitoring
            from sqlalchemy import select
            
            # Buscar contas ativas no banco
            logger.info("[DataCollector] Buscando contas de monitoramento...")
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(AccountMonitoring).where(AccountMonitoring.active == 1)
                )
                accounts = result.scalars().all()
            
            if not accounts:
                logger.warning("[DataCollector] Nenhuma conta de monitoramento ativa")
                return
            
            logger.info(f"[DataCollector] Encontradas {len(accounts)} contas")
            
            # Conectar cada conta
            for account in accounts:
                await self._connect_account(account)
                
        except Exception as e:
            logger.exception(f"[DataCollector] Erro ao conectar contas: {e}")
    
    async def _connect_account(self, account):
        """Conecta uma conta específica de monitoramento"""
        account_id = f"monitoring_{account.name}"
        ssid = account.ssid_system_demo
        
        if not ssid:
            logger.warning(f"[DataCollector] Conta {account.name} não tem SSID")
            return
        
        logger.info(f"[DataCollector] Conectando conta: {account.name}")
        
        # Conectar via ConnectionManager
        connected, msg = await self.connection_manager.connect(
            user_id=account_id,
            ssid=ssid,
            is_demo=True
        )
        
        if connected:
            self._monitoring_accounts.append(account_id)
            logger.info(f"[DataCollector] Conta {account.name} conectada")
            
            # Se for conta 'actives', configurar callbacks
            if account.name == "actives":
                await self._setup_actives_monitoring(account_id)
        else:
            logger.error(f"[DataCollector] Falha ao conectar {account.name}: {msg}")
    
    async def _setup_actives_monitoring(self, account_id: str):
        """Configura monitoramento de ativos para uma conta"""
        
        # Callback quando ativo é adicionado
        async def on_asset_added(event: str, data: dict):
            if event != "asset_added":
                return
            asset = data.get("asset")
            if not asset:
                return
            try:
                await self.create_asset_file(asset.symbol)
                await self._subscribe_to_asset(account_id, asset.symbol)
            except Exception as e:
                logger.error(f"[DC] Erro ao adicionar {asset.symbol}: {e}")
        
        # Callback quando ativo é removido
        async def on_asset_removed(event: str, data: dict):
            if event != "asset_removed":
                return
            symbol = data.get("symbol")
            if not symbol:
                return
            
            logger.info(f"[DC] Callback ativo removido: {symbol} - iniciando unsubscribe com retry")
            
            max_retries = 3
            retry_delay = 0.5
            
            for attempt in range(max_retries):
                try:
                    client = self.connection_manager.get_client(account_id)
                    if not client:
                        logger.error(f"[DC] Cliente não encontrado para unsubscribe: {symbol}")
                        break
                    
                    success = await client.unsubscribe_from_asset(symbol)
                    if success:
                        logger.info(f"[DC] Unsubscribe bem-sucedido: {symbol}")
                        return
                    else:
                        logger.warning(f"[DC] Unsubscribe falhou (tentativa {attempt+1}/{max_retries}): {symbol}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                except Exception as e:
                    logger.error(f"[DC] Erro ao fazer unsubscribe de {symbol} (tentativa {attempt+1}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
            
            logger.error(f"[DC] Falha ao fazer unsubscribe de {symbol} após {max_retries} tentativas")
            
            # Garantir que o arquivo seja deletado mesmo se unsubscribe falhar
            try:
                await self.delete_asset_file(symbol)
                logger.info(f"[DC] Arquivo deletado após falha de unsubscribe: {symbol}")
            except Exception as e:
                logger.error(f"[DC] Erro ao deletar arquivo após falha de unsubscribe: {symbol}: {e}")
        
        # Callback quando payout é atualizado
        async def on_payout_updated(event: str, data: dict):
            if event != "payout_updated":
                return
            # payout updates são silenciosos
            pass
        
        # Registrar callbacks
        self.add_callback(on_asset_added)
        self.add_callback(on_asset_removed)
        self.add_callback(on_payout_updated)
        
        # Sincronizar ativos já existentes
        await self._sync_existing_assets(account_id)
    
    async def _sync_existing_assets(self, account_id: str):
        """Sincroniza ativos já existentes no monitoramento"""
        existing_assets = list(self._monitored_assets.values())
        if not existing_assets:
            logger.info("[DataCollector] Nenhum ativo para sincronizar")
            return
        
        logger.info(f"[DataCollector] Sincronizando {len(existing_assets)} ativos...")
        
        # Limpar arquivos que não estão na lista de monitoramento
        await self._cleanup_unmonitored_files()
        
        for asset in existing_assets:
            try:
                # Criar arquivo
                await self.create_asset_file(asset.symbol)
                
                # Inscrever no WebSocket
                await self._subscribe_to_asset(account_id, asset.symbol)
                
            except Exception as e:
                logger.error(f"[DataCollector] Erro ao sincronizar {asset.symbol}: {e}")
    
    async def _subscribe_to_asset(self, account_id: str, symbol: str):
        """Inscreve em um ativo via WebSocket e solicita histórico de candles M1"""
        try:
            client = self.connection_manager.get_client(account_id)
            if not client:
                logger.error(f"[DC] Cliente não encontrado para {account_id}")
                return
            
            # Resolver nome correto do asset para get_candles (stocks OTC precisam de '#' prefixo)
            # Ex: AMZN_otc -> #AMZN_otc para get_candles, mas subfor usa AMZN_otc (sem #)
            from ..pocketoption.constants import ASSETS
            candles_symbol = symbol
            if symbol not in ASSETS and f"#{symbol}" in ASSETS:
                candles_symbol = f"#{symbol}"
            
            # Pedir candles de 60s (M1) — TrendM1 precisa de candles de 1 minuto
            history_candles = 100
            
            # Solicitar histórico de candles M1
            try:
                candles = await client.get_candles(asset=candles_symbol, timeframe=60, count=history_candles)
                if candles:
                    added = await self._prepend_historical_candles_m1(symbol, candles)
                    logger.info(f"[DC] {symbol}: {added}/{len(candles)} candles M1 históricos carregados")
                else:
                    logger.warning(f"[DC] {symbol}: nenhum candle histórico retornado")
            except Exception as e:
                logger.warning(f"[DC] Erro histórico {symbol}: {e}")
            
            # Inscrever tempo real — subfor usa símbolo sem '#' (ex: AMZN_otc, não #AMZN_otc)
            result = await client.subscribe_to_asset(symbol)
            if result:
                if symbol in self._monitored_assets:
                    self._monitored_assets[symbol].subscribed = True
                    logger.info(f"[DC] {symbol} inscrito com sucesso")
            else:
                logger.warning(f"[DC] Falha inscrição {symbol}")
                
        except Exception as e:
            logger.error(f"[DC] Erro ao inscrever {symbol}: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do coletor"""
        return {
            "running": self._running,
            "monitoring_accounts": len(self._monitoring_accounts),
            "accounts": self._monitoring_accounts,
            "monitored_assets": len(self._monitored_assets),
            "available_assets": len(self._all_available_assets),
            "max_assets": self.max_assets,
            "min_payout": self.min_payout,
            "buffer_size": sum(len(ticks) for ticks in self._storage_buffers.values()),
            "last_rebalance": self._last_rebalance_time.isoformat() if self._last_rebalance_time else None,
            "rebalance_count": self._rebalance_count,
            "failed_unsubscribes": self._failed_unsubscribes,
        }
    
    # ========== Métodos de Gerenciamento de Ativos (movidos do active_asset_monitor) ==========
    
    def add_callback(self, callback: Callable):
        """Adiciona callback para mudanças nos ativos monitorados"""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable):
        """Remove callback"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    async def _notify_callbacks(self, event: str, data: Any):
        """Notifica callbacks de mudanças"""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event, data)
                else:
                    callback(event, data)
            except Exception as e:
                logger.error(f"[DC] Erro no callback: {e}")
    
    async def update_all_assets(self, assets_data: Dict[str, Any]):
        """
        Atualiza todos os ativos disponíveis e rebalanceia se necessário
        assets_data: dict com dados dos ativos {symbol: payout}
        """
        added_assets = []
        removed_assets = []
        
        async with self._lock:
            # Validar dados de entrada
            validated_assets = {}
            for symbol, payout in assets_data.items():
                try:
                    payout_float = float(payout)
                    # Validar range razoável (0-100%)
                    if 0 <= payout_float <= 100:
                        validated_assets[symbol] = payout_float
                    else:
                        logger.warning(f"[DC] Payout inválido para {symbol}: {payout} (fora do range 0-100)")
                except (ValueError, TypeError):
                    logger.warning(f"[DC] Payout não é número para {symbol}: {payout}")
            
            self._all_available_assets = validated_assets
            
            # Filtrar ativos com payout suficiente
            valid_assets = {
                symbol: payout for symbol, payout in validated_assets.items()
                if payout >= self.min_payout
            }
            
            # Ordenar por payout (maior primeiro)
            sorted_assets = sorted(valid_assets.items(), key=lambda x: x[1], reverse=True)
            
            # Selecionar top ativos
            selected = sorted_assets[:self.max_assets]
            selected_symbols = {symbol for symbol, _ in selected}
            
            # Atualizar payout de ativos já monitorados
            for symbol in list(self._monitored_assets.keys()):
                if symbol in validated_assets:
                    new_payout = validated_assets[symbol]
                    old_payout = self._monitored_assets[symbol].payout
                    if new_payout != old_payout:
                        self._monitored_assets[symbol].payout = new_payout
                        self._monitored_assets[symbol].updated_at = datetime.now()
                        logger.debug(f"[DC] Payout atualizado: {symbol} {old_payout}% -> {new_payout}%")
            
            # Adicionar novos ativos
            for symbol, payout in selected:
                if symbol not in self._monitored_assets:
                    asset = MonitoredAsset(symbol=symbol, payout=payout)
                    self._monitored_assets[symbol] = asset
                    added_assets.append(asset)
            
            # Coletar ativos a remover
            for symbol in list(self._monitored_assets.keys()):
                if symbol not in selected_symbols:
                    removed_assets.append(symbol)
            
            # Remover da memória
            for symbol in removed_assets:
                if symbol in self._monitored_assets:
                    del self._monitored_assets[symbol]
        
        # Processar remoções FORA do lock
        for symbol in removed_assets:
            logger.info(f"[DC] Processando remoção do ativo: {symbol}")
            
            # FLUSH BUFFER FIRST para evitar perda de dados
            try:
                async with self._lock:
                    if symbol in self._storage_buffers and self._storage_buffers[symbol]:
                        try:
                            file_path = self._get_storage_file_path(symbol)
                            content = '\n'.join(self._storage_buffers[symbol]) + '\n'
                            await asyncio.to_thread(self._storage_append_to_file, file_path, content)
                            self._storage_buffers[symbol] = []
                            logger.info(f"[DC] Buffer flushed antes da remoção: {symbol}")
                        except Exception as e:
                            logger.error(f"[DC] Erro ao flush buffer de {symbol}: {e}")
            except Exception as e:
                logger.error(f"[DC] Erro ao preparar remoção de {symbol}: {e}")
            
            # THEN notificar callbacks (fazer unsubscribe)
            await self._notify_callbacks("asset_removed", {"symbol": symbol})
            
            # FINALLY deletar arquivo
            try:
                deleted = await self.delete_asset_file(symbol)
                logger.info(f"[DC] Arquivo {symbol} deletado: {deleted}")
            except Exception as e:
                logger.error(f"[DC] Erro ao deletar arquivo de {symbol}: {e}")
        
        # Notificar adições
        for asset in added_assets:
            await self._notify_callbacks("asset_added", {"asset": asset})
        
        # Log resumido
        if added_assets or removed_assets:
            logger.info(f"[DC] Rebalance: +{len(added_assets)} -{len(removed_assets)} | total: {len(self._monitored_assets)}")
            self._rebalance_count = getattr(self, '_rebalance_count', 0) + 1
            self._last_rebalance_time = datetime.now()
    
    async def _add_asset(self, symbol: str, payout: float) -> MonitoredAsset:
        """Adiciona um ativo ao monitoramento"""
        asset = MonitoredAsset(symbol=symbol, payout=payout)
        self._monitored_assets[symbol] = asset
        await self._notify_callbacks("asset_added", {"asset": asset})
        return asset
    
    async def _remove_asset(self, symbol: str):
        """Remove um ativo do monitoramento e deleta arquivo de dados"""
        if symbol in self._monitored_assets:
            logger.info(f"[DC] Removendo ativo do monitoramento: {symbol}")
            del self._monitored_assets[symbol]
            
            # Notificar callbacks (isso vai triggerar unsubscribe)
            await self._notify_callbacks("asset_removed", {"symbol": symbol})
            
            # Deletar arquivo (redundante mas garante limpeza)
            try:
                await self.delete_asset_file(symbol)
                logger.info(f"[DC] Arquivo do ativo removido: {symbol}")
            except Exception as e:
                logger.error(f"[DC] Erro ao deletar arquivo de {symbol}: {e}")
    
    async def update_asset_payout(self, symbol: str, new_payout: float):
        """Atualiza o payout de um ativo"""
        async with self._lock:
            if symbol in self._monitored_assets:
                asset = self._monitored_assets[symbol]
                old_payout = asset.payout
                asset.payout = new_payout
                asset.updated_at = datetime.now()
                
                await self._notify_callbacks("payout_updated", {
                    "symbol": symbol,
                    "payout": new_payout,
                    "old_payout": old_payout
                })
                
                logger.debug(f"[DataCollector] Payout atualizado: {symbol} {old_payout}% -> {new_payout}%")
                
                # Se payout caiu muito, remover ativo
                if new_payout < self.min_payout:
                    await self._remove_asset(symbol)
    
    def get_monitored_assets(self) -> List[MonitoredAsset]:
        """Retorna lista de ativos sendo monitorados"""
        return list(self._monitored_assets.values())
    
    def get_asset(self, symbol: str) -> Optional[MonitoredAsset]:
        """Retorna um ativo específico"""
        return self._monitored_assets.get(symbol)
    
    def is_monitoring(self, symbol: str) -> bool:
        """Verifica se um ativo está sendo monitorado"""
        return symbol in self._monitored_assets
    
    # ========== Métodos de Armazenamento (unificado do AssetStorageManager) ==========
    
    def _ensure_storage_directory(self):
        """Garante que o diretório de dados existe"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_storage_file_path(self, asset: str) -> Path:
        """Retorna o caminho do arquivo para um ativo"""
        safe_asset = "".join(c for c in asset if c.isalnum() or c in "_-").strip()
        return self.data_dir / f"{safe_asset}.txt"
        
    def _normalize_asset_name(self, asset: str) -> str:
        """Normaliza o nome do asset removendo prefixo #"""
        return asset.lstrip('#') if asset else asset
        
    async def _storage_periodic_flush(self):
        """Flush periódico do buffer a cada 1 segundo"""
        while self._running:
            try:
                await asyncio.sleep(1.0)
                await self._storage_flush_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DataCollector] Erro no flush periódico: {e}")
    
    async def _periodic_cleanup(self):
        """Cleanup periódico de arquivos órfãos (a cada 5 minutos)"""
        while self._running:
            try:
                await asyncio.sleep(300)  # 5 minutos
                logger.debug("[DC] Executando cleanup periódico de arquivos órfãos")
                await self._cleanup_orphan_files()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DC] Erro no cleanup periódico: {e}")
                
    async def _storage_flush_all(self):
        """Salva todos os buffers pendentes"""
        async with self._lock:
            for asset, ticks in list(self._storage_buffers.items()):
                if not ticks:
                    continue
                try:
                    file_path = self._get_storage_file_path(asset)
                    content = '\n'.join(ticks) + '\n'
                    await asyncio.to_thread(self._storage_append_to_file, file_path, content)
                    self._storage_buffers[asset] = []
                except Exception as e:
                    logger.error(f"[DataCollector] Erro ao salvar ticks de {asset}: {e}")
                    
    def _storage_append_to_file(self, file_path: Path, content: str):
        """Operação síncrona de append (executada em thread)"""
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(content)
            
    async def _storage_load_existing_timestamps(self, asset: str):
        """Carrega timestamps existentes do arquivo para deduplicação"""
        asset = self._normalize_asset_name(asset)
        try:
            file_path = self._get_storage_file_path(asset)
            if not file_path.exists():
                return
            
            timestamps = set()
            last_ts = 0.0
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#') or not line:
                        continue
                    parts = line.split(',')
                    if len(parts) >= 2:
                        try:
                            ts = float(parts[0])
                            timestamps.add(ts)
                            if ts > last_ts:
                                last_ts = ts
                        except ValueError:
                            continue
            
            self._storage_seen_timestamps[asset] = timestamps
            self._storage_last_timestamp[asset] = last_ts
            logger.debug(f"[DataCollector] {len(timestamps)} timestamps carregados para {asset}")
        except Exception as e:
            logger.error(f"[DataCollector] Erro ao carregar timestamps de {asset}: {e}")
            
    async def create_asset_file(self, asset: str) -> bool:
        """Cria arquivo de dados para um ativo"""
        asset = self._normalize_asset_name(asset)
        try:
            file_path = self._get_storage_file_path(asset)
            if not file_path.exists():
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Asset: {asset}\n")
                    f.write(f"# Created: {datetime.now().isoformat()}\n")
                    f.write(f"# Format: timestamp,price\n")
            else:
                await self._storage_load_existing_timestamps(asset)
            
            # Mark file as created
            if asset in self._monitored_assets:
                self._monitored_assets[asset].file_created = True
                logger.debug(f"[DC] Arquivo criado/marcado para {asset}")
            
            return True
        except Exception as e:
            logger.error(f"[DC] Erro ao criar arquivo {asset}: {e}")
            return False
            
    async def delete_asset_file(self, asset: str) -> bool:
        """Deleta arquivo de dados de um ativo"""
        original_asset = asset
        asset = self._normalize_asset_name(asset)
        
        try:
            file_path = self._get_storage_file_path(asset)
            logger.info(f"[DC] delete_asset_file: original={original_asset} normalized={asset} path={file_path}")
            
            # Check if file was ever created
            asset_obj = self._monitored_assets.get(asset)
            if asset_obj and not asset_obj.file_created:
                logger.debug(f"[DC] Arquivo nunca foi criado para {asset}, pulando deleção")
                return True  # Not an error, file was never created
            
            # Cleanup buffers INSIDE lock
            async with self._lock:
                if asset in self._storage_buffers:
                    del self._storage_buffers[asset]
                if asset in self._storage_seen_timestamps:
                    del self._storage_seen_timestamps[asset]
                if asset in self._storage_last_timestamp:
                    del self._storage_last_timestamp[asset]
            
            # Delete file OUTSIDE lock para não bloquear operações de coleta
            if file_path.exists():
                await asyncio.to_thread(self._delete_file_sync, file_path)
                logger.info(f"[DC] Arquivo deletado com sucesso: {file_path}")
            else:
                # Only warn if file was supposed to exist
                if asset_obj and asset_obj.file_created:
                    logger.warning(f"[DC] Arquivo deveria existir mas não encontrado: {file_path}")
                else:
                    logger.debug(f"[DC] Arquivo não existe (nunca foi criado): {file_path}")
            
            return True
        except Exception as e:
            logger.error(f"[DC] Erro ao deletar {asset}: {e}")
            return False
    
    def _delete_file_sync(self, file_path: Path):
        """Operação síncrona de delete (executada em thread)"""
        if file_path.exists():
            file_path.unlink()
            
    async def append_tick(self, asset: str, price: float, timestamp: Optional[float] = None) -> bool:
        """Adiciona um tick ao buffer com deduplicação (silencioso)"""
        asset = self._normalize_asset_name(asset)
        try:
            if timestamp is None:
                timestamp = datetime.now().timestamp()
            
            # Deduplicação
            if timestamp in self._storage_seen_timestamps[asset]:
                return False
            
            # Verificação temporal
            last_ts = self._storage_last_timestamp.get(asset, 0.0)
            if timestamp < last_ts:
                return False  # Out-of-order, ignora silenciosamente
            
            self._storage_seen_timestamps[asset].add(timestamp)
            self._storage_last_timestamp[asset] = timestamp
            
            tick_line = f"{timestamp},{price}"
            self._storage_buffers[asset].append(tick_line)
            return True
        except Exception as e:
            logger.error(f"[DC] Erro tick {asset}: {e}")
            return False
            
    async def append_candles(self, asset: str, candles: List[Dict[str, Any]]) -> bool:
        """Salva candles como ticks (apenas close price)"""
        try:
            for candle in candles:
                close = candle.get("close")
                timestamp = candle.get("timestamp") or candle.get("time")
                if close and timestamp:
                    await self.append_tick(asset, float(close), float(timestamp))
            return True
        except Exception as e:
            logger.error(f"[DataCollector] Erro ao adicionar candles para {asset}: {e}")
            return False

    async def _prepend_historical_candles_m1(self, asset: str, candles: list) -> int:
        """
        Reescreve o arquivo do asset colocando candles M1 históricos no início,
        seguidos dos ticks em tempo real já existentes que sejam mais recentes.
        Isso garante que TrendM1 sempre tenha dados suficientes ao reiniciar.
        Retorna o número de candles históricos adicionados.
        """
        asset_norm = self._normalize_asset_name(asset)
        try:
            # Parsear candles recebidos
            historical = []
            for candle in candles:
                if isinstance(candle, dict):
                    close = candle.get('close') or candle.get('price')
                    ts = candle.get('time') or candle.get('timestamp')
                else:
                    close = getattr(candle, 'close', None) or getattr(candle, 'price', None)
                    ts = getattr(candle, 'time', None) or getattr(candle, 'timestamp', None)
                if close and ts:
                    # Normalizar timestamp para múltiplo de 60
                    ts_norm = (int(float(ts)) // 60) * 60
                    historical.append((float(ts_norm), float(close)))

            if not historical:
                return 0

            # Ordenar histórico por timestamp
            historical.sort(key=lambda x: x[0])
            hist_min_ts = historical[0][0]
            hist_max_ts = historical[-1][0]

            # Ler ticks existentes no arquivo (apenas os mais recentes que o histórico)
            file_path = self._get_storage_file_path(asset_norm)
            existing_recent = []
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#') or not line:
                            continue
                        parts = line.split(',')
                        if len(parts) >= 2:
                            try:
                                ts_val = float(parts[0])
                                price_val = float(parts[1])
                                # Manter apenas ticks mais recentes que o último candle histórico
                                if ts_val > hist_max_ts:
                                    existing_recent.append((ts_val, price_val))
                            except ValueError:
                                continue

            # Reescrever arquivo: header + histórico + ticks recentes
            async with self._lock:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Asset: {asset_norm}\n")
                    f.write(f"# Updated: {datetime.now().isoformat()}\n")
                    f.write(f"# Format: timestamp,price\n")
                    for ts_val, price_val in historical:
                        f.write(f"{ts_val},{price_val}\n")
                    for ts_val, price_val in existing_recent:
                        f.write(f"{ts_val},{price_val}\n")

                # Atualizar estado de deduplicação
                all_ts = {ts for ts, _ in historical} | {ts for ts, _ in existing_recent}
                self._storage_seen_timestamps[asset_norm] = all_ts
                all_sorted = sorted(all_ts)
                self._storage_last_timestamp[asset_norm] = all_sorted[-1] if all_sorted else 0.0
                self._storage_buffers[asset_norm] = []  # Limpar buffer pendente

            return len(historical)

        except Exception as e:
            logger.error(f"[DC] Erro ao reescrever histórico M1 para {asset_norm}: {e}")
            return 0
            
    async def append_history_data(self, asset: str, history: List[List]) -> int:
        """
        Salva dados de histórico (formato: [[timestamp, price], ...])
        Retorna número de ticks adicionados
        """
        added = 0
        try:
            for tick in history:
                if isinstance(tick, (list, tuple)) and len(tick) >= 2:
                    timestamp = tick[0]
                    price = tick[1]
                    if await self.append_tick(asset, float(price), float(timestamp)):
                        added += 1
            logger.debug(f"[DataCollector] {added} ticks de histórico salvos para {asset}")
            return added
        except Exception as e:
            logger.error(f"[DataCollector] Erro ao adicionar histórico para {asset}: {e}")
            return 0
            
    async def get_asset_data(self, asset: str, limit: int = 1000) -> Optional[List[Dict[str, Any]]]:
        """Retorna os últimos ticks armazenados para um ativo"""
        asset = self._normalize_asset_name(asset)
        try:
            file_path = self._get_storage_file_path(asset)
            if not file_path.exists():
                return None
                
            ticks = []
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    line = line.strip()
                    if line.startswith('#') or not line:
                        continue
                    parts = line.split(',')
                    if len(parts) >= 2:
                        ticks.append({
                            "timestamp": float(parts[0]),
                            "price": float(parts[1])
                        })
            return ticks
        except Exception as e:
            logger.error(f"[DataCollector] Erro ao ler dados de {asset}: {e}")
            return None
            
    def list_stored_assets(self) -> List[str]:
        """Lista todos os ativos que têm arquivos de dados"""
        try:
            files = list(self.data_dir.glob("*.txt"))
            return [f.stem for f in files]
        except Exception as e:
            logger.error(f"[DataCollector] Erro ao listar ativos: {e}")
            return []
    
    async def _cleanup_orphan_files(self):
        """Remove arquivos de ativos que não estão sendo monitorados"""
        try:
            stored_assets = self.list_stored_assets()
            monitored_symbols = set(self._monitored_assets.keys())
            
            orphans = [asset for asset in stored_assets if asset not in monitored_symbols]
            
            if orphans:
                logger.info(f"[DataCollector] Encontrados {len(orphans)} arquivos órfãos para limpar")
                for asset in orphans:
                    try:
                        await self.delete_asset_file(asset)
                        logger.info(f"[DataCollector] Arquivo órfão removido: {asset}")
                    except Exception as e:
                        logger.error(f"[DataCollector] Erro ao remover arquivo órfão {asset}: {e}")
            else:
                logger.info("[DataCollector] Nenhum arquivo órfão encontrado")
                
        except Exception as e:
            logger.error(f"[DataCollector] Erro na limpeza de arquivos órfãos: {e}")
    
    async def _cleanup_unmonitored_files(self):
        """Remove arquivos de ativos que não estão na lista de monitoramento atual"""
        try:
            stored_assets = self.list_stored_assets()
            monitored_symbols = set(self._monitored_assets.keys())
            
            # Arquivos que existem mas não deveriam
            to_remove = [asset for asset in stored_assets if asset not in monitored_symbols]
            
            if to_remove:
                logger.info(f"[DataCollector] Removendo {len(to_remove)} arquivos não monitorados")
                for asset in to_remove:
                    try:
                        await self.delete_asset_file(asset)
                        logger.info(f"[DataCollector] Arquivo não monitorado removido: {asset}")
                    except Exception as e:
                        logger.error(f"[DataCollector] Erro ao remover {asset}: {e}")
            
        except Exception as e:
            logger.error(f"[DataCollector] Erro na limpeza de arquivos não monitorados: {e}")
