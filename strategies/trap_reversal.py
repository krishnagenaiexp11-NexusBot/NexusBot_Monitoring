"""
strategies/trap_reversal.py
Trap Reversal Strategy for NexusBot V3.

Captures reversals from false breakouts and structural traps in high-liquidity sweep environments.
"""
import pandas as pd
import numpy as np
from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class TrapReversalStrategy(V2BaseStrategy):
    """
    V3 Strategy: Trap Reversal.
    Exploits stop hunts, fake breakouts, and high contradiction states.
    """

    STRATEGY_NAME = "Trap Reversal"
    SUPPORTED_REGIMES = ["RANGING", "VOLATILE"]
    SUPPORTED_STATES = ["TRAP_ENVIRONMENT", "HIGH_LIQUIDITY_HUNT"]

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
        return compute_features(df)

    def generate_signal(self, df: pd.DataFrame) -> dict:
        if df is None or df.empty or not self._last_ready(df, ["close", "rsi", "volume_ratio"]):
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        row = df.iloc[-1]
        rsi_val = float(row.get("rsi", 50.0))
        vol_ratio = float(row.get("volume_ratio", 1.0))

        reasons = []
        # Trap triggers on heavy volume at range extremes
        if rsi_val >= 68.0 and vol_ratio > 1.3:
            reasons.append(f"Bearish Trap Reversal (RSI={rsi_val:.1f}, Vol Ratio={vol_ratio:.2f})")
            return {"signal": "SELL", "strength": 80, "reasons": reasons}
        elif rsi_val <= 32.0 and vol_ratio > 1.3:
            reasons.append(f"Bullish Trap Reversal (RSI={rsi_val:.1f}, Vol Ratio={vol_ratio:.2f})")
            return {"signal": "BUY", "strength": 80, "reasons": reasons}

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
        sweep_detected = bool(self._get_ctx_val(ctx, "candlestick_intelligence.liquidity_sweep", False))
        rejection_qual = float(self._get_ctx_val(ctx, "candlestick_intelligence.candle_quality", 50.0))
        vol_state = self._get_ctx_val(ctx, "volatility_state", None) or self._get_ctx_val(ctx, "mtf_context.h1_structure.volatility_state", "NORMAL")
        
        liq = self._get_ctx_val(ctx, "liquidity_state", None) or self._get_ctx_val(ctx, "session_context.session_liquidity", "MEDIUM")
        m5_timing = float(self._get_ctx_val(ctx, "m5_precision.m5_timing_score", 50.0))
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))
        
        contra_score = float(self._get_ctx_val(ctx, "contradiction_state.contradiction_score", 0.0)) or float(self._get_ctx_val(ctx, "contradiction_engine.contradiction_score", 0.0))
        h4_strength = float(self._get_ctx_val(ctx, "h4_structure.macro_strength", 50.0))

        # 1. Trend strength (inverted: weak trend = high trap reversal fit)
        trend_strength = max(100.0 - h4_strength, 0.0)

        # 2. Volatility alignment
        if vol_state in ["HIGH", "VOLATILE"]:
            vol_align = 90.0
        elif vol_state == "NORMAL":
            vol_align = 70.0
        else:
            vol_align = 40.0

        # 3. Structure quality (trap quality via contradiction + sweeps)
        struct_quality = contra_score
        if sweep_detected:
            struct_quality = min(struct_quality + 30.0, 100.0)

        # 4. Execution readiness
        exec_readiness = readiness_score

        # 5. Timing alignment
        timing_align = m5_timing
        if rejection_qual > 60.0:
            timing_align = min(timing_align + 15.0, 100.0)

        # Soft Penalties
        penalties = 0.0
        if not sweep_detected:
            penalties += 15.0
        if contra_score < 30.0:
            penalties += 10.0
        if liq == "LOW":
            penalties += 10.0
        if readiness_score < 50.0:
            penalties += 10.0

        # Missing context checks
        uncertainty = 0.0
        if self._get_ctx_val(ctx, "candlestick_intelligence", None) is None:
            uncertainty += 5.0
        if self._get_ctx_val(ctx, "contradiction_state", None) is None and self._get_ctx_val(ctx, "contradiction_engine", None) is None:
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
        Validates context for Trap Reversal eligibility.
        Hard-fails only on:
          - Severe readiness blockage (readiness_score < 20.0)
          - No sweep AND contradiction score is extremely low (contra < 10)
        """
        if ctx is None:
            return False

        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))
        sweep_detected = bool(self._get_ctx_val(ctx, "candlestick_intelligence.liquidity_sweep", False))
        contra_score = float(self._get_ctx_val(ctx, "contradiction_state.contradiction_score", 0.0)) or float(self._get_ctx_val(ctx, "contradiction_engine.contradiction_score", 0.0))

        # Hard blocks
        if readiness_score < 20.0:
            return False
        if not sweep_detected and contra_score < 10.0:
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
            "sweep_detected": bool(self._get_ctx_val(ctx, "candlestick_intelligence.liquidity_sweep", False)),
            "contradiction_score": float(self._get_ctx_val(ctx, "contradiction_state.contradiction_score", 0.0)) or float(self._get_ctx_val(ctx, "contradiction_engine.contradiction_score", 0.0)),
        }

        risk_ctx = {
            "fake_breakout_prob": float(self._get_ctx_val(ctx, "institutional_risk.fake_breakout_prob", 50.0)),
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
            "entry_style":         "trap_reversal",
            "reasons":             ["Institutional trap zone", "Sweep wick verification", "Readiness score confirmation"],
            "risk_context":        risk_ctx,
            "context_snapshot":    snapshot,
        }
        return candidate

    def score_market_fit(self, regime: dict) -> float:
        """Scores fit: volatility (30%), structure/contradiction (30%), timing (20%), readiness (20%)."""
        if regime is None:
            return 0.0

        breakdown = self.get_confidence_breakdown(regime)
        base_score = (
            breakdown["volatility_alignment"] * 0.30 +
            breakdown["structure_quality"] * 0.30 +
            breakdown["timing_alignment"] * 0.20 +
            breakdown["execution_readiness"] * 0.20
        )

        if base_score > 40.0:
            base_score = base_score * 1.15

        final_score = base_score - breakdown["soft_penalties"] - breakdown["uncertainty_penalties"]
        return float(np.clip(final_score, 0.0, 100.0))


# V2BaseStrategy registration hook
class TrapReversalStrategyAdapter(TrapReversalStrategy):
    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return TrapReversalStrategy(params)
