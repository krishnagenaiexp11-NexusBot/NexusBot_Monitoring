"""
engine/h4_structure.py
Macro Market Structure Engine for NexusBot V2.

Analyzes the H4 timeframe to determine institutional trend direction,
macro trend age, strength, and trend exhaustion probabilities.
"""
import pandas as pd
import numpy as np
from engine.feature_engineering import compute_features


class H4StructureEngine:
    """
    Computes macro structural context from H4 DataFrame.
    """

    def analyze(self, h4_df: pd.DataFrame) -> dict:
        """
        Runs macro structure analysis on H4 timeframe.

        Args:
            h4_df: H4 OHLCV DataFrame (synced).

        Returns:
            {
                "macro_direction": "BULLISH | BEARISH | NEUTRAL",
                "macro_strength": float (0-100),
                "institutional_bias": "STRONG_BULLISH | WEAK_BULLISH | STRONG_BEARISH | WEAK_BEARISH | NEUTRAL",
                "trend_age": int,
                "exhaustion_risk": float (5-95)
            }
        """
        if h4_df is None or h4_df.empty or len(h4_df) < 20:
            return {
                "macro_direction": "NEUTRAL",
                "macro_strength": 0.0,
                "institutional_bias": "NEUTRAL",
                "trend_age": 0,
                "exhaustion_risk": 15.0
            }

        try:
            feat = compute_features(h4_df)
            row = feat.iloc[-1]

            # Extract base variables
            close_val = float(row.get("close", 0.0))
            vwap_val = float(row.get("vwap", 0.0))
            ema_fast = float(row.get("ema_fast", 0.0))
            ema_slow = float(row.get("ema_slow", 0.0))
            ema_slope_val = float(row.get("ema_slope", 0.0))
            adx_val = float(row.get("adx", 0.0))
            rsi_val = float(row.get("rsi", 50.0))

            # Directional checks
            ema_bullish = ema_fast > ema_slow
            vwap_bullish = close_val > vwap_val if vwap_val > 0 else True
            slope_positive = ema_slope_val > 0

            bullish_votes = sum([ema_bullish, vwap_bullish, slope_positive])
            bearish_votes = sum([not ema_bullish, not vwap_bullish, not slope_positive])

            if bullish_votes >= 2:
                macro_direction = "BULLISH"
                institutional_bias = "STRONG_BULLISH" if ema_slope_val > 0 else "WEAK_BULLISH"
            elif bearish_votes >= 2:
                macro_direction = "BEARISH"
                institutional_bias = "STRONG_BEARISH" if ema_slope_val < 0 else "WEAK_BEARISH"
            else:
                macro_direction = "NEUTRAL"
                institutional_bias = "NEUTRAL"

            # Trend strength (ADX)
            macro_strength = float(np.clip(adx_val, 0.0, 100.0))

            # Trend Age: Consecutive candles where ema_fast is on same side of ema_slow
            is_above = feat["ema_fast"] > feat["ema_slow"]
            current_side = is_above.iloc[-1]
            consecutive = (is_above == current_side)[::-1].cumprod().sum()
            trend_age = int(consecutive)

            # Exhaustion Risk calculations
            # High age + extreme RSI or extreme ADX = high exhaustion risk
            exhaustion = 15.0
            if macro_direction == "BULLISH":
                if rsi_val > 70.0:
                    exhaustion += 40.0
                if adx_val > 45.0:
                    exhaustion += 25.0
                exhaustion += min(trend_age * 1.5, 30.0)
            elif macro_direction == "BEARISH":
                if rsi_val < 30.0:
                    exhaustion += 40.0
                if adx_val > 45.0:
                    exhaustion += 25.0
                exhaustion += min(trend_age * 1.5, 30.0)
            else:
                # Neutral ranging consolidations naturally have low exhaustion
                exhaustion = 20.0

            exhaustion_risk = float(np.clip(exhaustion, 5.0, 95.0))

            return {
                "macro_direction": macro_direction,
                "macro_strength": round(macro_strength, 1),
                "institutional_bias": institutional_bias,
                "trend_age": trend_age,
                "exhaustion_risk": round(exhaustion_risk, 1)
            }

        except Exception:
            return {
                "macro_direction": "NEUTRAL",
                "macro_strength": 0.0,
                "institutional_bias": "NEUTRAL",
                "trend_age": 0,
                "exhaustion_risk": 15.0
            }
