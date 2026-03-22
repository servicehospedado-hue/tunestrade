"""
Classe base para todos os indicadores técnicos
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
import pandas as pd


@dataclass
class IndicatorResult:
    """Resultado do cálculo de um indicador"""
    indicator_type: str
    values: pd.Series
    signal: str = "neutral"
    metadata: Dict[str, Any] = None
    current_value: Optional[float] = None
    previous_value: Optional[float] = None


class BaseIndicator(ABC):
    """Interface base para todos os indicadores"""
    
    def __init__(self, params: Dict[str, Any] = None):
        self.params = params or {}
        self.validate_params()
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nome do indicador"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Descrição do indicador"""
        pass
    
    @property
    @abstractmethod
    def required_params(self) -> list:
        """Parâmetros necessários para o indicador"""
        pass
    
    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> IndicatorResult:
        """Calcula o indicador e retorna resultado"""
        pass
    
    def validate_params(self) -> bool:
        """Valida se os parâmetros são válidos"""
        for param in self.required_params:
            if param not in self.params:
                raise ValueError(f"Parâmetro obrigatório ausente: {param}")
        return True
    
    def get_signal(self, current_value: float, previous_value: float = None) -> str:
        """Gera sinal baseado nos valores calculados"""
        return "neutral"
