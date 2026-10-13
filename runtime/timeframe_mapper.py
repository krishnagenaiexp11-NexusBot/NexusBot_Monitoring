"""
runtime/timeframe_mapper.py
Timeframe Mapper for MT5 integration.
"""
try:
    import MetaTrader5 as mt5
    TIMEFRAME_M1 = mt5.TIMEFRAME_M1
    TIMEFRAME_M5 = mt5.TIMEFRAME_M5
    TIMEFRAME_M15 = mt5.TIMEFRAME_M15
    TIMEFRAME_M30 = mt5.TIMEFRAME_M30
    TIMEFRAME_H1 = mt5.TIMEFRAME_H1
    TIMEFRAME_H4 = mt5.TIMEFRAME_H4
    TIMEFRAME_D1 = mt5.TIMEFRAME_D1
except (ImportError, AttributeError):
    # Safe fallback if library is not active or initialized
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408

TIMEFRAME_MAP = {
    "M1": TIMEFRAME_M1,
    "M5": TIMEFRAME_M5,
    "M15": TIMEFRAME_M15,
    "M30": TIMEFRAME_M30,
    "H1": TIMEFRAME_H1,
    "H4": TIMEFRAME_H4,
    "D1": TIMEFRAME_D1,
}

SUPPORTED_TIMEFRAMES = list(TIMEFRAME_MAP.keys())
