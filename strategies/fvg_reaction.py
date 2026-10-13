"""
strategies/fvg_reaction.py
FVG Reaction Strategy for NexusBot V3.

Detects Fair Value Gaps (imbalances) and enters trades on reaction fills back into the gap zone.
"""
import pandas as pd
import numpy as np
from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class FVGReactionStrategy(V2BaseStrategy):
    """
    V3 Strategy: FVG Reaction.
    Triggers execution candidates when market volatility expands and creates FVG imbalances.
    """

    STRATEGY_NAME = "FVG Reaction"
    SUPPORTED_REGIMES = ["TRENDING", "VOLATILE"]
    SUPPORTED_STATES = ["TRENDING", "REVERSAL", "SESSION_VOLATILITY"]

    DEFAULT_PARAMS = {
        "sl_atr_multiplier": 1.5,
        "tp_atr_multiplier": 3.0,
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
        df = compute_features(df)
        df["bullish_fvg"] = df["low"] > df["high"].shift(2)
        df["bearish_fvg"] = df["high"] < df["low"].shift(2)
        df["fvg_size"] = np.where(
            df["bullish_fvg"],
            df["low"] - df["high"].shift(2),
            np.where(df["bearish_fvg"], df["low"].shift(2) - df["high"], 0.0)
        )
        return df

    def generate_signal(self, df: pd.DataFrame) -> dict:
        required = ["close", "atr"]
        if df is None or df.empty or not self._last_ready(df, required) or "bullish_fvg" not in df.columns:
            df = self.prepare_indicators(df) if df is not None and not df.empty else df
            if df is None or df.empty or "bullish_fvg" not in df.columns:
                return {"signal": "HOLD", "strength": 0, "reasons": []}

        atr = float(df["atr"].iloc[-1])
        bull_active = any(df["bullish_fvg"].tail(3))
        bear_active = any(df["bearish_fvg"].tail(3))
        max_fvg_size = float(df["fvg_size"].tail(3).max())

        reasons = []
        if bull_active and max_fvg_size > 0.2 * atr:
            reasons.append(f"Bullish FVG reaction (size={max_fvg_size:.2f} > 0.2*ATR)")
            return {"signal": "BUY", "strength": 80, "reasons": reasons}
        elif bear_active and max_fvg_size > 0.2 * atr:
            reasons.append(f"Bearish FVG reaction (size={max_fvg_size:.2f} > 0.2*ATR)")
            return {"signal": "SELL", "strength": 80, "reasons": reasons}

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
        expansion_phase = bool(self._get_ctx_val(ctx, "regime_transition.expansion_phase", False))

        # 1. Trend strength
        trend_strength = h4_strength

        # 2. Volatility alignment (high volatility/expansion aligns best with FVG)
        if vol_state in ["HIGH", "VOLATILE"] or expansion_phase:
            vol_align = 90.0
        elif vol_state == "NORMAL":
            vol_align = 70.0
        else:
            vol_align = 45.0

        # 3. Structure quality (imbalance quality / expansion phase)
        struct_quality = 60.0
        if expansion_phase:
            struct_quality = 85.0

        # 4. Execution readiness
        exec_readiness = readiness_score

        # 5. Timing alignment
        timing_align = m5_timing

        # Soft Penalties
        penalties = 0.0
        if vol_state == "LOW":
            penalties += 15.0
        if not expansion_phase:
            penalties += 10.0
        if readiness_score < 50.0:
            penalties += 10.0

        # Missing context checks
        uncertainty = 0.0
        if self._get_ctx_val(ctx, "h4_structure", None) is None:
            uncertainty += 5.0
        if self._get_ctx_val(ctx, "regime_transition", None) is None:
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
        Validates context for FVG Reaction eligibility.
        Hard-fails only on:
          - Severe readiness blockage (readiness_score < 20.0)
        """
        if ctx is None:
            return False

        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))

        # Hard blocks
        if readiness_score < 20.0:
            return False

        return True

    def build_execution_candidate(self, ctx) -> dict | None:
        """Builds the execution candidate if context is valid."""
        if not self.validate_context(ctx):
            return None

        h4_direction = self._get_ctx_val(ctx, "h4_structure.macro_direction", "NEUTRAL")
        direction = h4_direction if h4_direction != "NEUTRAL" else "BUY"

        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "TRENDING")

        confidence = self.score_market_fit(ctx)

        snapshot = {
            "volatility_state": str(self._get_ctx_val(ctx, "mtf_context.h1_structure.volatility_state", "NORMAL")),
            "expansion_phase": bool(self._get_ctx_val(ctx, "regime_transition.expansion_phase", False)),
        }

        risk_ctx = {
            "risk_score": float(self._get_ctx_val(ctx, "institutional_risk.risk_score", 30.0)),
        }

        candidate = {
            "strategy":            self.STRATEGY_NAME,
            "candidate_type":      "continuation",
            "direction":           direction,
            "market_state":        str(regime),
            "confidence":          round(float(confidence), 1),
            "confidence_breakdown": self.get_confidence_breakdown(ctx),
            "timeframe_bias":      direction,
            "execution_timeframe": "M5",
            "entry_style":         "fvg_imbalance_reaction",
            "reasons":             ["Fair Value Gap imbalance", "Volatility expansion fill", "Readiness confirmation"],
            "risk_context":        risk_ctx,
            "context_snapshot":    snapshot,
        }
        return candidate

    def score_market_fit(self, regime: dict) -> float:
        """Scores fit: Volatility expansion (35%), trend (25%), timing (20%), readiness (20%)."""
        if regime is None:
            return 0.0

        breakdown = self.get_confidence_breakdown(regime)
        base_score = (
            breakdown["volatility_alignment"] * 0.35 +
            breakdown["trend_strength"] * 0.25 +
            breakdown["timing_alignment"] * 0.20 +
            breakdown["execution_readiness"] * 0.20
        )

        if base_score > 40.0:
            base_score = base_score * 1.15

        final_score = base_score - breakdown["soft_penalties"] - breakdown["uncertainty_penalties"]
        return float(np.clip(final_score, 0.0, 100.0))


# V2BaseStrategy registration hook
class FVGReactionStrategyAdapter(FVGReactionStrategy):
    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return FVGReactionStrategy(params)
