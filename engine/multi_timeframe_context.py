"""
engine/multi_timeframe_context.py
Multi-Timeframe Context Engine wrapper for V2 pipeline compatibility.
"""
import pandas as pd
from engine.mtf_context import MTFContextEngine


def build_multi_timeframe_context(h1_df: pd.DataFrame, m15_df: pd.DataFrame) -> dict:
    """
    Compatibility wrapper mapping new MTFContextEngine outputs to legacy schemas.
    """
    engine = MTFContextEngine()
    new_ctx = engine.analyze(h1_df, m15_df)

    h1_struct = new_ctx["h1_structure"]
    m15_exec = new_ctx["m15_execution"]

    # Legacy mapping for test compatibility
    legacy_h1_regime = {
        "regime":               h1_struct["macro_regime"],
        "direction":            h1_struct["structure_direction"],
        "trend_strength":       h1_struct["trend_strength"],
        "volatility_score":     h1_struct["trend_strength"],  # fallback
        "breakout_probability": 0.5 if h1_struct["breakout_bias"] == "NEUTRAL" else 0.8,
        "trend_persistence":    h1_struct["trend_persistence"],
        "_adx":                 h1_struct["_adx"],
        "_atr_ratio":           h1_struct["_atr_ratio"],
        "_compression_score":   h1_struct["_compression_score"],
    }

    legacy_m15_behavior = {
        "pullback_quality":  m15_exec["pullback_quality"],
        "breakout_strength": 0.9 if m15_exec["trigger_ready"] else 0.4,
        "momentum_quality":  m15_exec["momentum_alignment"],
    }

    return {
        # New keys
        "h1_structure":    h1_struct,
        "m15_execution":   m15_exec,
        # Legacy keys for backward-compatibility
        "h1_regime":       legacy_h1_regime,
        "m15_behavior":    legacy_m15_behavior,
        "alignment_score": new_ctx["alignment_score"],
        "context_label":   new_ctx["context_label"],
    }
