"""
Testes para os gerenciadores do sistema
"""
import pytest
import asyncio
from datetime import datetime

from src.managers.task_manager import TaskManager, Task
from src.managers.signal_manager import SignalManager, SignalConfig
from src.managers.cache.manager import CacheManager


@pytest.fixture
async def task_manager():
    """Fixture para TaskManager"""
    tm = TaskManager(max_workers=4, max_concurrent_tasks=10)
    await tm.start()
    yield tm
    await tm.stop()


@pytest.fixture
async def signal_manager():
    """Fixture para SignalManager"""
    sm = SignalManager(max_signals_per_user=10)
    await sm.start()
    yield sm
    await sm.stop()


@pytest.fixture
async def cache_manager():
    """Fixture para CacheManager"""
    cm = CacheManager(max_size_mb=10, default_ttl=5)
    await cm.start()
    yield cm
    await cm.stop()


class TestTaskManager:
    """Testes para TaskManager"""
    
    @pytest.mark.asyncio
    async def test_create_task(self, task_manager):
        """Testa criação de tarefa"""
        task_id = await task_manager.create_task(
            user_id="user_123",
            asset="EURUSD",
            timeframe=60,
            indicator_type="rsi",
            params={"period": 14}
        )
        assert task_id is not None
        assert len(task_id) > 0
    
    @pytest.mark.asyncio
    async def test_get_task(self, task_manager):
        """Testa recuperação de tarefa"""
        task_id = await task_manager.create_task(
            user_id="user_123",
            asset="EURUSD",
            timeframe=60,
            indicator_type="rsi",
            params={"period": 14}
        )
        task = task_manager.get_task(task_id)
        assert task is not None
        assert task.user_id == "user_123"
        assert task.asset == "EURUSD"
    
    @pytest.mark.asyncio
    async def test_cancel_task(self, task_manager):
        """Testa cancelamento de tarefa"""
        task_id = await task_manager.create_task(
            user_id="user_123",
            asset="EURUSD",
            timeframe=60,
            indicator_type="rsi",
            params={"period": 14}
        )
        result = await task_manager.cancel_task(task_id)
        assert result is True
        task = task_manager.get_task(task_id)
        assert task.status == "cancelled"
    
    @pytest.mark.asyncio
    async def test_get_user_tasks(self, task_manager):
        """Testa recuperação de tarefas do usuário"""
        # Criar múltiplas tarefas
        for i in range(3):
            await task_manager.create_task(
                user_id="user_123",
                asset="EURUSD",
                timeframe=60,
                indicator_type="rsi",
                params={"period": 14}
            )
        
        tasks = task_manager.get_user_tasks("user_123")
        assert len(tasks) == 3
    
    @pytest.mark.asyncio
    async def test_get_stats(self, task_manager):
        """Testa estatísticas do gerenciador"""
        stats = task_manager.get_stats()
        assert "total" in stats
        assert "pending" in stats
        assert "running" in stats
        assert "completed" in stats
        assert "failed" in stats


class TestSignalManager:
    """Testes para SignalManager"""
    
    @pytest.mark.asyncio
    async def test_generate_signal(self, signal_manager):
        """Testa geração de sinal"""
        signal = await signal_manager.generate_signal(
            user_id="user_123",
            asset="EURUSD",
            timeframe=60,
            signal_type="buy",
            confidence=0.85,
            metadata={"rsi": 30, "trend": "up"}
        )
        assert signal is not None
        assert signal.user_id == "user_123"
        assert signal.asset == "EURUSD"
    
    @pytest.mark.asyncio
    async def test_get_user_signals(self, signal_manager):
        """Testa recuperação de sinais do usuário"""
        # Gerar alguns sinais
        for i in range(3):
            await signal_manager.generate_signal(
                user_id="user_123",
                asset="EURUSD",
                timeframe=60,
                signal_type="buy",
                confidence=0.85
            )
        
        signals = signal_manager.get_user_signals("user_123")
        assert len(signals) == 3
    
    @pytest.mark.asyncio
    async def test_update_signal_status(self, signal_manager):
        """Testa atualização de status do sinal"""
        signal = await signal_manager.generate_signal(
            user_id="user_123",
            asset="EURUSD",
            timeframe=60,
            signal_type="buy",
            confidence=0.85
        )
        
        signal_manager.update_signal_status(signal.id, "executed")
        updated = signal_manager.get_signal(signal.id)
        assert updated.status.value == "executed"
    
    @pytest.mark.asyncio
    async def test_get_stats(self, signal_manager):
        """Testa estatísticas do gerenciador"""
        stats = signal_manager.get_stats()
        assert "total" in stats
        assert "pending" in stats
        assert "executed" in stats
        assert "expired" in stats


class TestCacheManager:
    """Testes para CacheManager"""
    
    @pytest.mark.asyncio
    async def test_set_and_get(self, cache_manager):
        """Testa set e get de valores"""
        await cache_manager.set("key1", "value1", ttl=10)
        value = await cache_manager.get("key1")
        assert value == "value1"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent(self, cache_manager):
        """Testa get de chave inexistente"""
        value = await cache_manager.get("nonexistent")
        assert value is None
    
    @pytest.mark.asyncio
    async def test_delete(self, cache_manager):
        """Testa delete de chave"""
        await cache_manager.set("key1", "value1", ttl=10)
        await cache_manager.delete("key1")
        value = await cache_manager.get("key1")
        assert value is None
    
    @pytest.mark.asyncio
    async def test_cache_candle_key(self, cache_manager):
        """Testa geração de chave para candles"""
        key = cache_manager.get_candle_cache_key("EURUSD", 60)
        assert "candle" in key
        assert "EURUSD" in key
        assert "60" in key
    
    @pytest.mark.asyncio
    async def test_cache_indicator_key(self, cache_manager):
        """Testa geração de chave para indicadores"""
        key = cache_manager.get_indicator_cache_key("rsi", "EURUSD", 60, {"period": 14})
        assert "indicator" in key
        assert "rsi" in key
        assert "EURUSD" in key
    
    @pytest.mark.asyncio
    async def test_get_stats(self, cache_manager):
        """Testa estatísticas do cache"""
        stats = cache_manager.get_stats()
        assert "total_entries" in stats
        assert "max_size_mb" in stats
        assert "current_size_mb" in stats
        assert "hit_rate" in stats
