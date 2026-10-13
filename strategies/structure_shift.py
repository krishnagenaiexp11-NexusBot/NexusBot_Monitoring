"""
strategies/structure_shift.py
Structure Shift Strategy for NexusBot V3.

Captures directional market structure transitions and breaks of structure.
"""
import pandas as pd
import numpy as np
from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class StructureShiftStrategy(V2BaseStrategy):
    """
    V3 Strategy: Structure Shift.
    Captures directional market structure transitions.
    """

    STRATEGY_NAME = "Structure Shift"
    SUPPORTED_REGIMES = ["TRENDING", "RANGING"]
    SUPPORTED_STATES = ["REVERSAL", "TRENDING"]

    DEFAULT_PARAMS = {
        "sl_atr_multiplier": 1.8,
        "tp_atr_multiplier": 3.5,
        "persistence_ceiling": 0.65,
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

        if close > ema_fast:
            return {"signal": "BUY", "strength": 70, "reasons": ["Structural breakout shift above EMA"]}
        elif close < ema_fast:
            return {"signal": "SELL", "strength": 70, "reasons": ["Structural breakdown shift below EMA"]}
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
        h4_dir = self._get_ctx_val(ctx, "h4_structure.macro_direction", "NEUTRAL")
        macro_str = float(self._get_ctx_val(ctx, "h4_structure.macro_strength", 50.0))
        persistence = float(self._get_ctx_val(ctx, "h4_structure.trend_persistence", 0.0))
        if persistence == 0.0:
            h1 = self._get_ctx_val(ctx, "h1_structure", {}) or self._get_ctx_val(ctx, "mtf_context.h1_structure", {})
            if isinstance(h1, dict):
                persistence = float(h1.get("trend_persistence", 0.5))
            else:
                persistence = 0.5

        transition_state = self._get_ctx_val(ctx, "regime_transition.transition_state", "STABLE")
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))
        
        m15_struct = self._get_ctx_val(ctx, "mtf_context.m15_execution", {})
        m15_align = float(m15_struct.get("pullback_quality", 0.5)) * 100.0 if isinstance(m15_struct, dict) else 50.0

        # 1. Trend strength
        trend_strength = macro_str
        if h4_dir != "NEUTRAL":
            trend_strength = min(trend_strength + 20.0, 100.0)

        # 2. Volatility alignment
        vol_align = 70.0

        # 3. Structure quality (inverted persistence: lower persistence -> higher shift probability)
        struct_quality = (1.0 - persistence) * 100.0
        if transition_state in ["TREND_EXHAUSTION", "DISTRIBUTION_CHOP"]:
            struct_quality = min(struct_quality + 20.0, 100.0)

        # 4. Execution readiness
        exec_readiness = readiness_score

        # 5. Timing alignment
        timing_align = m15_align

        # Soft Penalties
        penalties = 0.0
        if persistence > self.params["persistence_ceiling"]:
            penalties += 10.0
        if readiness_score < 50.0:
            penalties += 10.0
        if transition_state not in ["TREND_EXHAUSTION", "DISTRIBUTION_CHOP"]:
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
        Validates context for Structure Shift eligibility.
        Hard-fails only on:
          - Neutral macro trend direction (h4_direction == NEUTRAL)
          - Severe execution readiness blockage (readiness_score < 20.0)
        """
        if ctx is None:
            return False

        h4_dir = self._get_ctx_val(ctx, "h4_structure.macro_direction", "NEUTRAL")
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))

        # Hard blocks
        if h4_dir == "NEUTRAL":
            return False
        if readiness_score < 20.0:
            return False

        return True

    def build_execution_candidate(self, ctx) -> dict | None:
        """Builds the execution candidate if context is valid."""
        if not self.validate_context(ctx):
            return None

        h4_dir = self._get_ctx_val(ctx, "h4_structure.macro_direction", "NEUTRAL")
        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "RANGING")

        confidence = self.score_market_fit(ctx)

        snapshot = {
            "h4_direction": h4_dir,
            "trend_persistence": float(self._get_ctx_val(ctx, "h4_structure.trend_persistence", 0.0)),
            "transition_state": self._get_ctx_val(ctx, "regime_transition.transition_state", "STABLE"),
        }

        risk_ctx = {
            "fake_breakout_prob": float(self._get_ctx_val(ctx, "institutional_risk.fake_breakout_prob", 30.0)),
            "risk_score": float(self._get_ctx_val(ctx, "institutional_risk.risk_score", 30.0)),
        }

        candidate = {
            "strategy":            self.STRATEGY_NAME,
            "candidate_type":      "structure_shift",
            "direction":           h4_dir,
            "market_state":        str(regime),
            "confidence":          round(float(confidence), 1),
            "confidence_breakdown": self.get_confidence_breakdown(ctx),
            "timeframe_bias":      h4_dir,
            "execution_timeframe": "M15",
            "entry_style":         "break_of_structure",
            "reasons":             ["Trend exhaustion breakout", "Higher timeframe structure confirmation", "Execution readiness alignment"],
            "risk_context":        risk_ctx,
            "context_snapshot":    snapshot,
        }
        return candidate

    def score_market_fit(self, regime: dict) -> float:
        """Scores fit: H4 shift strength (45%), M15 timing/alignment (35%), readiness (20%)."""
        if regime is None:
            return 0.0

        breakdown = self.get_confidence_breakdown(regime)
        base_score = (
            breakdown["trend_strength"] * 0.45 +
            breakdown["timing_alignment"] * 0.35 +
            breakdown["execution_readiness"] * 0.20
        )

        if base_score > 40.0:
            base_score = base_score * 1.15

        final_score = base_score - breakdown["soft_penalties"] - breakdown["uncertainty_penalties"]
        return float(np.clip(final_score, 0.0, 100.0))


# V2BaseStrategy registration hook
class StructureShiftStrategyAdapter(StructureShiftStrategy):
    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return StructureShiftStrategy(params)
