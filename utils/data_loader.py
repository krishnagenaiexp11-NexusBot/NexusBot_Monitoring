from pathlib import Path
import hashlib
import pandas as pd


REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
TIME_ALIASES = ["timestamp", "time", "datetime", "date"]
VOLUME_ALIASES = ["volume", "tick_volume", "tickvolume", "tick_vol", "tickvol", "tick_volun", "real_volume", "realvolume"]


def _clean_column_name(column: str) -> str:
    return (
        str(column)
        .strip()
        .lower()
        .replace("<", "")
        .replace(">", "")
        .replace(" ", "_")
    )


def resolve_symbol(df=None, sidebar_symbol=None):
    if df is not None and "symbol" in df.columns:
        s = df["symbol"].dropna()
        if not s.empty:
            return str(s.iloc[-1]).upper()
    if sidebar_symbol:
        return str(sidebar_symbol).upper()
    return "UNKNOWN"


def load_ohlcv_csv(source) -> pd.DataFrame:
    df = pd.read_csv(source, sep=None, engine="python")
    df.columns = [_clean_column_name(col) for col in df.columns]

    if "timestamp" not in df.columns and "datetime" not in df.columns and {"date", "time"}.issubset(df.columns):
        df["timestamp"] = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()

    timestamp_col = next((col for col in TIME_ALIASES if col in df.columns), None)
    volume_col = _select_volume_column(df)

    rename_map = {}
    if timestamp_col:
        rename_map[timestamp_col] = "timestamp"
    if volume_col:
        rename_map[volume_col] = "volume"
    df = df.rename(columns=rename_map)

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        expected = "timestamp/time, open, high, low, close, and volume/tick_volume/real_volume"
        found = ", ".join(df.columns)
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}. Expected {expected}. Found: {found}")

    cols_to_keep = list(REQUIRED_COLUMNS)
    if "symbol" in df.columns:
        cols_to_keep.append("symbol")
    df = df[cols_to_keep].copy()
    df["timestamp"] = _parse_timestamp(df["timestamp"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().sort_values("timestamp").reset_index(drop=True)
    if df.empty:
        raise ValueError("CSV did not contain valid OHLCV rows")
    return df


def _select_volume_column(df: pd.DataFrame) -> str | None:
    if "volume" in df.columns:
        return "volume"

    real_volume_cols = [col for col in ["real_volume", "realvolume"] if col in df.columns]
    for col in real_volume_cols:
        values = pd.to_numeric(df[col], errors="coerce").fillna(0)
        if values.abs().sum() > 0:
            return col

    return next((col for col in VOLUME_ALIASES if col in df.columns), None)


def _parse_timestamp(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    parsed = pd.to_datetime(text, errors="coerce", utc=True)
    missing = parsed.isna()
    if missing.any():
        parsed_dayfirst = pd.to_datetime(text[missing], errors="coerce", utc=True, dayfirst=True)
        parsed.loc[missing] = parsed_dayfirst
    return parsed


def save_uploaded_dataset(uploaded_file, datasets_dir: str = "datasets") -> Path:
    path = Path(datasets_dir) / uploaded_file.name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(uploaded_file.getbuffer())
    return path


def get_dataset_fingerprint(df, filename="dataset"):
    try:
        if df is None or not hasattr(df, "empty") or df.empty:
            return {
                "name": filename,
                "dataset_name": filename,
                "row_count": 0,
                "rows": 0,
                "timeframe": "Unknown",
                "hash": "empty",
                "sha256": "empty",
                "fingerprint": f"{filename}_Unknown_0_empty"
            }
        
        rows_count = len(df)
        timeframe = "Unknown"
        time_col = None
        for col in ["timestamp", "time", "datetime", "date"]:
            if col in df.columns:
                time_col = col
                break
                
        if time_col is not None:
            try:
                temp_time = pd.to_datetime(df[time_col], errors="coerce")
                temp_time = temp_time.dropna().sort_values()
                if len(temp_time) > 1:
                    time_diff = temp_time.diff().median()
                    if pd.notna(time_diff):
                        minutes = time_diff.total_seconds() / 60.0
                        if minutes == 1.0:
                            timeframe = "M1"
                        elif minutes == 5.0:
                            timeframe = "M5"
                        elif minutes == 15.0:
                            timeframe = "M15"
                        elif minutes == 60.0:
                            timeframe = "H1"
                        elif minutes == 240.0:
                            timeframe = "H4"
                        elif minutes == 1440.0:
                            timeframe = "D1"
                        else:
                            timeframe = f"{int(minutes)}min"
            except Exception:
                pass
                
        h = "unknown"
        if "close" in df.columns:
            try:
                close_vals = pd.to_numeric(df["close"], errors="coerce").fillna(0.0).values
                close_bytes = close_vals.tobytes()
                h = hashlib.sha256(close_bytes).hexdigest()[:12]
            except Exception:
                pass
                
        return {
            "name": filename,
            "dataset_name": filename,
            "row_count": rows_count,
            "rows": rows_count,
            "timeframe": timeframe,
            "hash": h,
            "sha256": h,
            "fingerprint": f"{filename}_{timeframe}_{rows_count}_{h}"
        }
    except Exception:
        try:
            r = len(df) if df is not None else 0
        except Exception:
            r = 0
        return {
            "name": filename,
            "dataset_name": filename,
            "row_count": r,
            "rows": r,
            "timeframe": "Unknown",
            "hash": "unknown",
            "sha256": "unknown",
            "fingerprint": f"{filename}_Unknown_{r}_unknown"
        }

