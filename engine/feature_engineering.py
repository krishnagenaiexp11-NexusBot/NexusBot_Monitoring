"""
engine/feature_engineering.py
Canonical indicator computation layer for NexusBot V2.

All V2 strategies call ONLY this module for indicator computation.
No duplicated indicator logic inside strategies.
"""
import pandas as pd
import numpy as np

from utils.indicator_helpers import (
    ema,
    atr,
    rsi,
    adx,
    ema_slope,
    vwap,
    momentum,
    volume_ratio,
    detect_hh_ll,
    compression_score,
    volatility_score,
)


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts raw OHLCV DataFrame into a feature-rich DataFrame.

    Adds:
      - ema_fast(9), ema_slow(21)
      - ema_slope         : rate-of-change of ema_fast over 3 bars
      - atr               : ATR(14)
      - atr_mean          : rolling 20-bar mean of ATR
      - rsi               : RSI(14)
      - adx               : ADX(14)
      - vwap              : intraday VWAP (daily reset)
      - momentum          : close.diff(3)
      - volume_ratio      : volume / rolling_20_mean(volume)
      - hh                : Higher High flag
      - ll                : Lower Low flag
      - compression_score : ATR / rolling_mean_ATR  (< 0.7 = compressed)
      - volatility_score  : normalised ATR 0-100

    Returns a copy of the input with all new columns appended.
    Requires at least 50 rows for meaningful output.
    """
    df = df.copy()

    # ── Trend indicators ────────────────────────────────────────────────────
    df["ema_fast"] = ema(df["close"], 9)
    df["ema_slow"] = ema(df["close"], 21)
    df["ema_slope"] = ema_slope(df["close"], period=9, lookback=3)

    # ── Volatility indicators ────────────────────────────────────────────────
    df["atr"] = atr(df, 14)
    df["atr_mean"] = df["atr"].rolling(20).mean().fillna(df["atr"])

    # ── Momentum indicators ──────────────────────────────────────────────────
    df["rsi"] = rsi(df["close"], 14)
    df["adx"] = adx(df, 14)
    df["momentum"] = momentum(df["close"], 3)

    # ── Volume ───────────────────────────────────────────────────────────────
    df["volume_mean"] = df["volume"].rolling(20).mean().fillna(df["volume"])
    df["volume_ratio"] = volume_ratio(df["volume"], 20)

    # ── VWAP ─────────────────────────────────────────────────────────────────
    df["vwap"] = vwap(df)

    # ── Structure ────────────────────────────────────────────────────────────
    df = detect_hh_ll(df, lookback=5)  # adds 'hh', 'll' columns

    # ── Compression / Volatility scores ──────────────────────────────────────
    df["compression_score"] = compression_score(df["atr"], 20)
    df["volatility_score"] = volatility_score(df["atr"], 20)

    # ── EMA slowing signal (used by exit logic) ───────────────────────────────
    df["ema_slowing"] = df["ema_fast"].diff(1).abs() < df["atr"] * 0.15

    return df


def get_latest_features(df: pd.DataFrame) -> dict:
    """
    Returns the most recent row of a feature-engineered DataFrame as a dict.
    Useful for regime detection and signal generation on the latest candle.
    """
    if df is None or df.empty:
        return {}
    row = df.iloc[-1]
    return row.to_dict()
