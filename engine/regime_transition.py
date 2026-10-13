"""
engine/regime_transition.py
Regime Transition Engine for NexusBot V2.

Detects transitions between market regimes (Expansion, compression, breakout loading, exhaustion, chop).
"""
import pandas as pd
import numpy as np
from engine.feature_engineering import compute_features


class RegimeTransitionEngine:
    """
    Analyzes historical features to identify regime transition states and probabilities.
    """

    def analyze(self, h1_df: pd.DataFrame) -> dict:
        """
        Calculates transition states and probabilities from the H1 feature-engineered DataFrame.

        Args:
            h1_df: H1 feature DataFrame.

        Returns:
            {
                "transition_state": "EXPANSION_BEGINNING | BREAKOUT_LOADING | TREND_EXHAUSTION | DISTRIBUTION_CHOP | COMPRESSION_REGIME | STABLE",
                "transition_probability": float (0-100),
                "expansion_phase": bool,
                "compression_phase": bool,
                "trend_exhaustion": float (0-100),
                "breakout_loading": float (0-100)
            }
        """
        if h1_df is None or h1_df.empty or len(h1_df) < 20:
            return {
                "transition_state": "STABLE",
                "transition_probability": 10.0,
                "expansion_phase": False,
                "compression_phase": False,
                "trend_exhaustion": 10.0,
                "breakout_loading": 10.0,
            }

        try:
            # Centralized compute indicator check
            df = h1_df if "ema_fast" in h1_df.columns else compute_features(h1_df)
            row = df.iloc[-1]

            atr_val = float(row.get("atr", 0.0))
            atr_mean_val = float(row.get("atr_mean", 1.0))
            atr_ratio = atr_val / max(atr_mean_val, 1e-9)

            adx_val = float(row.get("adx", 0.0))
            comp_score = float(row.get("compression_score", 1.0))
            vol_score = float(row.get("volatility_score", 50.0))

            # Lookback momentum (slope over 3 candles)
            atr_diff_3 = float(df["atr"].diff(3).iloc[-1])
            adx_diff_3 = float(df["adx"].diff(3).iloc[-1])

            # 1. Expansion beginning: ATR rising + ADX rising
            expansion_detected = atr_diff_3 > 0 and adx_diff_3 > 0

            # 2. Breakout loading: ATR low + compression high
            breakout_loading_val = clip_score((1.0 - comp_score) * 100.0)
            if atr_ratio < 0.85:
                breakout_loading_val = min(breakout_loading_val + 20.0, 100.0)
            breakout_loading_detected = comp_score < 0.75 and atr_ratio < 0.9

            # 3. Trend exhaustion: ADX collapsing
            if adx_val > 35.0:
                trend_exh_val = clip_score((adx_val - 30.0) * 3.0 + max(-adx_diff_3, 0.0) * 5.0)
            else:
                trend_exh_val = 10.0
            trend_exhaustion_detected = adx_val > 30.0 and adx_diff_3 < -2.0

            # 4. Distribution/chop: VWAP flips increasing
            price_above_vwap = df["close"] > df["vwap"]
            vwap_crossings = int(price_above_vwap.astype(int).diff().abs().tail(10).sum())
            chop_detected = vwap_crossings >= 3

            # 5. Compression regime: EMA spread narrowing
            ema_spread = (df["ema_fast"] - df["ema_slow"]).abs()
            ema_spread_narrowing = ema_spread.diff(3).iloc[-1] < 0
            compression_regime_detected = ema_spread_narrowing and comp_score < 0.85

            # Determine phase flags
            expansion_phase = bool(expansion_detected or (atr_ratio > 1.25 and adx_diff_3 > 0))
            compression_phase = bool(breakout_loading_detected or compression_regime_detected)

            # Scoring probabilities and state selection
            # Default state is STABLE
            transition_state = "STABLE"
            transition_probability = 20.0

            if expansion_detected:
                transition_state = "EXPANSION_BEGINNING"
                transition_probability = 75.0
            elif breakout_loading_detected:
                transition_state = "BREAKOUT_LOADING"
                transition_probability = 80.0
            elif trend_exhaustion_detected:
                transition_state = "TREND_EXHAUSTION"
                transition_probability = 70.0
            elif chop_detected:
                transition_state = "DISTRIBUTION_CHOP"
                transition_probability = 65.0
            elif compression_regime_detected:
                transition_state = "COMPRESSION_REGIME"
                transition_probability = 60.0

            # Normalise probability ranges
            transition_probability = float(np.clip(transition_probability, 10.0, 95.0))

            return {
                "transition_state": transition_state,
                "transition_probability": round(transition_probability, 1),
                "expansion_phase": expansion_phase,
                "compression_phase": compression_phase,
                "trend_exhaustion": round(float(np.clip(trend_exh_val, 5.0, 95.0)), 1),
                "breakout_loading": round(float(np.clip(breakout_loading_val, 5.0, 95.0)), 1),
            }

        except Exception:
            return {
                "transition_state": "STABLE",
                "transition_probability": 15.0,
                "expansion_phase": False,
                "compression_phase": False,
                "trend_exhaustion": 15.0,
                "breakout_loading": 15.0,
            }


def clip_score(val: float) -> float:
    return float(np.clip(val, 0.0, 100.0))
