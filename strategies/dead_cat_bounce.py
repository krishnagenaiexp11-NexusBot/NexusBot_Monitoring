"""
strategies/dead_cat_bounce.py
Dead Cat Bounce Strategy for NexusBot V3.

Captures rapid rebounds/reversals from panic liquidation extremes and rapid ATR expansions.
"""
import pandas as pd
import numpy as np
from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class DeadCatBounceStrategy(V2BaseStrategy):
    """
    V3 Strategy: Dead Cat Bounce.
    Triggers counter-trend scalp positions when panic capitulation exhaustions occur.
    """

    STRATEGY_NAME = "Dead Cat Bounce"
    SUPPORTED_REGIMES = ["VOLATILE", "RANGING"]
    SUPPORTED_STATES = ["PANIC", "EXHAUSTED", "ABSORPTION"]

    DEFAULT_PARAMS = {
        "sl_atr_multiplier": 1.4,
        "tp_atr_multiplier": 2.5,
        "readiness_threshold": 50.0,
        "session_filter_enabled": False,
    }

    def __init__(self, params: dict | None = None):
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}

    def get_strategy_name(self) -> str:
        return self.STRATEGY_NAME

    def get_supported_regimes(self) -> list:
        return self.SUPPORTED_REGIMES

    def get_supported_market_states(self) -> list:
        return self.SUPPORTED_STATES

    def get_default_parameters(self) -> dict:
        return dict(self.DEFAULT_PARAMS)

    def prepare_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        return compute_features(df)

    def generate_signal(self, df: pd.DataFrame) -> dict:
        if df is None or df.empty or not self._last_ready(df, ["close", "rsi", "atr", "atr_mean"]):
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        row = df.iloc[-1]
        rsi_val = float(row.get("rsi", 50.0))
        atr_ratio = float(row.get("atr", 1.0)) / max(float(row.get("atr_mean", 1.0)), 1e-9)

        reasons = []
        if rsi_val <= 20.0 and atr_ratio > 1.4:
            reasons.append(f"Bullish capitulation rebound (RSI={rsi_val:.1f}, ATR Ratio={atr_ratio:.2f})")
            return {"signal": "BUY", "strength": 85, "reasons": reasons}
        elif rsi_val >= 80.0 and atr_ratio > 1.4:
            reasons.append(f"Bearish liquidation rebound (RSI={rsi_val:.1f}, ATR Ratio={atr_ratio:.2f})")
            return {"signal": "SELL", "strength": 85, "reasons": reasons}

        return {"signal": "HOLD", "strength": 0, "reasons": []}

    def calculate_sl_tp(self, price: float, atr: float, direction: str):
        return self._atr_sl_tp(price, atr, direction)

    def should_exit(self, position: dict, candle: dict) -> bool:
        return False

    def _get_ctx_val(self, ctx, path: str, default):
        """Safely retrieves a value from a path string supporting both objects and dicts."""
        if ctx is None:
            return default
        parts = path.split('.')
        curr = ctx
        for part in parts:
            if isinstance(curr, dict):
                curr = curr.get(part)
            else:
                curr = getattr(curr, part, None)
            if curr is None:
                return default
        return curr

    def get_confidence_breakdown(self, ctx) -> dict:
        """Computes the confidence breakdown components and penalties."""
        h4_strength = float(self._get_ctx_val(ctx, "h4_structure.macro_strength", 50.0))
        vol_state = self._get_ctx_val(ctx, "volatility_state", None) or self._get_ctx_val(ctx, "mtf_context.h1_structure.volatility_state", "NORMAL")
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))
        m5_timing = float(self._get_ctx_val(ctx, "m5_precision.m5_timing_score", 50.0))
        sweep_detected = bool(self._get_ctx_val(ctx, "candlestick_intelligence.liquidity_sweep", False))
        
        atr_ratio = float(self._get_ctx_val(ctx, "mtf_context.h1_structure._atr_ratio", 1.0))
        exhaustion_risk = float(self._get_ctx_val(ctx, "h4_structure.exhaustion_risk", 50.0))

        # 1. Trend strength (exhaustion/panic level)
        trend_strength = max(h4_strength, exhaustion_risk)

        # 2. Volatility alignment (extreme ATR ratio is positive for panic rebounds)
        vol_align = min(atr_ratio * 50.0, 100.0)

        # 3. Structure quality (liquidity sweep is highly positive for reversal confirmation)
        struct_quality = 50.0
        if sweep_detected:
            struct_quality = 85.0

        # 4. Execution readiness
        exec_readiness = readiness_score

        # 5. Timing alignment
        timing_align = m5_timing

        # Soft Penalties
        penalties = 0.0
        if vol_state != "HIGH":
            penalties += 15.0
        if not sweep_detected:
            penalties += 10.0
        if readiness_score < 50.0:
            penalties += 10.0

        # Missing context checks
        uncertainty = 0.0
        if self._get_ctx_val(ctx, "h4_structure", None) is None:
            uncertainty += 5.0
        if self._get_ctx_val(ctx, "execution_readiness", None) is None:
            uncertainty += 5.0

        return {
            "trend_strength": float(np.clip(trend_strength, 0.0, 100.0)),
            "volatility_alignment": float(np.clip(vol_align, 0.0, 100.0)),
            "structure_quality": float(np.clip(struct_quality, 0.0, 100.0)),
            "execution_readiness": float(np.clip(exec_readiness, 0.0, 100.0)),
            "timing_alignment": float(np.clip(timing_align, 0.0, 100.0)),
            "soft_penalties": penalties,
            "uncertainty_penalties": uncertainty
        }

    def validate_context(self, ctx) -> bool:
        """
        Validates context for Dead Cat Bounce eligibility.
        Hard-fails only on:
          - Regime is not PANIC, EXHAUSTED, or ABSORPTION
          - Severe readiness blockage (readiness_score < 20.0)
        """
        if ctx is None:
            return False

        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "VOLATILE")

        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))

        # Hard blocks
        if regime not in ["PANIC", "EXHAUSTED", "ABSORPTION", "VOLATILE"]:
            return False
        if readiness_score < 20.0:
            return False

        return True

    def build_execution_candidate(self, ctx) -> dict | None:
        """Builds the execution candidate if context is valid."""
        if not self.validate_context(ctx):
            return None

        h1_struct = self._get_ctx_val(ctx, "h1_structure", {}) or self._get_ctx_val(ctx, "mtf_context.h1_structure", {})
        if isinstance(h1_struct, dict):
            h1_dir = h1_struct.get("structure_direction", "NEUTRAL")
        else:
            h1_dir = "NEUTRAL"
        # Counter-trend trigger
        direction = "SELL" if h1_dir == "BULLISH" else "BUY"

        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "PANIC")

        confidence = self.score_market_fit(ctx)

        snapshot = {
            "macro_regime": str(regime),
            "volatility_state": str(self._get_ctx_val(ctx, "mtf_context.h1_structure.volatility_state", "NORMAL")),
        }

        risk_ctx = {
            "risk_score": float(self._get_ctx_val(ctx, "institutional_risk.risk_score", 30.0)),
        }

        candidate = {
            "strategy":            self.STRATEGY_NAME,
            "candidate_type":      "reversal",
            "direction":           direction,
            "market_state":        str(regime),
            "confidence":          round(float(confidence), 1),
            "confidence_breakdown": self.get_confidence_breakdown(ctx),
            "timeframe_bias":      direction,
            "execution_timeframe": "M5",
            "entry_style":         "dead_cat_bounce_liquidation",
            "reasons":             ["Capitulation liquidation rebound", "Capitulation volatility extreme", "Readiness confirmed"],
            "risk_context":        risk_ctx,
            "context_snapshot":    snapshot,
        }
        return candidate

    def score_market_fit(self, regime: dict) -> float:
        """Scores fit: Volatility capitulation (40%), structure (20%), timing (20%), readiness (20%)."""
        if regime is None:
            return 0.0

        breakdown = self.get_confidence_breakdown(regime)
        base_score = (
            breakdown["volatility_alignment"] * 0.40 +
            breakdown["structure_quality"] * 0.20 +
            breakdown["timing_alignment"] * 0.20 +
            breakdown["execution_readiness"] * 0.20
        )

        if base_score > 40.0:
            base_score = base_score * 1.15

        final_score = base_score - breakdown["soft_penalties"] - breakdown["uncertainty_penalties"]
        return float(np.clip(final_score, 0.0, 100.0))


# V2BaseStrategy registration hook
class DeadCatBounceStrategyAdapter(DeadCatBounceStrategy):
    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return DeadCatBounceStrategy(params)
