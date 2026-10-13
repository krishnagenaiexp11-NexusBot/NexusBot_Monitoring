"""
strategies/exhaustion_reversal.py
Exhaustion Reversal Strategy for NexusBot V3.

Captures counter-trend reversals when a strong trend shows signs of momentum exhaustion.
"""
import pandas as pd
import numpy as np
from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class ExhaustionReversalStrategy(V2BaseStrategy):
    """
    V3 Strategy: Exhaustion Reversal.
    Triggers counter-trend entries when trend persistence decays and wicks/rejections print.
    """

    STRATEGY_NAME = "Exhaustion Reversal"
    SUPPORTED_REGIMES = ["TRENDING", "VOLATILE"]
    SUPPORTED_STATES = ["EXHAUSTED", "REVERSAL", "ABSORPTION"]

    DEFAULT_PARAMS = {
        "sl_atr_multiplier": 1.6,
        "tp_atr_multiplier": 3.0,
        "readiness_threshold": 50.0,
        "adx_exhaustion_threshold": 30.0,
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
        if df is None or df.empty or not self._last_ready(df, ["close", "rsi", "adx", "ema_slowing"]):
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        row = df.iloc[-1]
        rsi_val = float(row.get("rsi", 50.0))
        adx_val = float(row.get("adx", 0.0))
        ema_slowing = bool(row.get("ema_slowing", False))

        reasons = []
        if adx_val > self.params["adx_exhaustion_threshold"] and rsi_val >= 70.0 and ema_slowing:
            reasons.append(f"Exhausted Uptrend (RSI={rsi_val:.1f}, ADX={adx_val:.1f})")
            return {"signal": "SELL", "strength": 75, "reasons": reasons}
        elif adx_val > self.params["adx_exhaustion_threshold"] and rsi_val <= 30.0 and ema_slowing:
            reasons.append(f"Exhausted Downtrend (RSI={rsi_val:.1f}, ADX={adx_val:.1f})")
            return {"signal": "BUY", "strength": 75, "reasons": reasons}

        return {"signal": "HOLD", "strength": 0, "reasons": []}

    def calculate_sl_tp(self, price: float, atr: float, direction: str):
        return self._atr_sl_tp(price, atr, direction)

    def should_exit(self, position: dict, candle: dict) -> bool:
        # Exit on standard ATR targets or trailing stops
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
        h4_direction = self._get_ctx_val(ctx, "h4_structure.macro_direction", "NEUTRAL")
        trend_persistence = float(self._get_ctx_val(ctx, "h4_structure.trend_persistence", 0.5))

        vol_state = self._get_ctx_val(ctx, "volatility_state", None) or self._get_ctx_val(ctx, "mtf_context.h1_structure.volatility_state", "NORMAL")
        rejection_qual = float(self._get_ctx_val(ctx, "candlestick_intelligence.candle_quality", 50.0))
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))
        m5_timing = float(self._get_ctx_val(ctx, "m5_precision.m5_timing_score", 50.0))

        exhaustion_risk = float(self._get_ctx_val(ctx, "h4_structure.exhaustion_risk", 50.0))

        # 1. Trend strength (ADX / exhaustion risk)
        trend_strength = max(h4_strength, exhaustion_risk)

        # 2. Volatility alignment
        if vol_state in ["HIGH", "VOLATILE"]:
            vol_align = 90.0
        elif vol_state == "NORMAL":
            vol_align = 70.0
        else:
            vol_align = 40.0

        # 3. Structure quality (inverted persistence: lower trend persistence = higher reversal structure quality)
        struct_quality = (1.0 - trend_persistence) * 100.0

        # 4. Execution readiness
        exec_readiness = readiness_score

        # 5. Timing alignment
        timing_align = m5_timing
        if rejection_qual > 70.0:
            timing_align = min(timing_align + 15.0, 100.0)

        # Soft Penalties
        penalties = 0.0
        if trend_persistence >= 0.75:
            penalties += 15.0
        if rejection_qual < 60.0:
            penalties += 10.0
        if h4_direction == "NEUTRAL":
            penalties += 10.0
        if readiness_score < 50.0:
            penalties += 10.0

        # Missing context checks
        uncertainty = 0.0
        if self._get_ctx_val(ctx, "h4_structure", None) is None:
            uncertainty += 5.0
        if self._get_ctx_val(ctx, "candlestick_intelligence", None) is None:
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
        Validates context for Exhaustion Reversal eligibility.
        Hard-fails only on:
          - Extremely strong macro trend persistence (trend_persistence >= 0.85)
          - Severe readiness blockage (readiness_score < 20.0)
        """
        if ctx is None:
            return False

        trend_persistence = float(self._get_ctx_val(ctx, "h4_structure.trend_persistence", 0.0))
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))

        # Hard blocks
        if trend_persistence >= 0.85:
            return False
        if readiness_score < 20.0:
            return False

        return True

    def build_execution_candidate(self, ctx) -> dict | None:
        """Builds the execution candidate if context is valid."""
        if not self.validate_context(ctx):
            return None

        h4_direction = self._get_ctx_val(ctx, "h4_structure.macro_direction", "NEUTRAL")
        direction = "SELL" if h4_direction == "BULLISH" else ("BUY" if h4_direction == "BEARISH" else "BUY")

        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "TRENDING")

        confidence = self.score_market_fit(ctx)

        snapshot = {
            "h4_direction": h4_direction,
            "trend_persistence": float(self._get_ctx_val(ctx, "h4_structure.trend_persistence", 0.0)),
            "exhaustion_risk": float(self._get_ctx_val(ctx, "h4_structure.exhaustion_risk", 0.0)),
        }

        risk_ctx = {
            "exhaustion_risk": float(self._get_ctx_val(ctx, "h4_structure.exhaustion_risk", 50.0)),
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
            "entry_style":         "exhaustion_reversal",
            "reasons":             ["Trend exhaustion detected", "Decaying trend persistence", "Execution readiness alignment"],
            "risk_context":        risk_ctx,
            "context_snapshot":    snapshot,
        }
        return candidate

    def score_market_fit(self, regime: dict) -> float:
        """Scores fit: trend strength (35%), structure (20%), volatility (15%), readiness (15%), timing (15%)."""
        if regime is None:
            return 0.0

        breakdown = self.get_confidence_breakdown(regime)
        base_score = (
            breakdown["trend_strength"] * 0.35 +
            breakdown["structure_quality"] * 0.20 +
            breakdown["volatility_alignment"] * 0.15 +
            breakdown["execution_readiness"] * 0.15 +
            breakdown["timing_alignment"] * 0.15
        )

        if base_score > 40.0:
            base_score = base_score * 1.15

        final_score = base_score - breakdown["soft_penalties"] - breakdown["uncertainty_penalties"]
        return float(np.clip(final_score, 0.0, 100.0))


# V2BaseStrategy registration hook
class ExhaustionReversalStrategyAdapter(ExhaustionReversalStrategy):
    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return ExhaustionReversalStrategy(params)
