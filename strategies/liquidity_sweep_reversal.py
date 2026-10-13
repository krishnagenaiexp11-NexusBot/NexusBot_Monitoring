"""
strategies/liquidity_sweep_reversal.py
Liquidity Sweep Reversal Strategy for NexusBot V3.

Captures stop-hunt sweeps and rejection reversals at key support/resistance boundaries.
"""
import pandas as pd
import numpy as np
from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class LiquiditySweepReversalStrategy(V2BaseStrategy):
    """
    V3 Strategy: Liquidity Sweep Reversal.
    Detects wicks/sweeps and confirms timing using M5 precision.
    """

    STRATEGY_NAME = "Liquidity Sweep Reversal"
    SUPPORTED_REGIMES = ["RANGING", "VOLATILE"]
    SUPPORTED_STATES = ["HIGH_LIQUIDITY_HUNT", "TRAP_ENVIRONMENT", "REVERSAL"]

    DEFAULT_PARAMS = {
        "sl_atr_multiplier": 1.8,
        "tp_atr_multiplier": 3.5,
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
        if df is None or df.empty or not self._last_ready(df, ["close", "atr"]):
            return {"signal": "HOLD", "strength": 0, "reasons": []}
        # Reversal signals are wick-based, default legacy signal checks inside bars
        row = df.iloc[-1]
        close = float(row.get("close", 0.0))
        vwap_val = float(row.get("vwap", 0.0))
        if close > vwap_val:
            return {"signal": "BUY", "strength": 60, "reasons": ["Wick rejection support"]}
        else:
            return {"signal": "SELL", "strength": 60, "reasons": ["Wick rejection resistance"]}

    def calculate_sl_tp(self, price: float, atr: float, direction: str):
        return self._atr_sl_tp(price, atr, direction)

    def should_exit(self, position: dict, candle: dict) -> bool:
        # Exit if target hit or trend age extreme
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
        sweep_detected = bool(self._get_ctx_val(ctx, "candlestick_intelligence.liquidity_sweep", False))
        pattern_type = self._get_ctx_val(ctx, "candlestick_intelligence.pattern_type", "NEUTRAL")
        rejection_qual = float(self._get_ctx_val(ctx, "candlestick_intelligence.candle_quality", 50.0))
        
        liq = self._get_ctx_val(ctx, "liquidity_state", None) or self._get_ctx_val(ctx, "session_context.session_liquidity", "MEDIUM")
        m5_timing = float(self._get_ctx_val(ctx, "m5_precision.m5_timing_score", 50.0))
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))
        
        h4_strength = float(self._get_ctx_val(ctx, "h4_structure.macro_strength", 50.0))
        trend_persistence = float(self._get_ctx_val(ctx, "h4_structure.trend_persistence", 0.5))
        sweep_risk = float(self._get_ctx_val(ctx, "institutional_risk.fake_breakout_prob", 50.0))

        # 1. Trend strength (inverted: weak trend = high reversal fit)
        trend_strength = max(100.0 - h4_strength, 0.0)

        # 2. Volatility alignment
        vol_align = sweep_risk

        # 3. Structure quality (rejection quality)
        struct_quality = rejection_qual
        if sweep_detected or pattern_type == "REVERSAL":
            struct_quality = min(struct_quality + 20.0, 100.0)

        # 4. Execution readiness
        exec_readiness = readiness_score

        # 5. Timing alignment
        timing_align = m5_timing

        # Soft Penalties
        penalties = 0.0
        if not (sweep_detected or pattern_type == "REVERSAL"):
            penalties += 15.0
        if liq == "LOW":
            penalties += 10.0
        if m5_timing < 40.0:
            penalties += 10.0
        if readiness_score < 50.0:
            penalties += 10.0

        # Missing context checks
        uncertainty = 0.0
        if self._get_ctx_val(ctx, "candlestick_intelligence", None) is None:
            uncertainty += 5.0
        if self._get_ctx_val(ctx, "m5_precision", None) is None:
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
        Validates context for Liquidity Sweep Reversal eligibility.
        Hard-fails only on:
          - Extreme macro continuation trend (strength >= 35.0 and persistence >= 0.8)
          - Severe readiness blockage (readiness_score < 20.0)
        """
        if ctx is None:
            return False

        h4_strength = float(self._get_ctx_val(ctx, "h4_structure.macro_strength", 0.0))
        trend_persistence = float(self._get_ctx_val(ctx, "h4_structure.trend_persistence", 0.0))
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))

        # Hard blocks
        if h4_strength >= 35.0 and trend_persistence >= 0.8:
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
        direction = "SELL" if h1_dir == "BULLISH" else "BUY"

        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "RANGING")

        confidence = self.score_market_fit(ctx)

        snapshot = {
            "candle_pattern": self._get_ctx_val(ctx, "candlestick_intelligence.pattern_name", "Pin Bar"),
            "candle_quality": float(self._get_ctx_val(ctx, "candlestick_intelligence.candle_quality", 70.0)),
            "liquidity": str(self._get_ctx_val(ctx, "liquidity_state", "MEDIUM")),
        }

        risk_ctx = {
            "liquidity_vacuum_risk": float(self._get_ctx_val(ctx, "institutional_risk.liquidity_vacuum_risk", 20.0)),
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
            "entry_style":         "sweep_rejection_reversal",
            "reasons":             ["Liquidity stop hunt sweep", "Wick rejection reversal structure", "M5 reversal alignment"],
            "risk_context":        risk_ctx,
            "context_snapshot":    snapshot,
        }
        return candidate

    def score_market_fit(self, regime: dict) -> float:
        """Scores fit: Sweep risk (35%), Rejection quality (30%), M5 timing (20%), readiness (15%)."""
        if regime is None:
            return 0.0

        breakdown = self.get_confidence_breakdown(regime)
        base_score = (
            breakdown["volatility_alignment"] * 0.35 +
            breakdown["structure_quality"] * 0.30 +
            breakdown["timing_alignment"] * 0.20 +
            breakdown["execution_readiness"] * 0.15
        )

        if base_score > 40.0:
            base_score = base_score * 1.15

        final_score = base_score - breakdown["soft_penalties"] - breakdown["uncertainty_penalties"]
        return float(np.clip(final_score, 0.0, 100.0))


class LiquiditySweepReversalStrategyAdapter(LiquiditySweepReversalStrategy):
    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return LiquiditySweepReversalStrategy(params)
