"""
strategies/breakout_hunter.py
Breakout Hunter Strategy — NexusBot V2.

Best for: ATR compression breakouts, volatility expansion, session breakouts.
Logic   : Compression phase → expansion trigger → volume spike + breakout candle.
Regimes : VOLATILE, TRENDING
"""
import pandas as pd
import numpy as np

from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class BreakoutHunterStrategy(V2BaseStrategy):

    STRATEGY_NAME     = "Breakout Hunter"
    SUPPORTED_REGIMES = ["VOLATILE", "TRENDING"]

    DEFAULT_PARAMS = {
        # Risk
        "risk_percent":              1.0,
        "max_parallel_positions":    1,
        # ATR stops — wider for breakouts
        "sl_atr_multiplier":         1.6,
        "tp_atr_multiplier":         3.5,
        "breakeven_atr":             1.2,
        "trailing_start_atr":        1.5,
        "trailing_step_atr":         1.2,
        # Breakout filters
        "atr_expansion_mult":        1.30,   # ATR must be > 1.3× mean
        "volume_spike_mult":         1.80,   # Volume must be > 1.8× mean
        "compression_threshold":     0.80,   # Prior compression: ATR < 0.8× mean
        "entry_cooldown_candles":    4,
        "fresh_signal_only":         True,
        # Session
        "session_filter_enabled":    False,
        "allowed_hours":             [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
        # Misc
        "partial_close_enabled":     False,
        "partial_close_progress":    0.55,
        "partial_close_pct":         0.25,
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
    }

    def __init__(self, params: dict | None = None):
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}

    # ── V2BaseStrategy interface ───────────────────────────────────────────────

    def get_strategy_name(self) -> str:
        return self.STRATEGY_NAME

    def get_supported_regimes(self) -> list:
        return self.SUPPORTED_REGIMES

    def get_default_parameters(self) -> dict:
        return dict(self.DEFAULT_PARAMS)

    def prepare_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = compute_features(df)
        # Track whether the prior 5 bars were compressed
        df["was_compressed"] = df["compression_score"].shift(1).rolling(5).mean() < self.params["compression_threshold"]
        return df

    def generate_signal(self, df: pd.DataFrame) -> dict:
        required = ["atr", "atr_mean", "volume_ratio", "momentum", "ema_fast", "rsi"]
        if not self._last_ready(df, required):
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        row    = df.iloc[-1]
        strength = 50
        reasons = []

        atr_val      = float(row.get("atr",             0.0) or 0.0)
        atr_mean_val = float(row.get("atr_mean",        atr_val) or atr_val)
        vol_ratio    = float(row.get("volume_ratio",    1.0) or 1.0)
        momentum_val = float(row.get("momentum",        0.0) or 0.0)
        ema_fast     = float(row.get("ema_fast",        0.0) or 0.0)
        close        = float(row.get("close",           0.0) or 0.0)
        rsi_val      = float(row.get("rsi",             50.0) or 50.0)

        # ── Core breakout filters ─────────────────────────────────────────────
        atr_expanding = atr_val > atr_mean_val * self.params["atr_expansion_mult"]
        vol_spiking   = vol_ratio > self.params["volume_spike_mult"]

        if not atr_expanding or not vol_spiking:
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        reasons.append(f"ATR Expansion {atr_val:.4f} > {atr_mean_val * self.params['atr_expansion_mult']:.4f}")
        reasons.append(f"Volume Spike {vol_ratio:.2f}× mean")

        # ── Direction ─────────────────────────────────────────────────────────
        is_buy  = momentum_val > 0 and close > ema_fast and rsi_val > 52
        is_sell = momentum_val < 0 and close < ema_fast and rsi_val < 48

        if not is_buy and not is_sell:
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        # ── Strength bonuses ──────────────────────────────────────────────────
        if vol_ratio > 2.5:
            strength += 20; reasons.append(f"Extreme Volume ({vol_ratio:.1f}×)")
        if atr_val > atr_mean_val * 1.8:
            strength += 15; reasons.append("Extreme ATR Expansion (>1.8×)")

        was_compressed = bool(row.get("was_compressed", False))
        if was_compressed:
            strength += 15; reasons.append("Prior Compression Detected")

        strength = min(strength, 100)

        if is_buy:
            reasons.append("Bullish Breakout Direction")
            return {"signal": "BUY", "strength": int(strength), "reasons": reasons}
        reasons.append("Bearish Breakout Direction")
        return {"signal": "SELL", "strength": int(strength), "reasons": reasons}

    def score_market_fit(self, regime: dict) -> float:
        regime_label  = regime.get("regime", "RANGING")
        brk_prob      = float(regime.get("breakout_probability", 0.5))
        vol_score     = float(regime.get("volatility_score", 50.0))

        if regime_label == "VOLATILE":
            base = 60.0 + brk_prob * 25.0 + vol_score * 0.15
            return float(np.clip(base, 0, 100))
        elif regime_label == "TRENDING":
            base = 45.0 + brk_prob * 20.0
            return float(np.clip(base, 0, 100))
        elif regime_label == "LOW_VOLATILITY":
            # Compression → potential future breakout setup
            return float(np.clip(20.0 + brk_prob * 30.0, 0, 60))
        else:  # RANGING
            return 22.0

    def calculate_sl_tp(self, price: float, atr: float, direction: str):
        return self._atr_sl_tp(price, atr, direction)

    def should_exit(self, position: dict, candle: dict) -> bool:
        """Exit when momentum reverses."""
        momentum_val = candle.get("momentum", 0.0) or 0.0
        if position["direction"] == "BUY":
            return float(momentum_val) < 0
        return float(momentum_val) > 0

    def validate_entry(self, df: pd.DataFrame) -> bool:
        row = df.iloc[-1]
        if not self._is_in_session(row.get("timestamp")):
            return False
        required = ["atr", "atr_mean", "volume_ratio", "momentum", "ema_fast", "rsi"]
        return self._last_ready(df, required) and float(row.get("atr", 0) or 0) > 0

    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return BreakoutHunterStrategy(params)
