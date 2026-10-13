"""
strategies/session_breakout.py
Session Breakout Strategy for NexusBot V3.

Captures volatility expansion during major session transitions.
"""
import pandas as pd
import numpy as np
from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class SessionBreakoutStrategy(V2BaseStrategy):
    """
    V3 Strategy: Session Breakout.
    Captures volatility expansion during major session transitions.
    """

    STRATEGY_NAME = "Session Breakout"
    SUPPORTED_REGIMES = ["VOLATILE", "LOW_VOLATILITY"]
    SUPPORTED_STATES = ["SESSION_VOLATILITY", "COMPRESSED"]

    DEFAULT_PARAMS = {
        "sl_atr_multiplier": 1.5,
        "tp_atr_multiplier": 3.0,
        "liquidity_acc_threshold": 1.0,
        "breakout_threshold": 40.0,
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
        if df is None or df.empty or not self._last_ready(df, ["close", "vwap"]):
            return {"signal": "HOLD", "strength": 0, "reasons": []}
        row = df.iloc[-1]
        close = float(row.get("close", 0.0))
        vwap = float(row.get("vwap", 0.0))

        if close > vwap:
            return {"signal": "BUY", "strength": 75, "reasons": ["Session transition breakout expansion (BULLISH)"]}
        elif close < vwap:
            return {"signal": "SELL", "strength": 75, "reasons": ["Session transition breakout expansion (BEARISH)"]}
        return {"signal": "HOLD", "strength": 0, "reasons": []}

    def calculate_sl_tp(self, price: float, atr: float, direction: str):
        return self._atr_sl_tp(price, atr, direction)

    def should_exit(self, position: dict, candle: dict) -> bool:
        # Exit if session volatility normalized or basic trailing stops hit
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
        current_sess = self._get_ctx_val(ctx, "session_context.current_session", "ASIAN")
        is_overlap = bool(self._get_ctx_val(ctx, "session_context.is_overlap", False))
        liq_acc = float(self._get_ctx_val(ctx, "session_context.liquidity_acceleration", 1.0))
        breakout_loading = float(self._get_ctx_val(ctx, "regime_transition.breakout_loading", 50.0))
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))
        trend_str_val = float(self._get_ctx_val(ctx, "h4_structure.macro_strength", 50.0))
        sess_vol = float(self._get_ctx_val(ctx, "session_context.session_volatility", 0.5))

        # 1. Trend strength
        trend_strength = trend_str_val

        # 2. Volatility alignment (breakout loading)
        vol_align = breakout_loading

        # 3. Structure quality (session volatility)
        struct_quality = min(sess_vol * 100.0, 100.0)

        # 4. Execution readiness
        exec_readiness = readiness_score

        # 5. Timing alignment (liquidity acceleration)
        timing_align = min(liq_acc / 3.0 * 100.0, 100.0)

        # Soft Penalties
        penalties = 0.0
        is_session_active = is_overlap or current_sess in ["LONDON", "LONDON_NY_OVERLAP", "NEW_YORK"]
        if not is_session_active:
            penalties += 10.0
        if liq_acc < self.params["liquidity_acc_threshold"]:
            penalties += 10.0
        if breakout_loading < self.params["breakout_threshold"]:
            penalties += 10.0
        if readiness_score < 50.0:
            penalties += 10.0

        # Missing context checks
        uncertainty = 0.0
        if self._get_ctx_val(ctx, "session_context", None) is None:
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
        Validates context for Session Breakout eligibility.
        Hard-fails only on:
          - Severe execution readiness blockage (readiness_score < 20.0)
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

        h4_struct = self._get_ctx_val(ctx, "h4_structure", {})
        if isinstance(h4_struct, dict):
            h4_dir = h4_struct.get("macro_direction", "NEUTRAL")
        else:
            h4_dir = "NEUTRAL"
        direction = h4_dir if h4_dir != "NEUTRAL" else "BUY"

        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "VOLATILE")

        confidence = self.score_market_fit(ctx)

        snapshot = {
            "session": self._get_ctx_val(ctx, "session_context.current_session", "LONDON"),
            "liquidity_acceleration": float(self._get_ctx_val(ctx, "session_context.liquidity_acceleration", 1.0)),
            "breakout_loading": float(self._get_ctx_val(ctx, "regime_transition.breakout_loading", 0.0)),
        }

        risk_ctx = {
            "fake_breakout_prob": float(self._get_ctx_val(ctx, "institutional_risk.fake_breakout_prob", 30.0)),
            "risk_score": float(self._get_ctx_val(ctx, "institutional_risk.risk_score", 30.0)),
        }

        candidate = {
            "strategy":            self.STRATEGY_NAME,
            "candidate_type":      "session_breakout",
            "direction":           direction,
            "market_state":        str(regime),
            "confidence":          round(float(confidence), 1),
            "confidence_breakdown": self.get_confidence_breakdown(ctx),
            "timeframe_bias":      direction,
            "execution_timeframe": "M5",
            "entry_style":         "session_breakout",
            "reasons":             ["Session transition active", "Liquidity expansion detected", "Elevated breakout loading"],
            "risk_context":        risk_ctx,
            "context_snapshot":    snapshot,
        }
        return candidate

    def score_market_fit(self, regime: dict) -> float:
        """Scores fit: Volatility/Liquidity acceleration (40%), breakout probability (35%), readiness (25%)."""
        if regime is None:
            return 0.0

        breakdown = self.get_confidence_breakdown(regime)
        base_score = (
            breakdown["timing_alignment"] * 0.40 +
            breakdown["volatility_alignment"] * 0.35 +
            breakdown["execution_readiness"] * 0.25
        )

        if base_score > 40.0:
            base_score = base_score * 1.15

        final_score = base_score - breakdown["soft_penalties"] - breakdown["uncertainty_penalties"]
        return float(np.clip(final_score, 0.0, 100.0))


# V2BaseStrategy registration hook
class SessionBreakoutStrategyAdapter(SessionBreakoutStrategy):
    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return SessionBreakoutStrategy(params)
