"""
Rotas de Estratégias - Disponibiliza estratégias e indicadores
"""
from fastapi import APIRouter
from typing import List

from ...managers.log_manager import get_manager_logger
from ...strategies import ScalpingStrategy, TrendM1Strategy

logger = get_manager_logger("strategies_routes")
router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("/available")
async def available_strategies():
    """Retorna estratégias reais disponíveis no sistema"""
    strategies = []
    
    # Scalping5s
    scalping = ScalpingStrategy()
    strategies.append({
        "id": "scalping_5s",
        "name": scalping.name,
        "description": scalping.description,
        "timeframe": scalping.timeframe,
        "min_confidence": scalping.min_confidence,
        "indicators": list(scalping.indicator_weights.keys()),
        "indicator_weights": scalping.indicator_weights,
        "params": {
            "rsi_period": {"default": 14, "min": 5, "max": 30, "type": "int"},
            "ema_fast": {"default": 9, "min": 5, "max": 20, "type": "int"},
            "ema_slow": {"default": 21, "min": 10, "max": 50, "type": "int"},
            "momentum_period": {"default": 10, "min": 5, "max": 20, "type": "int"},
            "stoch_k": {"default": 14, "min": 5, "max": 20, "type": "int"},
            "stoch_d": {"default": 3, "min": 1, "max": 10, "type": "int"},
            "bb_period": {"default": 20, "min": 10, "max": 30, "type": "int"},
            "bb_std": {"default": 2.0, "min": 1.0, "max": 3.0, "type": "float"},
            "macd_fast": {"default": 12, "min": 5, "max": 20, "type": "int"},
            "macd_slow": {"default": 26, "min": 15, "max": 40, "type": "int"},
            "macd_signal": {"default": 9, "min": 5, "max": 15, "type": "int"}
        },
        "category": "Scalping"
    })

    # TrendM1
    trend_m1 = TrendM1Strategy()
    strategies.append({
        "id": "trend_m1",
        "name": trend_m1.name,
        "description": trend_m1.description,
        "timeframe": trend_m1.timeframe,
        "min_confidence": trend_m1.min_confidence,
        "indicators": list(trend_m1.indicator_weights.keys()),
        "indicator_weights": trend_m1.indicator_weights,
        "params": {
            "rsi_period": {"default": 14, "min": 5, "max": 30, "type": "int"},
            "ema_fast": {"default": 9, "min": 5, "max": 20, "type": "int"},
            "ema_slow": {"default": 21, "min": 10, "max": 50, "type": "int"},
            "macd_fast": {"default": 12, "min": 5, "max": 20, "type": "int"},
            "macd_slow": {"default": 26, "min": 15, "max": 40, "type": "int"},
            "macd_signal": {"default": 9, "min": 5, "max": 15, "type": "int"},
            "adx_period": {"default": 14, "min": 5, "max": 30, "type": "int"},
            "stoch_k": {"default": 14, "min": 5, "max": 20, "type": "int"},
            "stoch_d": {"default": 3, "min": 1, "max": 10, "type": "int"},
            "bb_period": {"default": 20, "min": 10, "max": 30, "type": "int"},
            "bb_std": {"default": 2.0, "min": 1.0, "max": 3.0, "type": "float"},
            "cci_period": {"default": 14, "min": 5, "max": 30, "type": "int"},
            "williams_period": {"default": 14, "min": 5, "max": 30, "type": "int"},
            "atr_period": {"default": 14, "min": 5, "max": 30, "type": "int"},
        },
        "category": "Tendência"
    })

    return {
        "strategies": strategies,
        "total": len(strategies)
    }


