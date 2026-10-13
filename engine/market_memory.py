"""
engine/market_memory.py
Market State Memory Engine for NexusBot V2.

Tracks temporal persistence of regimes, volatility states, compression, and stability over time.
"""
import pandas as pd
import numpy as np
from engine.feature_engineering import compute_features


class MarketMemoryEngine:
    """
    Analyzes historical time-series data to track how long states persist and overall stability.
    """

    def analyze(self, h1_df: pd.DataFrame) -> dict:
        """
        Runs temporal persistence analysis on H1 timeframe.

        Args:
            h1_df: H1 OHLCV DataFrame.

        Returns:
            {
                "regime_duration": int (candles in current regime),
                "h1_trend_age": int (candles in current EMA alignment),
                "volatility_persistence": int (candles in current volatility state),
                "compression_persistence": int (candles in current compression state),
                "market_stability": float (0-100)
            }
        """
        if h1_df is None or h1_df.empty or len(h1_df) < 30:
            return {
                "regime_duration": 0,
                "h1_trend_age": 0,
                "volatility_persistence": 0,
                "compression_persistence": 0,
                "market_stability": 50.0,
            }

        try:
            # Ensure features are computed
            df = h1_df if "ema_fast" in h1_df.columns else compute_features(h1_df)

            # Compute historical regimes and states for all rows
            adx_series = df["adx"]
            atr_val = df["atr"]
            atr_mean_val = df["atr_mean"].replace(0, 1e-9)
            atr_ratio = atr_val / atr_mean_val

            # Regime definitions matching mtf_context
            volatile = (atr_ratio > 1.4) & (adx_series > 18.0)
            low_vol = (atr_ratio < 0.7) & (~volatile)
            trending = (adx_series >= 25.0) & (~volatile) & (~low_vol)
            ranging = (~volatile) & (~low_vol) & (~trending)

            # Build regime series
            regimes = pd.Series("RANGING", index=df.index)
            regimes[volatile] = "VOLATILE"
            regimes[low_vol] = "LOW_VOLATILITY"
            regimes[trending] = "TRENDING"
            regimes[ranging] = "RANGING"

            # 1. Regime Duration: count consecutive matching current regime at the end
            current_regime = regimes.iloc[-1]
            regime_match = regimes == current_regime
            # Cumulative product from tail to get streak duration
            regime_duration = int((regime_match)[::-1].cumprod().sum())

            # 2. H1 Trend Age: consecutive matching EMA alignment direction
            is_above = df["ema_fast"] > df["ema_slow"]
            current_side = is_above.iloc[-1]
            trend_age = int((is_above == current_side)[::-1].cumprod().sum())

            # 3. Volatility state persistence
            # Volatility state categorization
            vol_states = pd.Series("NORMAL", index=df.index)
            vol_states[atr_ratio > 1.4] = "HIGH"
            vol_states[atr_ratio < 0.7] = "LOW"

            current_vol_state = vol_states.iloc[-1]
            vol_match = vol_states == current_vol_state
            volatility_persistence = int((vol_match)[::-1].cumprod().sum())

            # 4. Compression state persistence
            # Compression is active when compression_score < 0.85
            comp_score = df["compression_score"]
            is_compressed = comp_score < 0.85
            current_comp_state = is_compressed.iloc[-1]
            comp_match = is_compressed == current_comp_state
            compression_persistence = int((comp_match)[::-1].cumprod().sum())

            # 5. Market Stability Score: based on regime switches over last 30 bars
            # Count changes in regime
            regime_switches = (regimes.shift() != regimes).tail(30).sum()
            # If 0 switches, stability = 100. Each switch penalizes stability.
            stability = max(100.0 - (regime_switches * 8.0), 10.0)

            return {
                "regime_duration": regime_duration,
                "h1_trend_age": trend_age,
                "volatility_persistence": volatility_persistence,
                "compression_persistence": compression_persistence,
                "market_stability": round(float(stability), 1),
            }

        except Exception:
            return {
                "regime_duration": 0,
                "h1_trend_age": 0,
                "volatility_persistence": 0,
                "compression_persistence": 0,
                "market_stability": 50.0,
            }
