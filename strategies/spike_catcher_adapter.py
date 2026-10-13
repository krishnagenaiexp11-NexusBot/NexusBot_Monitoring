"""
strategies/spike_catcher_adapter.py
Adapter wrapping the existing SpikeCatcher into the V2BaseStrategy interface.

Does NOT rewrite the proven core logic — only adapts it.
"""
import numpy as np
import pandas as pd

from strategies.v2_base_strategy import V2BaseStrategy
from strategies.spike_catcher import SpikeCatcher


class SpikeCatcherAdapter(V2BaseStrategy):

    STRATEGY_NAME     = "Spike Catcher"
    SUPPORTED_REGIMES = ["VOLATILE"]

    def __init__(self, params: dict | None = None):
        defaults = SpikeCatcher.default_params
        self.params = {**defaults, **(params or {})}
        self._inner = SpikeCatcher(self.params)

    # ── Identity ──────────────────────────────────────────────────────────────

    def get_strategy_name(self) -> str:
        return self.STRATEGY_NAME

    def get_supported_regimes(self) -> list:
        return self.SUPPORTED_REGIMES

    def get_default_parameters(self) -> dict:
        return dict(SpikeCatcher.default_params)

    # ── Delegation to inner strategy ──────────────────────────────────────────

    def prepare_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        return self._inner.prepare_indicators(df)

    def generate_signal(self, df: pd.DataFrame) -> dict:
        result = self._inner.generate_signal(df)
        if isinstance(result, dict):
            return result
        return {"signal": result, "strength": 50, "reasons": []}

    def calculate_sl_tp(self, price: float, atr: float, direction: str):
        return self._inner.calculate_sl_tp(price, atr, direction)

    def should_exit(self, position: dict, candle: dict) -> bool:
        return self._inner.should_exit(position, candle)

    # ── Tournament scoring ────────────────────────────────────────────────────

    def score_market_fit(self, regime: dict) -> float:
        """
        Spike Catcher is built for explosive volatility events.
        Peak score in VOLATILE regime with high breakout probability.
        """
        regime_label = regime.get("regime", "RANGING")
        brk_prob     = float(regime.get("breakout_probability", 0.5))
        vol_score    = float(regime.get("volatility_score", 50.0))

        if regime_label == "VOLATILE":
            base = 55.0 + brk_prob * 30.0 + vol_score * 0.15
            return float(np.clip(base, 0, 100))
        elif regime_label == "TRENDING":
            # Can work on strong trend continuations
            return float(np.clip(30.0 + brk_prob * 20.0, 0, 65))
        elif regime_label == "RANGING":
            return 15.0
        else:  # LOW_VOLATILITY
            return 5.0     # Worst fit — no spikes in low vol

    # ── Backtest ──────────────────────────────────────────────────────────────

    def _create_parameterised_instance(self, params: dict):
        """Use the proven SpikeCatcher for actual backtesting."""
        return SpikeCatcher(params)

    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)
