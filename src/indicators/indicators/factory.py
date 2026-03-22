"""
Factory para criar instâncias de indicadores
"""
from typing import Dict, Type
from ..base import BaseIndicator
from .sma import SMAIndicator
from .ema import EMAIndicator
from .rsi import RSIIndicator
from .macd import MACDIndicator
from .bb import BBIndicator
from .atr import ATRIndicator
from .stochastic import StochasticIndicator
from .wma import WMAIndicator
from .hma import HMAIndicator
from .vwap import VWAPIndicator
from .smma import SMMAIndicator
from .dema import DEMAIndicator
from .cci import CCIIndicator
from .momentum import MomentumIndicator
from .williams_r import WilliamsRIndicator
from .awesome_oscillator import AwesomeOscillatorIndicator
from .ultimate_oscillator import UltimateOscillatorIndicator
from .roc import ROCIndicator
from .adx import ADXIndicator
from .parabolic_sar import ParabolicSARIndicator
from .ichimoku import IchimokuIndicator
from .super_trend import SuperTrendIndicator
from .vortex import VortexIndicator
from .obv import OBVIndicator
from .mfi import MFIIndicator
from .chaikin_money_flow import ChaikinMoneyFlowIndicator
from .volume_oscillator import VolumeOscillatorIndicator
from .keltner_channels import KeltnerChannelsIndicator
from .donchian_channels import DonchianChannelsIndicator
from .stddev import StdDevIndicator
from .fibonacci_levels import FibonacciLevelsIndicator
from .pivot_points import PivotPointsIndicator
from .tsi import TSIIndicator
from .trix import TRIXIndicator


class IndicatorFactory:
    """Factory para criar indicadores"""
    
    _indicators: Dict[str, Type[BaseIndicator]] = {
        "sma": SMAIndicator,
        "ema": EMAIndicator,
        "rsi": RSIIndicator,
        "macd": MACDIndicator,
        "bb": BBIndicator,
        "atr": ATRIndicator,
        "stochastic": StochasticIndicator,
        "wma": WMAIndicator,
        "hma": HMAIndicator,
        "vwap": VWAPIndicator,
        "smma": SMMAIndicator,
        "dema": DEMAIndicator,
        "cci": CCIIndicator,
        "momentum": MomentumIndicator,
        "williams_r": WilliamsRIndicator,
        "awesome_oscillator": AwesomeOscillatorIndicator,
        "ultimate_oscillator": UltimateOscillatorIndicator,
        "roc": ROCIndicator,
        "adx": ADXIndicator,
        "parabolic_sar": ParabolicSARIndicator,
        "ichimoku": IchimokuIndicator,
        "super_trend": SuperTrendIndicator,
        "vortex": VortexIndicator,
        "obv": OBVIndicator,
        "mfi": MFIIndicator,
        "cmf": ChaikinMoneyFlowIndicator,
        "chaikin_money_flow": ChaikinMoneyFlowIndicator,
        "volume_oscillator": VolumeOscillatorIndicator,
        "keltner_channels": KeltnerChannelsIndicator,
        "donchian_channels": DonchianChannelsIndicator,
        "stddev": StdDevIndicator,
        "fibonacci": FibonacciLevelsIndicator,
        "fibonacci_levels": FibonacciLevelsIndicator,
        "pivot_points": PivotPointsIndicator,
        "tsi": TSIIndicator,
        "trix": TRIXIndicator,
    }
    
    @classmethod
    def create(cls, indicator_type: str, params: dict = None) -> BaseIndicator:
        """Cria uma instância do indicador"""
        indicator_type = indicator_type.lower()
        
        if indicator_type not in cls._indicators:
            raise ValueError(f"Indicador desconhecido: {indicator_type}")
        
        indicator_class = cls._indicators[indicator_type]
        return indicator_class(params)
    
    @classmethod
    def get_available(cls) -> Dict[str, str]:
        """Retorna lista de indicadores disponíveis"""
        return {
            name: indicator_class().description
            for name, indicator_class in cls._indicators.items()
        }
    
    @classmethod
    def register(cls, name: str, indicator_class: Type[BaseIndicator]):
        """Registra um novo indicador"""
        cls._indicators[name.lower()] = indicator_class
