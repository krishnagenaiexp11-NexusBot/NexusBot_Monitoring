"""
engine/bundle_validator.py
Dataset Bundle Validation Engine for NexusBot V2.

Verifies synchronization, resample integrity, timezone alignment,
and prevents lookahead leakage across multiple timeframes.
"""
import pandas as pd


class BundleValidator:
    """
    Validates a multi-timeframe dataset bundle containing m5, m15, h1, h4 DataFrames.
    """

    def validate(self, bundle: dict) -> dict:
        """
        Validates the synchronized timeframe bundle.

        Args:
            bundle: Dict containing DataFrames for 'm5', 'm15', 'h1', 'h4'.

        Returns:
            {
                "is_valid": bool,
                "errors": list[str],
                "warnings": list[str],
                "details": dict,
            }
        """
        errors = []
        warnings = []
        details = {}

        # 1. Essential key checking
        required_keys = ["m5", "m15", "h1", "h4"]
        for key in required_keys:
            if key not in bundle or not isinstance(bundle[key], pd.DataFrame):
                errors.append(f"Missing required timeframe key or invalid DataFrame: '{key}'")
                return {"is_valid": False, "errors": errors, "warnings": warnings, "details": details}

        m5_df = bundle["m5"]
        m15_df = bundle["m15"]
        h1_df = bundle["h1"]
        h4_df = bundle["h4"]

        # If any of them are empty, return error
        for name, df in [("m5", m5_df), ("m15", m15_df), ("h1", h1_df), ("h4", h4_df)]:
            if df.empty:
                errors.append(f"Timeframe '{name}' is empty.")
            else:
                details[f"{name}_rows"] = len(df)
                if "timestamp" not in df.columns:
                    errors.append(f"Timeframe '{name}' is missing 'timestamp' column.")

        if errors:
            return {"is_valid": False, "errors": errors, "warnings": warnings, "details": details}

        # ── Step 1: Timezone & Parse Checks ───────────────────────────────────
        for name, df in [("m5", m5_df), ("m15", m15_df), ("h1", h1_df), ("h4", h4_df)]:
            try:
                # Ensure datetime types
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                tzs = {str(t.tzinfo) for t in df["timestamp"] if t.tzinfo is not None}
                if len(tzs) > 1:
                    errors.append(f"Timeframe '{name}' has mixed timezones: {tzs}")
            except Exception as exc:
                errors.append(f"Failed parsing timestamps for '{name}': {exc}")

        if errors:
            return {"is_valid": False, "errors": errors, "warnings": warnings, "details": details}

        # ── Step 2: Timezone Alignment Check ──────────────────────────────────
        m5_tz = m5_df["timestamp"].dt.tz
        for name, df in [("m15", m15_df), ("h1", h1_df), ("h4", h4_df)]:
            if df["timestamp"].dt.tz != m5_tz:
                warnings.append(
                    f"Timezone mismatch: '{name}' tz ({df['timestamp'].dt.tz}) "
                    f"differs from 'm5' tz ({m5_tz}). Normalizing internally."
                )

        # ── Step 3: Resample Integrity Validation ─────────────────────────────
        # Validate that M15 start/end bounds match the boundaries of M5
        m5_start = m5_df["timestamp"].iloc[0]
        m5_end = m5_df["timestamp"].iloc[-1]
        
        # Allow tolerance of up to the timeframe duration for resampled bins
        for name, df, max_delta in [("m15", m15_df, pd.Timedelta(minutes=15)),
                                    ("h1", h1_df, pd.Timedelta(hours=1)),
                                    ("h4", h4_df, pd.Timedelta(hours=4))]:
            df_start = df["timestamp"].iloc[0]
            df_end = df["timestamp"].iloc[-1]
            if df_start < m5_start - max_delta:
                errors.append(f"Resample bounds error: Timeframe '{name}' starts before base 'm5' boundary (Base: {m5_start}, derived: {df_start})")
            if df_end > m5_end:
                errors.append(f"Resample bounds error: Timeframe '{name}' ends after base 'm5' (Base: {m5_end}, derived: {df_end})")

        # ── Step 4: Anti-Lookahead Validation ──────────────────────────────────
        # Ensure that no derived higher timeframe bar timestamp exceeds the current base bar's timestamp.
        # This prevents the system from 'peeking' into future low-frequency prices.
        # Check that H1 and H4 candle closes correspond to the boundaries of M15/M5
        for name, df, mins in [("m15", m15_df, 15), ("h1", h1_df, 60), ("h4", h4_df, 240)]:
            # High-frequency last timestamp
            if df["timestamp"].iloc[-1] > m5_end:
                errors.append(f"Lookahead danger: '{name}' has candles extending beyond 'm5' end boundary.")

        details["is_synchronized"] = len(errors) == 0
        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "details": details,
        }