@router.get("/indicators")
async def available_indicators():
    """Retorna indicadores disponíveis"""
    indicators = [
        # Tendência
        {"id": "sma", "type": "sma", "name": "Simple Moving Average", "description": "Média Móvel Simples", "category": "Tendência", "parameters": {"period": 20}, "is_active": True, "is_default": True},
        {"id": "ema", "type": "ema", "name": "Exponential Moving Average", "description": "Média Móvel Exponencial", "category": "Tendência", "parameters": {"period": 20}, "is_active": True, "is_default": True},
        {"id": "dema", "type": "dema", "name": "Double Exponential Moving Average", "description": "Média Móvel Exponencial Dupla", "category": "Tendência", "parameters": {"period": 20}, "is_active": True, "is_default": False},
        {"id": "hma", "type": "hma", "name": "Hull Moving Average", "description": "Média Móvel Hull", "category": "Tendência", "parameters": {"period": 20}, "is_active": True, "is_default": False},
        {"id": "smma", "type": "smma", "name": "Smoothed Moving Average", "description": "Média Móvel Suavizada", "category": "Tendência", "parameters": {"period": 20}, "is_active": True, "is_default": False},
        {"id": "wma", "type": "wma", "name": "Weighted Moving Average", "description": "Média Móvel Ponderada", "category": "Tendência", "parameters": {"period": 20}, "is_active": True, "is_default": False},
        {"id": "macd", "type": "macd", "name": "MACD", "description": "MACD", "category": "Tendência", "parameters": {"fast": 12, "slow": 26, "signal": 9}, "is_active": True, "is_default": True},
        {"id": "parabolic_sar", "type": "parabolic_sar", "name": "Parabolic SAR", "description": "Parabolic SAR", "category": "Tendência", "parameters": {"initial_af": 0.02, "max_af": 0.2}, "is_active": True, "is_default": False},
        {"id": "ichimoku", "type": "ichimoku", "name": "Ichimoku Cloud", "description": "Ichimoku Cloud", "category": "Tendência", "parameters": {"tenkan_period": 9, "kijun_period": 26, "senkou_span_b_period": 52, "chikou_shift": 26}, "is_active": True, "is_default": False},
        {"id": "super_trend", "type": "super_trend", "name": "Supertrend", "description": "Supertrend", "category": "Tendência", "parameters": {"period": 10, "multiplier": 3}, "is_active": True, "is_default": False},
        
        # Momentum
        {"id": "rsi", "type": "rsi", "name": "Relative Strength Index", "description": "Índice de Força Relativa", "category": "Momentum", "parameters": {"period": 14}, "is_active": True, "is_default": True},
        {"id": "stochastic", "type": "stochastic", "name": "Stochastic Oscillator", "description": "Oscilador Estocástico", "category": "Momentum", "parameters": {"k_period": 14, "d_period": 3}, "is_active": True, "is_default": True},
        {"id": "williams_r", "type": "williams_r", "name": "Williams %R", "description": "Williams %R", "category": "Momentum", "parameters": {"period": 14}, "is_active": True, "is_default": False},
        {"id": "cci", "type": "cci", "name": "Commodity Channel Index", "description": "Commodity Channel Index", "category": "Momentum", "parameters": {"period": 20}, "is_active": True, "is_default": False},
        {"id": "roc", "type": "roc", "name": "Rate of Change", "description": "Rate of Change", "category": "Momentum", "parameters": {"period": 12}, "is_active": True, "is_default": False},
        {"id": "momentum", "type": "momentum", "name": "Momentum", "description": "Momentum", "category": "Momentum", "parameters": {"period": 10}, "is_active": True, "is_default": False},
        {"id": "mfi", "type": "mfi", "name": "Money Flow Index", "description": "Money Flow Index", "category": "Momentum", "parameters": {"period": 14}, "is_active": True, "is_default": False},
        {"id": "awesome_oscillator", "type": "awesome_oscillator", "name": "Awesome Oscillator", "description": "Awesome Oscillator", "category": "Momentum", "parameters": {"fast_period": 5, "slow_period": 34}, "is_active": True, "is_default": False},
        {"id": "tsi", "type": "tsi", "name": "True Strength Index", "description": "True Strength Index", "category": "Momentum", "parameters": {"long_period": 25, "short_period": 13}, "is_active": True, "is_default": False},
        {"id": "ultimate_oscillator", "type": "ultimate_oscillator", "name": "Ultimate Oscillator", "description": "Ultimate Oscillator", "category": "Momentum", "parameters": {"period1": 7, "period2": 14, "period3": 28}, "is_active": True, "is_default": False},
        {"id": "trix", "type": "trix", "name": "TRIX", "description": "TRIX (Triple Exponential Moving Average)", "category": "Momentum", "parameters": {"period": 15}, "is_active": True, "is_default": False},
        
        # Volatilidade
        {"id": "bb", "type": "bb", "name": "Bollinger Bands", "description": "Bandas de Bollinger", "category": "Volatilidade", "parameters": {"period": 20, "std_dev": 2}, "is_active": True, "is_default": True},
        {"id": "atr", "type": "atr", "name": "Average True Range", "description": "Average True Range", "category": "Volatilidade", "parameters": {"period": 14}, "is_active": True, "is_default": True},
        {"id": "keltner_channels", "type": "keltner_channels", "name": "Keltner Channels", "description": "Keltner Channels", "category": "Volatilidade", "parameters": {"period": 20, "atr_multiplier": 2}, "is_active": True, "is_default": False},
        {"id": "donchian_channels", "type": "donchian_channels", "name": "Donchian Channels", "description": "Donchian Channels", "category": "Volatilidade", "parameters": {"period": 20}, "is_active": True, "is_default": False},
        {"id": "adx", "type": "adx", "name": "Average Directional Index", "description": "Average Directional Index", "category": "Volatilidade", "parameters": {"period": 14}, "is_active": True, "is_default": False},
        {"id": "stddev", "type": "stddev", "name": "Standard Deviation", "description": "Standard Deviation", "category": "Volatilidade", "parameters": {"period": 20}, "is_active": True, "is_default": False},
        
        # Volume
        {"id": "obv", "type": "obv", "name": "On Balance Volume", "description": "On Balance Volume", "category": "Volume", "parameters": {}, "is_active": True, "is_default": False},
        {"id": "vwap", "type": "vwap", "name": "Volume Weighted Average Price", "description": "Volume Weighted Average Price", "category": "Volume", "parameters": {}, "is_active": True, "is_default": False},
        {"id": "mfi", "type": "mfi", "name": "Money Flow Index", "description": "Money Flow Index", "category": "Volume", "parameters": {"period": 14}, "is_active": True, "is_default": False},
        {"id": "chaikin_money_flow", "type": "chaikin_money_flow", "name": "Chaikin Money Flow", "description": "Chaikin Money Flow", "category": "Volume", "parameters": {"period": 20}, "is_active": True, "is_default": False},
        {"id": "volume_oscillator", "type": "volume_oscillator", "name": "Volume Oscillator", "description": "Volume Oscillator", "category": "Volume", "parameters": {"fast_period": 12, "slow_period": 26}, "is_active": True, "is_default": False},
        
        # Outros
        {"id": "pivot_points", "type": "pivot_points", "name": "Pivot Points", "description": "Pivot Points", "category": "Outros", "parameters": {}, "is_active": True, "is_default": False},
        {"id": "fibonacci_levels", "type": "fibonacci_levels", "name": "Fibonacci Levels", "description": "Fibonacci Levels", "category": "Outros", "parameters": {}, "is_active": True, "is_default": False},
        {"id": "vortex", "type": "vortex", "name": "Vortex Indicator", "description": "Vortex Indicator", "category": "Outros", "parameters": {"period": 14}, "is_active": True, "is_default": False},
    ]
    
    return {
        "indicators": indicators,
        "total": len(indicators),
        "page": 1,
        "page_size": len(indicators)
    }
