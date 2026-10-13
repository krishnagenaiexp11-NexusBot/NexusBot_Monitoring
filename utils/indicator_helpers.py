"""
utils/indicator_helpers.py
Thin wrappers that expose existing utils.indicators functions under
clean V2 names, plus new helpers not already in utils/indicators.py.
"""
import numpy as np
import pandas as pd

# Re-export existing indicators for use by feature_engineering
from utils.indicators import ema, atr, rsi, adx, supertrend  # noqa: F401


def ema_slope(series: pd.Series, period: int = 9, lookback: int = 3) -> pd.Series:
    """
    Returns the rate-of-change of an EMA over the last `lookback` bars.
    Positive = ascending, negative = descending.
    """
    e = ema(series, period)
    return e.diff(lookback)


def vwap(df: pd.DataFrame) -> pd.Series:
    """
    Intraday VWAP calculated as cumulative (typical_price * volume) / cumulative volume.
    Resets daily. Falls back to rolling 20-bar approximate VWAP if timestamp parsing fails.
    """
    try:
        temp = df.copy()
        temp["timestamp"] = pd.to_datetime(temp["timestamp"])
        temp["typical_price"] = (temp["high"] + temp["low"] + temp["close"]) / 3
        temp["tp_vol"] = temp["typical_price"] * temp["volume"]
        temp["date"] = temp["timestamp"].dt.date
        temp["cum_tp_vol"] = temp.groupby("date")["tp_vol"].cumsum()
        temp["cum_vol"] = temp.groupby("date")["volume"].cumsum()
        return (temp["cum_tp_vol"] / temp["cum_vol"].replace(0, np.nan)).fillna(method="ffill")
    except Exception:
        # Fallback: rolling approximate VWAP
        tp = (df["high"] + df["low"] + df["close"]) / 3
        cum_tp_vol = (tp * df["volume"]).rolling(20).sum()
        cum_vol = df["volume"].rolling(20).sum()
        return (cum_tp_vol / cum_vol.replace(0, np.nan)).fillna(tp)


def momentum(series: pd.Series, period: int = 3) -> pd.Series:
    """Simple rate-of-change momentum."""
    return series.diff(period)


def volume_ratio(volume: pd.Series, period: int = 20) -> pd.Series:
    """Volume relative to its rolling mean. >1.5 = spike, <0.7 = dry."""
    mean_vol = volume.rolling(period).mean()
    return volume / mean_vol.replace(0, np.nan)


def detect_hh_ll(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """
    Adds 'hh' (higher high) and 'll' (lower low) boolean columns.
    A Higher High = current high > max high in prior `lookback` bars.
    A Lower Low   = current low  < min low  in prior `lookback` bars.
    """
    df = df.copy()
    df["hh"] = df["high"] > df["high"].shift(1).rolling(lookback).max()
    df["ll"] = df["low"] < df["low"].shift(1).rolling(lookback).min()
    return df


def compression_score(atr_series: pd.Series, period: int = 20) -> pd.Series:
    """
    ATR relative to its rolling mean.
    <0.7 = compressed (consolidation), >1.4 = expanded (volatile).
    """
    mean_atr = atr_series.rolling(period).mean()
    return atr_series / mean_atr.replace(0, np.nan)


def volatility_score(atr_series: pd.Series, period: int = 20) -> pd.Series:
    """
    Normalise ATR to 0-100 range over a rolling window.
    Provides a scalar volatility reading comparable across instruments.
    """
    rolling_min = atr_series.rolling(period).min()
    rolling_max = atr_series.rolling(period).max()
    denom = (rolling_max - rolling_min).replace(0, np.nan)
    return ((atr_series - rolling_min) / denom * 100).fillna(50.0)
