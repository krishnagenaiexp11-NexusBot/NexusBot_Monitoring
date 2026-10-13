"""
utils/validation.py
DataFrame validation helpers for V2 pipeline.

Includes a robust auto-normalization layer that handles MT5 export
column name variants BEFORE strict validation runs.
"""
import pandas as pd
import numpy as np


REQUIRED_OHLCV_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}

# ── Column alias maps ─────────────────────────────────────────────────────────
# Each key = canonical name, values = accepted aliases (case-insensitive matching)
_COLUMN_ALIASES: dict[str, list[str]] = {
    "timestamp": [
        "timestamp", "time", "datetime", "date",
        "Date", "Time", "DateTime", "Datetime",
        "open_time", "opentime", "bar_time",
    ],
    "open":   ["open",   "Open",   "OPEN"],
    "high":   ["high",   "High",   "HIGH"],
    "low":    ["low",    "Low",    "LOW"],
    "close":  ["close",  "Close",  "CLOSE"],
    "volume": [
        "volume", "Volume", "VOLUME",
        "tick_volume", "TickVol", "tickvol",
        "real_volume", "RealVol", "realvol",
        "vol", "Vol",
    ],
}

# Build lowercase → canonical lookup for fast matching
_ALIAS_LOOKUP: dict[str, str] = {}
for _canonical, _aliases in _COLUMN_ALIASES.items():
    for _alias in _aliases:
        _ALIAS_LOOKUP[_alias.lower()] = _canonical


class DataValidationError(Exception):
    """Raised when the uploaded dataset fails validation after normalization."""


# ── Normalization ─────────────────────────────────────────────────────────────

