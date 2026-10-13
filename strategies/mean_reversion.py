"""
strategies/mean_reversion.py
Mean Reversion Strategy — NexusBot V3.

Best for: RANGING markets, weak ADX, low volatility.
Logic   : RSI exhaustion at VWAP deviation extremes.
          Enter counter-trend when price is over-extended from VWAP and
          RSI reaches overbought/oversold.
Regimes : RANGING
"""
import pandas as pd
import numpy as np

from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class MeanReversionStrategy(V2BaseStrategy):

    STRATEGY_NAME     = "Mean Reversion"
    SUPPORTED_REGIMES = ["RANGING"]
    SUPPORTED_STATES  = ["RANGING", "COMPRESSED"]

    DEFAULT_PARAMS = {
        # Risk
        "risk_percent":              1.0,
        "max_parallel_positions":    2,
        # ATR stops — tighter for reversion
        "sl_atr_multiplier":         1.4,
        "tp_atr_multiplier":         2.2,
        "breakeven_atr":             1.0,
        "trailing_start_atr":        1.2,
        "trailing_step_atr":         0.8,
        # RSI thresholds
        "rsi_oversold":              32.0,
        "rsi_overbought":            68.0,
        # VWAP deviation threshold (as multiple of ATR)
        "vwap_deviation_atr_mult":   1.5,
        # ADX ceiling — only trade in ranging/weak-trend conditions
        "adx_ceiling":               24.0,
        "entry_cooldown_candles":    5,
        "fresh_signal_only":         True,
        # Session
        "session_filter_enabled":    False,
        "allowed_hours":             [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
        # Misc
        "partial_close_enabled":     True,
        "partial_close_progress":    0.6,
        "partial_close_pct":         0.3,
        "monitor_roll_enabled":      False,
        "monitor_roll_progress":     0.3,
        "ema_slowing_lookback":      1,
        "candle_strength_threshold": 0.0,
        "spread":                    0.0,
        "commission_per_unit":       0.0,
        "min_atr_threshold":         0.0,
        "consecutive_loss_brake":    0,
        "daily_max_loss_pct":        0.0,
        # V1 compat
        "atr_period":                14,
        "ema_fast":                  9,
        "ema_slow":                  21,
        "supertrend_period":         10,
        "supertrend_multiplier":     3.0,
        # V3 threshold
        "readiness_threshold":       50.0,
    }

    def __init__(self, params: dict | None = None):
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}

    # ── V2BaseStrategy interface ───────────────────────────────────────────────

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
        # Bollinger-style VWAP deviation band
        vwap_series = df["vwap"]
        df["vwap_upper"] = vwap_series + df["atr"] * self.params["vwap_deviation_atr_mult"]
        df["vwap_lower"] = vwap_series - df["atr"] * self.params["vwap_deviation_atr_mult"]
        return df

    def generate_signal(self, df: pd.DataFrame) -> dict:
        required = ["rsi", "adx", "vwap", "atr", "close", "vwap_upper", "vwap_lower"]
        if not self._last_ready(df, required):
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        row     = df.iloc[-1]
        reasons = []
        strength = 50

        rsi_val    = float(row.get("rsi",         50.0) or 50.0)
        adx_val    = float(row.get("adx",          0.0) or 0.0)
        close      = float(row.get("close",         0.0) or 0.0)
        vwap_upper = float(row.get("vwap_upper",    0.0) or 0.0)
        vwap_lower = float(row.get("vwap_lower",    0.0) or 0.0)

        # Gate: only trade in ranging / weak-trend conditions
        if adx_val > self.params["adx_ceiling"]:
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        # ── BUY: oversold at lower VWAP band ─────────────────────────────────
        is_buy = (
            rsi_val <= self.params["rsi_oversold"]
            and close <= vwap_lower
        )
        # ── SELL: overbought at upper VWAP band ───────────────────────────────
        is_sell = (
            rsi_val >= self.params["rsi_overbought"]
            and close >= vwap_upper
        )

        if not is_buy and not is_sell:
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        # Strength bonus for deeper extremes
        if is_buy:
            reasons.append(f"RSI Oversold ({rsi_val:.1f} ≤ {self.params['rsi_oversold']:.1f})")
            reasons.append(f"Price at/below VWAP Lower Band")
            if rsi_val < 25:
                strength += 20; reasons.append("Extreme Oversold (RSI < 25)")
            if adx_val < 15:
                strength += 10; reasons.append("Very Weak Trend (ADX < 15) — ideal ranging")
            strength = min(strength, 100)
            return {"signal": "BUY", "strength": int(strength), "reasons": reasons}

        reasons.append(f"RSI Overbought ({rsi_val:.1f} ≥ {self.params['rsi_overbought']:.1f})")
        reasons.append(f"Price at/above VWAP Upper Band")
        if rsi_val > 75:
            strength += 20; reasons.append("Extreme Overbought (RSI > 75)")
        if adx_val < 15:
            strength += 10; reasons.append("Very Weak Trend (ADX < 15) — ideal ranging")
        strength = min(strength, 100)
        return {"signal": "SELL", "strength": int(strength), "reasons": reasons}

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
        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "RANGING")

        h4_dir = self._get_ctx_val(ctx, "h4_structure.macro_direction", "NEUTRAL")
        trend_persistence = float(self._get_ctx_val(ctx, "h4_structure.trend_persistence", 0.0))
        if trend_persistence == 0.0:
            h1_struct = self._get_ctx_val(ctx, "h1_structure", {}) or self._get_ctx_val(ctx, "mtf_context.h1_structure", {})
            if isinstance(h1_struct, dict):
                trend_persistence = float(h1_struct.get("trend_persistence", 0.5))
            else:
                trend_persistence = 0.5

        vol_state = self._get_ctx_val(ctx, "volatility_state", None)
        if not vol_state:
            vol_state = self._get_ctx_val(ctx, "mtf_context.h1_structure.volatility_state", "NORMAL")

        breakout_loading = float(self._get_ctx_val(ctx, "regime_transition.breakout_loading", 0.0))
        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))
        adx_val = float(self._get_ctx_val(ctx, "mtf_context.h1_structure._adx", 20.0))
        m5_timing = float(self._get_ctx_val(ctx, "m5_precision.m5_timing_score", 50.0))

        # 1. Trend strength (inverted logic: lower ADX means stronger ranging alignment)
        trend_strength = float(np.clip(100.0 - adx_val * 3.0, 0.0, 100.0))
        if h4_dir == "NEUTRAL":
            trend_strength = min(trend_strength + 20.0, 100.0)

        # 2. Volatility alignment
        if vol_state == "NORMAL":
            vol_align = 80.0
        elif vol_state == "LOW":
            vol_align = 100.0
        else:  # HIGH
            vol_align = 30.0

        # 3. Structure quality (inverted trend persistence: weak trend is better for range)
        struct_quality = float(np.clip((1.0 - trend_persistence) * 100.0, 0.0, 100.0))

        # 4. Execution readiness
        exec_readiness = readiness_score

        # 5. Timing alignment
        timing_align = m5_timing

        # Soft Penalties
        penalties = 0.0
        if h4_dir != "NEUTRAL" and regime != "RANGING":
            penalties += 10.0
        if trend_persistence > 0.5:
            penalties += 10.0
        if breakout_loading >= 40.0:
            penalties += 10.0
        if breakout_loading >= 70.0:
            penalties += 20.0
        if readiness_score < 50.0:
            penalties += 10.0

        # Missing context checks for uncertainty penalties
        uncertainty = 0.0
        if self._get_ctx_val(ctx, "h4_structure", None) is None:
            uncertainty += 5.0
        if self._get_ctx_val(ctx, "execution_readiness", None) is None:
            uncertainty += 5.0
        if self._get_ctx_val(ctx, "m5_precision", None) is None:
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
        Validates context for Mean Reversion eligibility.
        Hard-fails only on:
          - Trending regime (regime == TRENDING)
          - Volatility state is HIGH (vol_state == HIGH)
          - Severe readiness blockage (readiness_score < 20.0)
        """
        if ctx is None:
            return False

        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "RANGING")

        vol_state = self._get_ctx_val(ctx, "volatility_state", None)
        if not vol_state:
            vol_state = self._get_ctx_val(ctx, "mtf_context.h1_structure.volatility_state", "NORMAL")

        readiness_score = float(self._get_ctx_val(ctx, "execution_readiness.readiness_score", 50.0))

        # Hard blocks
        if regime == "TRENDING":
            return False
        if vol_state == "HIGH":
            return False
        if readiness_score < 20.0:
            return False

        return True

    def build_execution_candidate(self, ctx) -> dict | None:
        """Builds the execution candidate if context is valid."""
        if not self.validate_context(ctx):
            return None

        # Opposite of micro direction, fallback to BUY
        m5_dir = self._get_ctx_val(ctx, "m5_precision.micro_direction", "NEUTRAL")
        direction = "BUY" if m5_dir == "BEARISH" else ("SELL" if m5_dir == "BULLISH" else "BUY")

        regime = self._get_ctx_val(ctx, "market_regime", None)
        if not regime:
            regime = self._get_ctx_val(ctx, "mtf_context.h1_structure.macro_regime", "RANGING")

        confidence = self.score_market_fit(ctx)

        snapshot = {
            "macro_regime": str(regime),
            "trend_persistence": float(self._get_ctx_val(ctx, "h4_structure.trend_persistence", 0.0)),
            "volatility_state": str(self._get_ctx_val(ctx, "mtf_context.h1_structure.volatility_state", "NORMAL")),
        }

        risk_ctx = {
            "exhaustion_risk": float(self._get_ctx_val(ctx, "h4_structure.exhaustion_risk", 50.0)),
            "risk_score": float(self._get_ctx_val(ctx, "institutional_risk.risk_score", 30.0)),
        }

        candidate = {
            "strategy":            self.STRATEGY_NAME,
            "candidate_type":      "mean_reversion",
            "direction":           direction,
            "market_state":        str(regime),
            "confidence":          round(float(confidence), 1),
            "confidence_breakdown": self.get_confidence_breakdown(ctx),
            "timeframe_bias":      "NEUTRAL",
            "execution_timeframe": "M5",
            "entry_style":         "mean_reversion",
            "reasons":             ["Balanced market structure", "Weak trend persistence", "Absence of breakout pressure"],
            "risk_context":        risk_ctx,
            "context_snapshot":    snapshot,
        }
        return candidate

    def score_market_fit(self, regime: dict) -> float:
        """Scores fit: trend strength/ADX suitability (40%), volatility alignment (20%), structure (10%), readiness (15%), timing (15%)."""
        if regime is None:
            return 0.0

        breakdown = self.get_confidence_breakdown(regime)
        base_score = (
            breakdown["trend_strength"] * 0.40 +
            breakdown["volatility_alignment"] * 0.20 +
            breakdown["structure_quality"] * 0.10 +
            breakdown["execution_readiness"] * 0.15 +
            breakdown["timing_alignment"] * 0.15
        )

        if base_score > 40.0:
            base_score = base_score * 1.15

        final_score = base_score - breakdown["soft_penalties"] - breakdown["uncertainty_penalties"]
        return float(np.clip(final_score, 0.0, 100.0))

    def calculate_sl_tp(self, price: float, atr: float, direction: str):
        return self._atr_sl_tp(price, atr, direction)

    def should_exit(self, position: dict, candle: dict) -> bool:
        """Exit when RSI returns to neutral (50) — mean reversion completed."""
        rsi_val = float(candle.get("rsi", 50.0) or 50.0)
        if position["direction"] == "BUY":
            return rsi_val >= 55.0
        return rsi_val <= 45.0

    def validate_entry(self, df: pd.DataFrame) -> bool:
        row = df.iloc[-1]
        if not self._is_in_session(row.get("timestamp")):
            return False
        required = ["rsi", "adx", "vwap", "atr", "close"]
        return self._last_ready(df, required) and float(row.get("atr", 0) or 0) > 0

    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return MeanReversionStrategy(params)
