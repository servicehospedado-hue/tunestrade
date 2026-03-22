"""
Testes unitários para o módulo de constantes
"""
import pytest
from src.pocketoption.constants import ASSETS, REGIONS, CONNECTION_SETTINGS


def test_assets_has_common_pairs():
    """Verifica se ASSETS contém pares comuns"""
    assert hasattr(ASSETS, 'FOREX')
    assert hasattr(ASSETS, 'OTC')
    assert hasattr(ASSETS, 'COMMODITIES')
    assert len(ASSETS.FOREX) > 0


def test_regions_has_urls():
    """Verifica se REGIONS tem URLs válidas"""
    all_regions = REGIONS.get_all()
    assert len(all_regions) > 0
    assert all(url.startswith('wss://') for url in all_regions)


def test_connection_settings_has_required_keys():
    """Verifica se CONNECTION_SETTINGS tem configurações necessárias"""
    required_keys = ['ping_interval', 'ping_timeout', 'max_reconnect_attempts', 'reconnect_delay']
    for key in required_keys:
        assert key in CONNECTION_SETTINGS


def test_demo_regions_exists():
    """Verifica se há regiões demo disponíveis"""
    demo_regions = REGIONS.get_demo_regions()
    assert len(demo_regions) > 0
    assert all('demo' in url or 'demo' in url.lower() for url in demo_regions)