def normalize_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Attempts to map raw column names → canonical OHLCV names.

    Handles:
      - Case variations (Open, OPEN, open)
      - MT5 alias variants (tick_volume, TickVol, etc.)
      - Separate Date + Time columns → combined timestamp column

    Returns:
        (normalized_df, normalization_report)

    normalization_report keys:
        original_columns  : list of raw column names as uploaded
        mapped            : dict {raw → canonical} for successfully mapped cols
        unmapped          : list of raw columns that could not be mapped
        date_time_merged  : bool — True if Date+Time were merged
        missing_after     : set of still-missing canonical columns
    """
    df = df.copy()
    original_columns = list(df.columns)

    # ── Step 1: try to merge separate Date + Time columns ─────────────────────
    date_time_merged = False
    col_lower = {c.lower(): c for c in df.columns}

    date_col = col_lower.get("date") or col_lower.get("date")
    time_col = col_lower.get("time")

    # Only merge if neither is already a combined datetime
    if date_col and time_col and "timestamp" not in col_lower:
        try:
            combined = (
                df[date_col].astype(str).str.strip()
                + " "
                + df[time_col].astype(str).str.strip()
            )
            parsed = pd.to_datetime(combined)
            df["timestamp"] = parsed
            # Drop the separate columns so they don't conflict with mapping below
            df = df.drop(columns=[date_col, time_col], errors="ignore")
            date_time_merged = True
        except Exception:
            pass  # leave original columns intact; mapping will try individually

    # ── Step 2: map remaining columns via alias lookup ─────────────────────────
    rename_map: dict[str, str] = {}
    mapped:     dict[str, str] = {}   # original_name → canonical
    unmapped:   list[str]      = []

    for raw_col in df.columns:
        canonical = _ALIAS_LOOKUP.get(raw_col.lower())
        if canonical and canonical not in rename_map.values():
            rename_map[raw_col] = canonical
            mapped[raw_col]     = canonical
        else:
            unmapped.append(raw_col)

    df = df.rename(columns=rename_map)

    # ── Step 3: report what's still missing ───────────────────────────────────
    present = set(df.columns)
    missing_after = REQUIRED_OHLCV_COLUMNS - present

    report = {
        "original_columns": original_columns,
        "mapped":           mapped,
        "unmapped":         [c for c in unmapped if c not in rename_map],
        "date_time_merged": date_time_merged,
        "missing_after":    missing_after,
    }
    return df, report


# ── Validation ────────────────────────────────────────────────────────────────

def validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Full pipeline:
      1. Auto-normalize column names (MT5 aliases, Date+Time merge, etc.)
      2. Validate all required columns exist after normalization
      3. Parse types, clean NaN, sort, deduplicate
      4. Sanity-check OHLCV integrity

    Returns the cleaned, canonical-schema DataFrame.
    Raises DataValidationError with a descriptive message on failure.
    """
    if df is None or not isinstance(df, pd.DataFrame):
        raise DataValidationError("Input is not a DataFrame.")
    if df.empty:
        raise DataValidationError("DataFrame is empty.")

    # ── Normalize ─────────────────────────────────────────────────────────────
    df, report = normalize_columns(df)

    if report["missing_after"]:
        original_cols = ", ".join(report["original_columns"])
        missing_str   = ", ".join(sorted(report["missing_after"]))
        raise DataValidationError(
            f"Missing required columns after normalization: [{missing_str}]. "
            f"Original columns found: [{original_cols}]. "
            f"Successfully mapped: {report['mapped']}. "
            f"Could not map: {report['unmapped']}. "
            "Supported aliases — timestamp: time/date/datetime/Date/Time; "
            "volume: tick_volume/TickVol/real_volume/Volume."
        )

    # ── Keep only canonical columns + any extras (passthrough) ────────────────
    # (extras like spread, symbol etc. are kept for downstream use)

    # ── Parse timestamp ────────────────────────────────────────────────────────
    try:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    except Exception as exc:
        raise DataValidationError(
            f"Cannot parse 'timestamp' column as datetime: {exc}. "
            "Ensure the timestamp format is recognizable (e.g. 2024-01-15 09:00:00)."
        )

    # ── Coerce OHLCV to numeric ────────────────────────────────────────────────
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Drop rows with NaN in OHLC columns ────────────────────────────────────
    rows_before = len(df)
    df = df.dropna(subset=["open", "high", "low", "close"])
    if df.empty:
        raise DataValidationError(
            "All rows contain NaN in OHLC columns after type coercion. "
            "Check that open/high/low/close are numeric values."
        )

    # ── Fill volume NaN with 0 (some brokers omit volume) ─────────────────────
    df["volume"] = df["volume"].fillna(0.0)

    # ── Sort chronologically ───────────────────────────────────────────────────
    df = df.sort_values("timestamp").reset_index(drop=True)

    # ── Remove duplicates (keep last occurrence per timestamp) ─────────────────
    df = df.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)

    # ── Sanity checks ──────────────────────────────────────────────────────────
    bad_rows = (df["high"] < df["low"]).sum()
    if bad_rows > 0:
        # Remove bad rows rather than hard-failing — some brokers export oddities
        df = df[df["high"] >= df["low"]].reset_index(drop=True)

    if len(df) < 100:
        raise DataValidationError(
            f"Dataset has only {len(df)} valid rows after cleaning "
            f"(started with {rows_before}). At least 100 candles are required."
        )

    return df


def get_dataset_summary(df: pd.DataFrame) -> dict:
    """Returns a summary dict for display in the UI."""
    if df is None or df.empty:
        return {}
    return {
        "rows":              len(df),
        "start":             str(df["timestamp"].iloc[0]),
        "end":               str(df["timestamp"].iloc[-1]),
        "avg_volume":        float(df["volume"].mean()),
        "price_range_high":  float(df["high"].max()),
        "price_range_low":   float(df["low"].min()),
    }


def get_normalization_report(df_raw: pd.DataFrame) -> dict:
    """
    Returns a normalization report WITHOUT modifying or validating the DataFrame.
    Useful for UI preview of what the pipeline would detect.
    """
    try:
        _, report = normalize_columns(df_raw.copy())
        return report
    except Exception as exc:
        return {"error": str(exc)}
