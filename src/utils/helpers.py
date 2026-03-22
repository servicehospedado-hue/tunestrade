"""
Utilitários do sistema
"""
import hashlib
import json
from typing import Dict, Any
from datetime import datetime


def generate_cache_key(prefix: str, **kwargs) -> str:
    """Gera chave de cache baseada em parâmetros"""
    data = json.dumps(kwargs, sort_keys=True, default=str)
    hash_obj = hashlib.md5(data.encode())
    return f"{prefix}:{hash_obj.hexdigest()}"


def format_timestamp(dt: datetime) -> str:
    """Formata timestamp para string ISO"""
    return dt.isoformat()


def parse_timestamp(ts: str) -> datetime:
    """Parse de string ISO para datetime"""
    return datetime.fromisoformat(ts)


def validate_asset_symbol(asset: str) -> bool:
    """Valida símbolo de ativo"""
    valid_suffixes = ['_otc', '_crypto', '']
    return any(asset.endswith(suffix) for suffix in valid_suffixes) or '_' in asset


def timeframe_to_seconds(timeframe: str) -> int:
    """Converte timeframe para segundos"""
    mapping = {
        'M1': 60,
        'M5': 300,
        'M15': 900,
        'M30': 1800,
        'H1': 3600,
        'H4': 14400,
        'D1': 86400,
    }
    return mapping.get(timeframe, 60)


def calculate_risk_amount(balance: float, risk_percent: float) -> float:
    """Calcula valor de risco baseado no saldo"""
    return balance * (risk_percent / 100)
