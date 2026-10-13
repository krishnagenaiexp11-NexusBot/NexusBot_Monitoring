"""
strategies/elder_swing.py
Elder Swing Strategy — NexusBot V2.

Best for: Strong TRENDING markets, gold (XAUUSD), indices.
Logic   : EMA alignment + ADX > 25 + EMA slope confirmation.
Entry   : Pullback recovery toward EMA slow zone in trend direction.
Exit    : EMA cross reversal or Supertrend flip.
"""
import pandas as pd
import numpy as np

from strategies.v2_base_strategy import V2BaseStrategy
from engine.feature_engineering import compute_features


class ElderSwingStrategy(V2BaseStrategy):

    STRATEGY_NAME     = "Elder Swing"
    SUPPORTED_REGIMES = ["TRENDING"]

    DEFAULT_PARAMS = {
        # Risk
        "risk_percent":           1.0,
        "max_parallel_positions": 2,
        # ATR stops
        "sl_atr_multiplier":      1.8,
        "tp_atr_multiplier":      4.0,
        "breakeven_atr":          1.5,
        "trailing_start_atr":     1.8,
        "trailing_step_atr":      1.0,
        # Entry filters
        "adx_threshold":          22.0,
        "entry_cooldown_candles": 6,
        "fresh_signal_only":      True,
        # Session
        "session_filter_enabled": False,
        "allowed_hours":          [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
        # Misc
        "partial_close_enabled":  True,
        "partial_close_progress": 0.55,
        "partial_close_pct":      0.25,
        "monitor_roll_enabled":   False,
        "monitor_roll_progress":  0.3,
        "ema_slowing_lookback":   1,
        "candle_strength_threshold": 0.0,
        "spread":                 0.0,
        "commission_per_unit":    0.0,
        "min_atr_threshold":      0.0,
        "consecutive_loss_brake": 0,
        "daily_max_loss_pct":     0.0,
        # V1 compat
        "atr_period":             14,
        "ema_fast":               9,
        "ema_slow":               21,
        "supertrend_period":      10,
        "supertrend_multiplier":  3.0,
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
        from utils.indicator_helpers import supertrend as _supertrend
        df = compute_features(df)
        st = _supertrend(df, self.params["supertrend_period"], self.params["supertrend_multiplier"])
        df = df.join(st)
        return df

    def generate_signal(self, df: pd.DataFrame) -> dict:
        if not self._last_ready(df, ["ema_fast", "ema_slow", "adx", "atr"]):
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        row     = df.iloc[-1]
        reasons = []
        strength = 50

        adx_val  = float(row.get("adx", 0.0) or 0.0)
        ema_fast = float(row.get("ema_fast", 0.0) or 0.0)
        ema_slow = float(row.get("ema_slow", 0.0) or 0.0)
        close    = float(row.get("close", 0.0) or 0.0)
        vwap_val = float(row.get("vwap", 0.0) or 0.0)

        # Minimum ADX filter — no signal in weak-trend markets
        if adx_val < self.params["adx_threshold"]:
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        is_buy  = ema_fast > ema_slow and close > vwap_val
        is_sell = ema_fast < ema_slow and close < vwap_val

        if not is_buy and not is_sell:
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        # Supertrend confirmation (optional — column may not exist)
        st_dir = row.get("supertrend_dir", None)

        if is_buy:
            reasons.append(f"EMA Fast {ema_fast:.4f} > Slow {ema_slow:.4f}")
            reasons.append(f"ADX {adx_val:.1f} > {self.params['adx_threshold']:.1f}")
            reasons.append("Close above VWAP (bullish bias)")
            if adx_val > 30:
                strength += 20; reasons.append("Strong trend (ADX > 30)")
            if st_dir == 1:
                strength += 15; reasons.append("Supertrend bullish confirmation")
            strength = min(strength, 100)
            return {"signal": "BUY", "strength": int(strength), "reasons": reasons}

        if is_sell:
            reasons.append(f"EMA Fast {ema_fast:.4f} < Slow {ema_slow:.4f}")
            reasons.append(f"ADX {adx_val:.1f} > {self.params['adx_threshold']:.1f}")
            reasons.append("Close below VWAP (bearish bias)")
            if adx_val > 30:
                strength += 20; reasons.append("Strong trend (ADX > 30)")
            if st_dir == -1:
                strength += 15; reasons.append("Supertrend bearish confirmation")
            strength = min(strength, 100)
            return {"signal": "SELL", "strength": int(strength), "reasons": reasons}

        return {"signal": "HOLD", "strength": 0, "reasons": []}

    def score_market_fit(self, regime: dict) -> float:
        """
        Scores how well the current regime suits Elder Swing.
        Peak score when TRENDING + strong ADX + clear direction.
        """
        regime_label = regime.get("regime", "RANGING")
        trend_str    = float(regime.get("trend_strength", 0.0))
        direction    = regime.get("direction", "NEUTRAL")

        if regime_label == "TRENDING":
            base = 65.0
            base += min(trend_str * 0.4, 25.0)        # ADX boost (max +25)
            if direction != "NEUTRAL":
                base += 8.0                            # Clear direction bonus
            persistence = float(regime.get("trend_persistence", 0.5))
            base += persistence * 5.0                  # Structural bonus
            return float(np.clip(base, 0, 100))
        elif regime_label == "VOLATILE":
            return 38.0    # Can work but not optimal
        elif regime_label == "RANGING":
            return 12.0    # Poor fit
        else:              # LOW_VOLATILITY
            return 8.0

    def calculate_sl_tp(self, price: float, atr: float, direction: str):
        return self._atr_sl_tp(price, atr, direction)

    def should_exit(self, position: dict, candle: dict) -> bool:
        """Exit on EMA cross or Supertrend flip."""
        st_dir = candle.get("supertrend_dir", None)
        if position["direction"] == "BUY":
            return st_dir == -1
        return st_dir == 1

    def validate_entry(self, df: pd.DataFrame) -> bool:
        row = df.iloc[-1]
        if not self._is_in_session(row.get("timestamp")):
            return False
        required = ["ema_fast", "ema_slow", "adx", "atr", "vwap"]
        return self._last_ready(df, required) and float(row.get("atr", 0) or 0) > 0

    # ── V2BaseStrategy factory ────────────────────────────────────────────────
    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)

    def _create_parameterised_instance(self, params: dict):
        return ElderSwingStrategy(params)
