"""
strategies/compression_breakout.py
Compression Breakout Strategy for NexusBot V3.

Captures volatility expansion and breakouts after low-volatility compression.
"""
import pandas as pd
import numpy as np
from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class CompressionBreakoutStrategy(V2BaseStrategy):
    """
    V3 Strategy: Compression Breakout.
    Detects market compression and triggers breakouts when volume/liquidity active.
    """

    STRATEGY_NAME = "Compression Breakout"
    SUPPORTED_REGIMES = ["LOW_VOLATILITY", "VOLATILE"]
    SUPPORTED_STATES = ["COMPRESSED", "SESSION_VOLATILITY"]

    DEFAULT_PARAMS = {
        "sl_atr_multiplier": 1.5,
        "tp_atr_multiplier": 3.0,
        "compression_threshold": 0.8,
        "breakout_threshold": 50.0,
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
        if df is None or df.empty or not self._last_ready(df, ["close", "compression_score", "volatility_score"]):
            return {"signal": "HOLD", "strength": 0, "reasons": []}
        row = df.iloc[-1]
        comp = float(row.get("compression_score", 1.0))
        vol = float(row.get("volatility_score", 0.0))

        if comp < self.params["compression_threshold"] and vol > self.params["breakout_threshold"]:
            direction = "BUY" if float(row.get("close", 0.0)) > float(row.get("vwap", 0.0)) else "SELL"
            return {"signal": direction, "strength": 80, "reasons": ["Compression breakout active"]}
        return {"signal": "HOLD", "strength": 0, "reasons": []}

    def calculate_sl_tp(self, price: float, atr: float, direction: str):
        return self._atr_sl_tp(price, atr, direction)

    def should_exit(self, position: dict, candle: dict) -> bool:
        # Exit if volatility dies or score is flat
        comp = float(candle.get("compression_score", 1.0))
        return comp > 0.85

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
        vol_state = self._get_ctx_val(ctx, "volatility_state", "NORMAL")
        comp_score = float(self._get_ctx_val(ctx, "mtf_context.h1_structure._compression_score", 0.8))
        breakout_loading = float(self._get_ctx_val(ctx, "regime_transition.breakout_loading", 50.0))
        session_liq = self._get_ctx_val(ctx, "session_context.session_liquidity", "MEDIUM")
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))
        trend_str_val = float(self._get_ctx_val(ctx, "h4_structure.macro_strength", 50.0))

        # 1. Trend strength
        trend_strength = trend_str_val

        # 2. Volatility alignment
        vol_align = (1.0 - min(comp_score, 1.0)) * 100.0
        if vol_state == "LOW":
            vol_align = min(vol_align + 20.0, 100.0)

        # 3. Structure quality (breakout loading)
        struct_quality = breakout_loading

        # 4. Execution readiness
        exec_readiness = readiness_score

        # 5. Timing alignment
        if session_liq == "HIGH":
            timing_align = 90.0
        elif session_liq == "MEDIUM":
            timing_align = 70.0
        else:
            timing_align = 40.0

        # Soft Penalties
        penalties = 0.0
        if comp_score >= self.params["compression_threshold"]:
            penalties += 10.0
        if breakout_loading < self.params["breakout_threshold"]:
            penalties += 10.0
        if session_liq == "LOW":
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
        Validates context for Compression Breakout eligibility.
        Hard-fails only on:
          - Volatility state already HIGH (volatility_state == HIGH)
          - Severe readiness blockage (readiness_score < 20.0)
          - Excessive contradictions (contra_score >= 50.0)
        """
        if ctx is None:
            return False

        vol_state = self._get_ctx_val(ctx, "volatility_state", "NORMAL")
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))
        contra_score = float(self._get_ctx_val(ctx, "contradiction_state.contradiction_score", 0.0))
        if contra_score == 0.0:
            contra_score = float(self._get_ctx_val(ctx, "contradiction_engine.contradiction_score", 0.0))

        # Hard blocks
        if vol_state == "HIGH":
            return False
        if readiness_score < 20.0:
            return False
        if contra_score >= 50.0:
            return False

        return True

    def build_execution_candidate(self, ctx) -> dict | None:
        """Builds the execution candidate if context is valid."""
        if not self.validate_context(ctx):
            return None

        h1_struct = self._get_ctx_val(ctx, "h1_structure", {}) or self._get_ctx_val(ctx, "mtf_context.h1_structure", {})
        if isinstance(h1_struct, dict):
            breakout_bias = h1_struct.get("breakout_bias", "BULLISH")
        else:
            breakout_bias = "BULLISH"
        direction = "BUY" if breakout_bias == "BULLISH" else "SELL"

        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "LOW_VOLATILITY")

        confidence = self.score_market_fit(ctx)

        snapshot = {
            "compression_score": float(self._get_ctx_val(ctx, "mtf_context.h1_structure._compression_score", 0.8)),
            "breakout_bias": breakout_bias,
            "session": self._get_ctx_val(ctx, "session_context.current_session", "LONDON"),
        }

        risk_ctx = {
            "fake_breakout_prob": float(self._get_ctx_val(ctx, "institutional_risk.fake_breakout_prob", 30.0)),
            "risk_score": float(self._get_ctx_val(ctx, "institutional_risk.risk_score", 30.0)),
        }

        candidate = {
            "strategy":            self.STRATEGY_NAME,
            "candidate_type":      "breakout",
            "direction":           direction,
            "market_state":        str(regime),
            "confidence":          round(float(confidence), 1),
            "confidence_breakdown": self.get_confidence_breakdown(ctx),
            "timeframe_bias":      direction,
            "execution_timeframe": "M15",
            "entry_style":         "compression_expansion",
            "reasons":             ["Volatility compression squeeze", "Breakout probability elevated", "Active session hours"],
            "risk_context":        risk_ctx,
            "context_snapshot":    snapshot,
        }
        return candidate

    def score_market_fit(self, regime: dict) -> float:
        """Scores fit: Volatility alignment (40%), breakout probability (30%), readiness (15%), timing (15%)."""
        if regime is None:
            return 0.0

        breakdown = self.get_confidence_breakdown(regime)
        base_score = (
            breakdown["volatility_alignment"] * 0.40 +
            breakdown["structure_quality"] * 0.30 +
            breakdown["execution_readiness"] * 0.15 +
            breakdown["timing_alignment"] * 0.15
        )

        if base_score > 40.0:
            base_score = base_score * 1.15

        final_score = base_score - breakdown["soft_penalties"] - breakdown["uncertainty_penalties"]
        return float(np.clip(final_score, 0.0, 100.0))


# V2BaseStrategy registration hook
class CompressionBreakoutStrategyAdapter(CompressionBreakoutStrategy):
    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return CompressionBreakoutStrategy(params)
