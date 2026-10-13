"""
engine/execution_clock.py
Closed-Candle Execution Clock for NexusBot V3.

Determines whether the current candle is "closed" (safe for entry),
how many minutes remain until the next candle, and whether we are in
a premium execution window. No threading, no websockets — deterministic.
"""
import numpy as np
import pandas as pd


class ExecutionClock:
    """
    Computes time-based execution readiness from the last candle timestamp.

    Assumptions:
      - Candle intervals are inferred from the dataset (M5, M15, H1, H4).
      - Analysis is always performed on the most recently CLOSED candle.
      - No live market data connections are made.
    """

    # Session premium windows (UTC hours)
    PREMIUM_WINDOWS = [
        (8, 10),    # London open
        (13, 15),   # London/NY overlap
        (7, 8),     # Pre-London institutional positioning
    ]

    def analyze(self, df: pd.DataFrame, timeframe_minutes: int = 5) -> dict:
        """
        Computes closed-candle state and timing quality.

        Args:
            df                : OHLCV DataFrame with 'timestamp' column.
            timeframe_minutes : Candle interval in minutes (5, 15, 60, 240).

        Returns:
            {
                "candle_closed"        : bool  (always True for historical data),
                "candle_age_minutes"   : float (minutes since last candle close),
                "minutes_to_next"      : float (minutes until next theoretical candle),
                "is_premium_window"    : bool  (within high-quality session window),
                "current_utc_hour"     : int,
                "execution_timing"     : "OPTIMAL | ACCEPTABLE | SUBOPTIMAL",
                "timing_score"         : float (0-100)
            }
        """
        if df is None or df.empty:
            return self._empty()

        try:
            row = df.iloc[-1]
            timestamp = row.get("timestamp")
            if timestamp is None:
                return self._empty()

            dt = pd.to_datetime(timestamp)
            current_utc_hour = int(dt.hour)

            # Candle age and next candle timing
            # In historical analysis, the candle is always closed
            candle_closed = True
            # Age = how many minutes since the candle opened (always = timeframe_minutes for closed)
            candle_age_minutes = float(timeframe_minutes)
            minutes_to_next = 0.0   # Next candle is the one after — we're analyzing historical

            # Premium window check
            is_premium_window = any(
                start <= current_utc_hour < end
                for start, end in self.PREMIUM_WINDOWS
            )

            # Execution timing classification
            if is_premium_window:
                execution_timing = "OPTIMAL"
                timing_score = 85.0 + (5.0 if current_utc_hour in [9, 14] else 0.0)
            elif 7 <= current_utc_hour < 21:
                execution_timing = "ACCEPTABLE"
                timing_score = 60.0
            else:
                execution_timing = "SUBOPTIMAL"
                timing_score = 30.0

            timing_score = float(np.clip(timing_score, 0.0, 100.0))

            return {
                "candle_closed": candle_closed,
                "candle_age_minutes": candle_age_minutes,
                "minutes_to_next": minutes_to_next,
                "is_premium_window": is_premium_window,
                "current_utc_hour": current_utc_hour,
                "execution_timing": execution_timing,
                "timing_score": round(timing_score, 1),
            }

        except Exception:
            return self._empty()

    def _empty(self) -> dict:
        return {
            "candle_closed": True,
            "candle_age_minutes": 5.0,
            "minutes_to_next": 0.0,
            "is_premium_window": False,
            "current_utc_hour": 0,
            "execution_timing": "SUBOPTIMAL",
            "timing_score": 0.0,
        }
