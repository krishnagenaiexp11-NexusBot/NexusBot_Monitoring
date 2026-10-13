"""
utils/timeframes.py
Timeframe detection and helper utilities for V2 pipeline.
"""
import pandas as pd


def detect_timeframe(df: pd.DataFrame) -> str:
    """
    Infers the dominant candle timeframe from a timestamp column.
    Returns a human-readable label: 'M1', 'M5', 'M15', 'H1', 'H4', 'D1', 'UNKNOWN'.
    """
    if df is None or df.empty or "timestamp" not in df.columns:
        return "UNKNOWN"

    try:
        ts = pd.to_datetime(df["timestamp"]).sort_values().reset_index(drop=True)
        deltas = ts.diff().dropna()
        if deltas.empty:
            return "UNKNOWN"
        median_delta = deltas.median()
        total_seconds = int(median_delta.total_seconds())

        mapping = {
            60: "M1",
            300: "M5",
            900: "M15",
            1800: "M30",
            3600: "H1",
            14400: "H4",
            86400: "D1",
        }
        # Allow 10% tolerance
        for seconds, label in sorted(mapping.items()):
            if abs(total_seconds - seconds) <= seconds * 0.1:
                return label
        return f"~{total_seconds}s"
    except Exception:
        return "UNKNOWN"


def resample_to_h1(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resamples a higher-frequency DataFrame to H1 OHLCV.
    Requires 'timestamp' column (datetime-parseable).
    """
    try:
        temp = df.copy()
        temp["timestamp"] = pd.to_datetime(temp["timestamp"])
        temp = temp.sort_values("timestamp").set_index("timestamp")
        agg_dict = {
            "open": ("open", "first"),
            "high": ("high", "max"),
            "low": ("low", "min"),
            "close": ("close", "last"),
            "volume": ("volume", "sum"),
        }
        if "symbol" in temp.columns:
            agg_dict["symbol"] = ("symbol", "first")
        h1 = temp.resample("1h").agg(**agg_dict).dropna().reset_index()
        return h1
    except Exception:
        return df.copy()


def resample_to_m15(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resamples a higher-frequency DataFrame to M15 OHLCV.
    """
    try:
        temp = df.copy()
        temp["timestamp"] = pd.to_datetime(temp["timestamp"])
        temp = temp.sort_values("timestamp").set_index("timestamp")
        agg_dict = {
            "open": ("open", "first"),
            "high": ("high", "max"),
            "low": ("low", "min"),
            "close": ("close", "last"),
            "volume": ("volume", "sum"),
        }
        if "symbol" in temp.columns:
            agg_dict["symbol"] = ("symbol", "first")
        m15 = temp.resample("15min").agg(**agg_dict).dropna().reset_index()
        return m15
    except Exception:
        return df.copy()


def session_label(timestamp) -> str:
    """Returns the trading session for a given UTC timestamp."""
    try:
        dt = pd.to_datetime(timestamp)
        hour = dt.hour
        if 8 <= hour < 13:
            return "London"
        elif 13 <= hour < 17:
            return "NY Overlap"
        elif 17 <= hour < 22:
            return "NY"
        else:
            return "Asian"
    except Exception:
        return "Unknown"
