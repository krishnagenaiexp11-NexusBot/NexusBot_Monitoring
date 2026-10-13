"""
engine/multi_timeframe_pipeline.py
Multi-Timeframe Data Pipeline for NexusBot V2.

Automatically resamples high-frequency datasets (typically M5)
into synchronized lower-frequency datasets (M15, H1, H4).
"""
import pandas as pd
from utils.timeframes import detect_timeframe
from utils.validation import validate_ohlcv


class MultiTimeframePipeline:
    """
    Takes a validated base OHLCV DataFrame and generates resampled timeframes.
    Output: {"m5": df, "m15": df, "h1": df, "h4": df}
    """

    def process(self, df: pd.DataFrame) -> dict:
        """
        Validates, cleans, and resamples the input dataframe.

        Args:
            df: Raw or partially cleaned base DataFrame.

        Returns:
            Dict containing DataFrames for m5, m15, h1, h4 timeframes.
        """
        # Validate base timeframe to canonical form
        df_clean = validate_ohlcv(df)
        base_tf = detect_timeframe(df_clean)

        # Initialize outputs
        m5_df = pd.DataFrame()
        m15_df = pd.DataFrame()
        h1_df = pd.DataFrame()
        h4_df = pd.DataFrame()

        if base_tf == "M5":
            m5_df = df_clean.copy()
            m15_df = self._resample(df_clean, "15min")
            h1_df = self._resample(df_clean, "1h")
            h4_df = self._resample(df_clean, "4h")
        elif base_tf == "M15":
            m5_df = df_clean.copy()  # Fallback: copy base
            m15_df = df_clean.copy()
            h1_df = self._resample(df_clean, "1h")
            h4_df = self._resample(df_clean, "4h")
        elif base_tf == "H1":
            m5_df = df_clean.copy()
            m15_df = df_clean.copy()
            h1_df = df_clean.copy()
            h4_df = self._resample(df_clean, "4h")
        else:
            # Fallback if base timeframe is H4 or larger
            m5_df = df_clean.copy()
            m15_df = df_clean.copy()
            h1_df = df_clean.copy()
            h4_df = df_clean.copy()

        return {
            "m5": m5_df,
            "m15": m15_df,
            "h1": h1_df,
            "h4": h4_df,
            "base_timeframe": base_tf,
        }

    def _resample(self, df: pd.DataFrame, rule: str) -> pd.DataFrame:
        """Helper to resample OHLCV columns using pandas resample."""
        try:
            temp = df.copy()
            temp["timestamp"] = pd.to_datetime(temp["timestamp"])
            temp = temp.sort_values("timestamp").set_index("timestamp")
            
            resampled = temp.resample(rule).agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
            ).dropna().reset_index()
            
            return resampled
        except Exception:
            return df.copy()
