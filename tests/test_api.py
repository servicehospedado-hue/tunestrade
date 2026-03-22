"""
Testes para a API
"""
import pytest
from fastapi.testclient import TestClient
from src.api.routes import app


@pytest.fixture
def client():
    """Fixture para cliente de teste da API"""
    return TestClient(app)


class TestAPIHealth:
    """Testes de health check"""
    
    def test_health_check(self, client):
        """Testa endpoint de health check"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestAPIUsers:
    """Testes para endpoints de usuários"""
    
    def test_register_user(self, client):
        """Testa registro de usuário"""
        response = client.post(
            "/users/register",
            json={
                "user_id": "test_user_123",
                "ssid": "test_ssid_demo",
                "is_demo": True
            }
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert "success" in data or "user_id" in data
    
    def test_get_user(self, client):
        """Testa obtenção de dados do usuário"""
        # Primeiro registrar
        client.post(
            "/users/register",
            json={
                "user_id": "test_user_456",
                "ssid": "test_ssid_demo",
                "is_demo": True
            }
        )
        
        response = client.get("/users/test_user_456")
        assert response.status_code == 200


class TestAPISignals:
    """Testes para endpoints de sinais"""
    
    def test_get_signals(self, client):
        """Testa obtenção de sinais"""
        response = client.get("/signals")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_signal_config(self, client):
        """Testa criação de configuração de sinais"""
        response = client.post(
            "/users/test_user/signals/config",
            json={
                "asset": "EURUSD",
                "timeframe": 60,
                "indicators": [
                    {"name": "rsi", "params": {"period": 14}}
                ]
            }
        )
        assert response.status_code in [200, 201]


class TestAPISystem:
    """Testes para endpoints de sistema"""
    
    def test_system_stats(self, client):
        """Testa obtenção de estatísticas do sistema"""
        response = client.get("/system/stats")
        assert response.status_code == 200
        data = response.json()
        assert "system" in data
        assert "users" in data
