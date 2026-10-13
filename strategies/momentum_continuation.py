"""
strategies/momentum_continuation.py
Momentum Continuation Strategy for NexusBot V3.

Captures trend continuation after healthy pullbacks in trending markets.
"""
import pandas as pd
import numpy as np
from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class MomentumContinuationStrategy(V2BaseStrategy):
    """
    V3 Strategy: Momentum Continuation.
    Captures trending conditions and returns structured execution candidates.
    """

    STRATEGY_NAME = "Momentum Continuation"
    SUPPORTED_REGIMES = ["TRENDING", "VOLATILE"]
    SUPPORTED_STATES = ["TRENDING", "SESSION_VOLATILITY", "PANIC"]

    DEFAULT_PARAMS = {
        "sl_atr_multiplier": 2.0,
        "tp_atr_multiplier": 4.0,
        "trend_persistence_threshold": 0.6,
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
        if df is None or df.empty or not self._last_ready(df, ["close", "ema_fast", "ema_slow"]):
            return {"signal": "HOLD", "strength": 0, "reasons": []}
        row = df.iloc[-1]
        close = float(row.get("close", 0.0))
        ema_fast = float(row.get("ema_fast", 0.0))
        ema_slow = float(row.get("ema_slow", 0.0))

        if ema_fast > ema_slow:
            return {"signal": "BUY", "strength": 70, "reasons": ["EMA fast above slow"]}
        elif ema_fast < ema_slow:
            return {"signal": "SELL", "strength": 70, "reasons": ["EMA fast below slow"]}
        return {"signal": "HOLD", "strength": 0, "reasons": []}

    def calculate_sl_tp(self, price: float, atr: float, direction: str):
        return self._atr_sl_tp(price, atr, direction)

    def should_exit(self, position: dict, candle: dict) -> bool:
        # Simple exit on opposite fast/slow cross
        ema_fast = float(candle.get("ema_fast", 0.0))
        ema_slow = float(candle.get("ema_slow", 0.0))
        if position["direction"] == "BUY":
            return ema_fast < ema_slow
        return ema_fast > ema_slow

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
        h4_dir = self._get_ctx_val(ctx, "h4_structure.macro_direction", "NEUTRAL")
        trend_str_val = float(self._get_ctx_val(ctx, "h4_structure.macro_strength", 50.0))
        persistence = float(self._get_ctx_val(ctx, "h4_structure.trend_persistence", 0.0))
        if persistence == 0.0:
            h1 = self._get_ctx_val(ctx, "h1_structure", {}) or self._get_ctx_val(ctx, "mtf_context.h1_structure", {})
            if isinstance(h1, dict):
                persistence = float(h1.get("trend_persistence", 0.5))
            else:
                persistence = 0.5

        vol_state = self._get_ctx_val(ctx, "volatility_state", "NORMAL")
        atr_ratio = float(self._get_ctx_val(ctx, "mtf_context.h1_structure._atr_ratio", 1.0))
        
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))
        m15_trigger = bool(self._get_ctx_val(ctx, "m15_execution.trigger_ready", False))
        if not m15_trigger:
            m15_trigger = bool(self._get_ctx_val(ctx, "mtf_context.m15_execution.trigger_ready", False))

        m5_dir = self._get_ctx_val(ctx, "m5_precision.micro_direction", "NEUTRAL")
        m5_timing = float(self._get_ctx_val(ctx, "m5_precision.m5_timing_score", 50.0))

        # 1. Trend strength
        trend_strength = trend_str_val
        if h4_dir != "NEUTRAL":
            trend_strength = min(trend_strength + 30.0, 100.0)

        # 2. Volatility alignment
        if vol_state == "NORMAL":
            vol_align = 80.0
        elif vol_state == "LOW":
            vol_align = 60.0
        else:
            vol_align = 40.0
        if 0.8 <= atr_ratio <= 1.5:
            vol_align = min(vol_align + 15.0, 100.0)

        # 3. Structure quality
        struct_quality = persistence * 100.0

        # 4. Execution readiness
        exec_readiness = readiness_score

        # 5. Timing alignment
        timing_align = m5_timing
        if m15_trigger:
            timing_align = min(timing_align + 20.0, 100.0)
        if m5_dir == h4_dir and h4_dir != "NEUTRAL":
            timing_align = min(timing_align + 15.0, 100.0)

        # Soft Penalties
        penalties = 0.0
        if persistence < 0.6:
            penalties += 30.0
        if not m15_trigger:
            penalties += 10.0
        if m5_dir != h4_dir:
            penalties += 8.0
        if readiness_score < 50.0:
            penalties += 10.0

        # Missing context checking for uncertainty penalties
        uncertainty = 0.0
        if self._get_ctx_val(ctx, "h4_structure", None) is None:
            uncertainty += 5.0
        if self._get_ctx_val(ctx, "execution_readiness", None) is None:
            uncertainty += 5.0
        if self._get_ctx_val(ctx, "m15_execution", None) is None:
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
        Validates context for Momentum Continuation eligibility.
        Hard-fails only on:
          - Neutral macro trend direction (h4_direction == NEUTRAL)
          - Severe execution readiness blockage (readiness_score < 20.0)
          - Incompatible regime (regime == RANGING)
        """
        if ctx is None:
            return False

        h4_dir = self._get_ctx_val(ctx, "h4_structure.macro_direction", "NEUTRAL")
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))

        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "TRENDING")

        # Hard blocks
        if h4_dir == "NEUTRAL":
            return False
        if readiness_score < 20.0:
            return False
        if regime == "RANGING":
            return False

        return True

    def build_execution_candidate(self, ctx) -> dict | None:
        """Builds the execution candidate if context is valid."""
        if not self.validate_context(ctx):
            return None

        h4_dir = self._get_ctx_val(ctx, "h4_structure.macro_direction", "NEUTRAL")
        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "TRENDING")

        confidence = self.score_market_fit(ctx)

        snapshot = {
            "h4_direction": h4_dir,
            "readiness_score": float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 0.0)),
            "m15_trigger_ready": bool(self._get_ctx_val(ctx, "m15_execution.trigger_ready", False)),
        }

        risk_ctx = {
            "exhaustion_risk": float(self._get_ctx_val(ctx, "h4_structure.exhaustion_risk", 50.0)),
            "risk_score": float(self._get_ctx_val(ctx, "institutional_risk.risk_score", 30.0)),
        }

        candidate = {
            "strategy":            self.STRATEGY_NAME,
            "candidate_type":      "continuation",
            "direction":           h4_dir,
            "market_state":        str(regime),
            "confidence":          round(float(confidence), 1),
            "confidence_breakdown": self.get_confidence_breakdown(ctx),
            "timeframe_bias":      h4_dir,
            "execution_timeframe": "M5",
            "entry_style":         "pullback_continuation",
            "reasons":             ["Aligned macro structure", "M15 pullback recovery", "M5 execution timing"],
            "risk_context":        risk_ctx,
            "context_snapshot":    snapshot,
        }
        return candidate

    def score_market_fit(self, regime: dict) -> float:
        """Scores fit: Trend strength (35%), structure (20%), volatility (15%), readiness (15%), timing (15%)."""
        if regime is None:
            return 0.0

        breakdown = self.get_confidence_breakdown(regime)
        base_score = (
            breakdown["trend_strength"] * 0.35 +
            breakdown["volatility_alignment"] * 0.15 +
            breakdown["structure_quality"] * 0.20 +
            breakdown["execution_readiness"] * 0.15 +
            breakdown["timing_alignment"] * 0.15
        )

        # Scale/normalize distribution to easily score 60-80 on high quality setups
        if base_score > 40.0:
            base_score = base_score * 1.15

        final_score = base_score - breakdown["soft_penalties"] - breakdown["uncertainty_penalties"]
        return float(np.clip(final_score, 0.0, 100.0))


# V2BaseStrategy registration hook
class MomentumContinuationStrategyAdapter(MomentumContinuationStrategy):
    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return MomentumContinuationStrategy(params)
