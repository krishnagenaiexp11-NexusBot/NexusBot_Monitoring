"""
engine/session_context.py
Session Context Engine for NexusBot V2.

Tracks session overlap (Asian, London, London/NY Overlap, NY) and measures liquidity acceleration.
"""
import pandas as pd
import numpy as np


class SessionContextEngine:
    """
    Computes session metadata, overlap states, and liquidity indicators from timestamp and volume data.
    """

    def analyze(self, df: pd.DataFrame) -> dict:
        """
        Runs session overlap intelligence on the latest candle.

        Args:
            df: Feature-engineered DataFrame (base timeframe, e.g. M5 or M15).

        Returns:
            {
                "current_session": "ASIAN | LONDON | LONDON_NY_OVERLAP | NEW_YORK",
                "is_overlap": bool,
                "session_liquidity": "HIGH | MEDIUM | LOW",
                "liquidity_acceleration": float,
                "session_volatility": float
            }
        """
        if df is None or df.empty:
            return {
                "current_session": "ASIAN",
                "is_overlap": False,
                "session_liquidity": "LOW",
                "liquidity_acceleration": 1.0,
                "session_volatility": 1.0,
            }

        try:
            row = df.iloc[-1]
            timestamp = row.get("timestamp")
            dt = pd.to_datetime(timestamp)
            hour = dt.hour

            # 1. Determine Session based on UTC/Broker hour
            # Asian/Sydney/Tokyo: 21:00 to 08:00
            # London pre-overlap: 08:00 to 13:00
            # London/NY Overlap: 13:00 to 16:00
            # New York post-overlap: 16:00 to 21:00
            if 8 <= hour < 13:
                current_session = "LONDON"
                is_overlap = False
                session_liquidity = "HIGH"
            elif 13 <= hour < 16:
                current_session = "LONDON_NY_OVERLAP"
                is_overlap = True
                session_liquidity = "HIGH"
            elif 16 <= hour < 21:
                current_session = "NEW_YORK"
                is_overlap = False
                session_liquidity = "MEDIUM"
            else:
                current_session = "ASIAN"
                is_overlap = False
                session_liquidity = "LOW"

            # 2. Liquidity acceleration: current volume relative to recent average
            # We can use the pre-computed volume_ratio from feature_engineering.py
            # If not present, calculate it on the fly
            if "volume_ratio" in row:
                liquidity_acc = float(row["volume_ratio"])
            else:
                vol = float(row.get("volume", 1.0))
                vol_mean = df["volume"].tail(20).mean()
                liquidity_acc = vol / max(vol_mean, 1e-9)

            # 3. Session Volatility: Standard deviation of returns or close price over last 12 bars
            if len(df) >= 12:
                recent_close = df["close"].tail(12)
                session_vol = float(recent_close.pct_change().std() * 100.0)
            else:
                session_vol = 1.0

            # Replace NaNs
            if np.isnan(liquidity_acc) or np.isinf(liquidity_acc):
                liquidity_acc = 1.0
            if np.isnan(session_vol) or np.isinf(session_vol):
                session_vol = 0.5

            return {
                "current_session": current_session,
                "is_overlap": is_overlap,
                "session_liquidity": session_liquidity,
                "liquidity_acceleration": round(liquidity_acc, 2),
                "session_volatility": round(session_vol, 3),
            }

        except Exception:
            return {
                "current_session": "ASIAN",
                "is_overlap": False,
                "session_liquidity": "LOW",
                "liquidity_acceleration": 1.0,
                "session_volatility": 0.5,
            }
