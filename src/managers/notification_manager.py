"""
Gerenciador de Notificações Push
Envia notificações para usuários via Firebase Cloud Messaging (FCM) ou OneSignal
"""
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import aiohttp
import json

from ..managers.log_manager import get_manager_logger

logger = get_manager_logger("notification_manager")


class NotificationProvider(Enum):
    """Provedores de notificação suportados"""
    FIREBASE = "firebase"      # Firebase Cloud Messaging (gratuito)
    ONESIGNAL = "onesignal"    # OneSignal (gratuito até 10k)
    EXPO = "expo"              # Expo Push (se usar Expo)


@dataclass
class NotificationPayload:
    """Payload de uma notificação"""
    title: str
    body: str
    user_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    priority: str = "high"  # high, normal, low
    badge: Optional[int] = None
    sound: Optional[str] = None
    image: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DeviceToken:
    """Token de dispositivo para notificações"""
    user_id: str
    token: str
    platform: str  # ios, android, web
    provider: NotificationProvider
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    is_active: bool = True


class NotificationManager:
    """
    Gerenciador de notificações push
    Suporta múltiplos provedores (Firebase, OneSignal, Expo)
    """
    
    def __init__(
        self,
        provider: NotificationProvider = NotificationProvider.FIREBASE,
        firebase_credentials: Optional[str] = None,
        onesignal_app_id: Optional[str] = None,
        onesignal_api_key: Optional[str] = None,
        expo_access_token: Optional[str] = None
    ):
        self.provider = provider
        
        # Configurações dos provedores
        self.firebase_credentials = firebase_credentials
        self.onesignal_app_id = onesignal_app_id
        self.onesignal_api_key = onesignal_api_key
        self.expo_access_token = expo_access_token
        
        # Tokens dos dispositivos (user_id -> list of DeviceToken)
        self._device_tokens: Dict[str, List[DeviceToken]] = {}
        
        # Fila de notificações pendentes
        self._notification_queue: asyncio.Queue = asyncio.Queue()
        self._queue_processor_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Estatísticas
        self._stats = {
            "sent": 0,
            "failed": 0,
            "queued": 0,
            "tokens_registered": 0
        }
        
        # HTTP session
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def start(self):
        """Inicia o gerenciador de notificações"""
        logger.info(f"NotificationManager iniciado (provider: {self.provider.value})")
        
        self._running = True
        self._session = aiohttp.ClientSession()
        
        # Iniciar processador de fila
        self._queue_processor_task = asyncio.create_task(self._process_queue())
        
        # Carregar tokens do banco de dados (se disponível)
        await self._load_tokens_from_db()
        
    async def stop(self):
        """Para o gerenciador de notificações"""
        logger.info("NotificationManager parando...")
        
        self._running = False
        
        # Cancelar processador de fila
        if self._queue_processor_task:
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass
        
        # Fechar sessão HTTP
        if self._session:
            await self._session.close()
        
        logger.info("NotificationManager parado")
        
    async def register_device(
        self,
        user_id: str,
        token: str,
        platform: str,
        provider: Optional[NotificationProvider] = None
    ) -> bool:
        """
        Registra token de dispositivo para um usuário
        
        Args:
            user_id: ID do usuário
            token: Token FCM/OneSignal/Expo do dispositivo
            platform: ios, android, ou web
            provider: Provedor de notificação (usa o padrão se não especificado)
            
        Returns:
            bool: True se registrado com sucesso
        """
        try:
            provider = provider or self.provider
            
            device_token = DeviceToken(
                user_id=user_id,
                token=token,
                platform=platform.lower(),
                provider=provider
            )
            
            # Adicionar à lista do usuário
            if user_id not in self._device_tokens:
                self._device_tokens[user_id] = []
            
            # Remover token duplicado se existir
            self._device_tokens[user_id] = [
                t for t in self._device_tokens[user_id]
                if t.token != token
            ]
            
            self._device_tokens[user_id].append(device_token)
            self._stats["tokens_registered"] += 1
            
            logger.info(f"Device token registrado para {user_id} ({platform})")
            
            # Salvar no banco de dados
            await self._save_token_to_db(device_token)
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao registrar device token: {e}")
            return False
            
    async def unregister_device(self, user_id: str, token: str) -> bool:
        """Remove token de dispositivo de um usuário"""
        try:
            if user_id in self._device_tokens:
                original_count = len(self._device_tokens[user_id])
                self._device_tokens[user_id] = [
                    t for t in self._device_tokens[user_id]
                    if t.token != token
                ]
                removed = original_count - len(self._device_tokens[user_id])
                
                if removed > 0:
                    logger.info(f"Device token removido para {user_id}")
                    await self._remove_token_from_db(user_id, token)
                    return True
                    
            return False
            
        except Exception as e:
            logger.error(f"Erro ao remover device token: {e}")
            return False
            
    async def send_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        priority: str = "high"
    ) -> bool:
        """
        Envia notificação para um usuário
        
        Args:
            user_id: ID do usuário
            title: Título da notificação
            body: Corpo/mensagem da notificação
            data: Dados extras (payload)
            priority: high, normal, ou low
            
        Returns:
            bool: True se enviada com sucesso
        """
        try:
            # Verificar se usuário tem tokens registrados
            if user_id not in self._device_tokens or not self._device_tokens[user_id]:
                logger.warning(f"Nenhum device token encontrado para {user_id}")
                return False
            
            # Criar payload
            payload = NotificationPayload(
                title=title,
                body=body,
                user_id=user_id,
                data=data or {},
                priority=priority
            )
            
            # Adicionar à fila para processamento assíncrono
            await self._notification_queue.put(payload)
            self._stats["queued"] += 1
            
            logger.info(f"Notificação enfileirada para {user_id}: {title}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao enfileirar notificação: {e}")
            return False
            
    async def send_bulk_notification(
        self,
        user_ids: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, int]:
        """
        Envia notificação em massa para múltiplos usuários
        
        Returns:
            Dict com estatísticas: {"sent": X, "failed": Y}
        """
        results = {"sent": 0, "failed": 0}
        
        tasks = [
            self.send_notification(uid, title, body, data)
            for uid in user_ids
        ]
        
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results_list:
            if result is True:
                results["sent"] += 1
            else:
                results["failed"] += 1
                
        logger.info(f"Bulk notification: {results['sent']} enviadas, {results['failed']} falhas")
        return results
        
    async def _process_queue(self):
        """Processa fila de notificações em background"""
        while self._running:
            try:
                # Pegar notificação da fila (com timeout para verificar _running)
                try:
                    payload = await asyncio.wait_for(
                        self._notification_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Enviar notificação
                await self._send_to_provider(payload)
                
            except Exception as e:
                logger.error(f"Erro no processador de fila: {e}")
                await asyncio.sleep(1)
                
    async def _send_to_provider(self, payload: NotificationPayload):
        """Envia notificação através do provedor configurado"""
        user_id = payload.user_id
        
        if user_id not in self._device_tokens:
            return
            
        tokens = self._device_tokens[user_id]
        
        for device_token in tokens:
            if not device_token.is_active:
                continue
                
            try:
                if device_token.provider == NotificationProvider.FIREBASE:
                    await self._send_firebase(payload, device_token.token)
                elif device_token.provider == NotificationProvider.ONESIGNAL:
                    await self._send_onesignal(payload, device_token.token)
                elif device_token.provider == NotificationProvider.EXPO:
                    await self._send_expo(payload, device_token.token)
                    
                device_token.last_used = datetime.now()
                self._stats["sent"] += 1
                
            except Exception as e:
                logger.error(f"Erro ao enviar notificação para {user_id}: {e}")
                self._stats["failed"] += 1
                
    async def _send_firebase(self, payload: NotificationPayload, token: str):
        """Envia notificação via Firebase Cloud Messaging"""
        if not self._session:
            return
            
        url = "https://fcm.googleapis.com/fcm/send"
        
        headers = {
            "Authorization": f"key={self.firebase_credentials}",
            "Content-Type": "application/json"
        }
        
        body = {
            "to": token,
            "notification": {
                "title": payload.title,
                "body": payload.body,
                "sound": payload.sound or "default",
                "badge": payload.badge
            },
            "data": payload.data,
            "priority": payload.priority
        }
        
        async with self._session.post(url, headers=headers, json=body) as response:
            if response.status != 200:
                raise Exception(f"FCM error: {response.status}")
                
    async def _send_onesignal(self, payload: NotificationPayload, token: str):
        """Envia notificação via OneSignal"""
        if not self._session:
            return
            
        url = "https://onesignal.com/api/v1/notifications"
        
        headers = {
            "Authorization": f"Basic {self.onesignal_api_key}",
            "Content-Type": "application/json"
        }
        
        body = {
            "app_id": self.onesignal_app_id,
            "include_player_ids": [token],
            "headings": {"en": payload.title},
            "contents": {"en": payload.body},
            "data": payload.data,
            "priority": 10 if payload.priority == "high" else 5
        }
        
        async with self._session.post(url, headers=headers, json=body) as response:
            if response.status != 200:
                raise Exception(f"OneSignal error: {response.status}")
                
    async def _send_expo(self, payload: NotificationPayload, token: str):
        """Envia notificação via Expo Push"""
        if not self._session:
            return
            
        url = "https://exp.host/--/api/v2/push/send"
        
        headers = {
            "Authorization": f"Bearer {self.expo_access_token}",
            "Content-Type": "application/json"
        }
        
        body = {
            "to": token,
            "title": payload.title,
            "body": payload.body,
            "data": payload.data,
            "priority": payload.priority,
            "badge": payload.badge,
            "sound": payload.sound or "default"
        }
        
        async with self._session.post(url, headers=headers, json=body) as response:
            if response.status != 200:
                raise Exception(f"Expo error: {response.status}")
                
    async def _load_tokens_from_db(self):
        """Carrega tokens do banco de dados"""
        # Implementar quando DatabaseManager estiver integrado
        pass
        
    async def _save_token_to_db(self, token: DeviceToken):
        """Salva token no banco de dados"""
        # Implementar quando DatabaseManager estiver integrado
        pass
        
    async def _remove_token_from_db(self, user_id: str, token: str):
        """Remove token do banco de dados"""
        # Implementar quando DatabaseManager estiver integrado
        pass
        
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de notificações"""
        return {
            **self._stats,
            "users_with_tokens": len(self._device_tokens),
            "total_tokens": sum(len(tokens) for tokens in self._device_tokens.values()),
            "provider": self.provider.value,
            "queue_size": self._notification_queue.qsize()
        }
        
    async def test_notification(self, user_id: str) -> bool:
        """Envia notificação de teste para um usuário"""
        return await self.send_notification(
            user_id=user_id,
            title="🧪 Teste de Notificação",
            body="Seu sistema de notificações está funcionando!",
            data={"type": "test", "timestamp": datetime.now().isoformat()}
        )
