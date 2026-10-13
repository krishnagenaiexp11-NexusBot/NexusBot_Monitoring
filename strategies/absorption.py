"""
strategies/absorption.py
Absorption Strategy for NexusBot V3.

Detects institutional absorption zones where heavy volume is processed without resulting in price expansion.
"""
import pandas as pd
import numpy as np
from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class AbsorptionStrategy(V2BaseStrategy):
    """
    V3 Strategy: Absorption.
    Triggers positions when high volume ratio overlaps with volatility compression and VWAP.
    """

    STRATEGY_NAME = "Absorption"
    SUPPORTED_REGIMES = ["RANGING", "TRENDING"]
    SUPPORTED_STATES = ["ABSORPTION", "REVERSAL", "HIGH_LIQUIDITY_HUNT"]

    DEFAULT_PARAMS = {
        "sl_atr_multiplier": 1.6,
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
        return compute_features(df)

    def generate_signal(self, df: pd.DataFrame) -> dict:
        if df is None or df.empty or not self._last_ready(df, ["close", "vwap", "volume_ratio", "compression_score"]):
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        row = df.iloc[-1]
        vol_ratio = float(row.get("volume_ratio", 1.0))
        comp_score = float(row.get("compression_score", 1.0))
        close = float(row.get("close", 0.0))
        vwap = float(row.get("vwap", 0.0))

        reasons = []
        if vol_ratio > 1.3 and comp_score < 0.8:
            direction = "BUY" if close > vwap else "SELL"
            reasons.append(f"Institutional absorption (vol_ratio={vol_ratio:.2f}, comp_score={comp_score:.2f}, side={direction})")
            return {"signal": direction, "strength": 75, "reasons": reasons}

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
        vol_state = self._get_ctx_val(ctx, "volatility_state", None) or self._get_ctx_val(ctx, "mtf_context.h1_structure.volatility_state", "NORMAL")
        liq = self._get_ctx_val(ctx, "liquidity_state", None) or self._get_ctx_val(ctx, "session_context.session_liquidity", "MEDIUM")
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))
        m5_timing = float(self._get_ctx_val(ctx, "m5_precision.m5_timing_score", 50.0))

        comp_score = float(self._get_ctx_val(ctx, "mtf_context.h1_structure._compression_score", 0.8))
        liq_acc = float(self._get_ctx_val(ctx, "session_context.liquidity_acceleration", 1.0))
        h4_strength = float(self._get_ctx_val(ctx, "h4_structure.macro_strength", 50.0))

        # 1. Trend strength
        trend_strength = h4_strength

        # 2. Volatility alignment (compressed volatility is positive for absorption)
        vol_align = (1.0 - min(comp_score, 1.0)) * 100.0

        # 3. Structure quality (liquidity acceleration / volume imbalance)
        struct_quality = min(liq_acc * 50.0, 100.0)

        # 4. Execution readiness
        exec_readiness = readiness_score

        # 5. Timing alignment
        timing_align = m5_timing

        # Soft Penalties
        penalties = 0.0
        if liq_acc < 1.1:
            penalties += 15.0
        if vol_state == "HIGH":
            penalties += 10.0
        if readiness_score < 50.0:
            penalties += 10.0

        # Missing context checks
        uncertainty = 0.0
        if self._get_ctx_val(ctx, "session_context", None) is None:
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
        Validates context for Absorption eligibility.
        Hard-fails only on:
          - Regime is TRENDING with extremely high persistence (trend_persistence >= 0.8)
          - Severe readiness blockage (readiness_score < 20.0)
        """
        if ctx is None:
            return False

        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "RANGING")

        trend_persistence = float(self._get_ctx_val(ctx, "h4_structure.trend_persistence", 0.0))
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))

        # Hard blocks
        if regime == "TRENDING" and trend_persistence >= 0.8:
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
        direction = "BUY" if h1_dir == "BULLISH" else "SELL"

        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "RANGING")

        confidence = self.score_market_fit(ctx)

        snapshot = {
            "macro_regime": str(regime),
            "compression_score": float(self._get_ctx_val(ctx, "mtf_context.h1_structure._compression_score", 0.8)),
            "liquidity_acceleration": float(self._get_ctx_val(ctx, "session_context.liquidity_acceleration", 1.0)),
        }

        risk_ctx = {
            "risk_score": float(self._get_ctx_val(ctx, "institutional_risk.risk_score", 30.0)),
        }

        candidate = {
            "strategy":            self.STRATEGY_NAME,
            "candidate_type":      "absorption",
            "direction":           direction,
            "market_state":        str(regime),
            "confidence":          round(float(confidence), 1),
            "confidence_breakdown": self.get_confidence_breakdown(ctx),
            "timeframe_bias":      direction,
            "execution_timeframe": "M5",
            "entry_style":         "institutional_absorption",
            "reasons":             ["Institutional volume block", "Volatility compression absorption", "Readiness confirmed"],
            "risk_context":        risk_ctx,
            "context_snapshot":    snapshot,
        }
        return candidate

    def score_market_fit(self, regime: dict) -> float:
        """Scores fit: compression/volatility (35%), volume/liquidity (30%), timing (15%), readiness (20%)."""
        if regime is None:
            return 0.0

        breakdown = self.get_confidence_breakdown(regime)
        base_score = (
            breakdown["volatility_alignment"] * 0.35 +
            breakdown["structure_quality"] * 0.30 +
            breakdown["timing_alignment"] * 0.15 +
            breakdown["execution_readiness"] * 0.20
        )

        if base_score > 40.0:
            base_score = base_score * 1.15

        final_score = base_score - breakdown["soft_penalties"] - breakdown["uncertainty_penalties"]
        return float(np.clip(final_score, 0.0, 100.0))


# V2BaseStrategy registration hook
class AbsorptionStrategyAdapter(AbsorptionStrategy):
    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return AbsorptionStrategy(params)
