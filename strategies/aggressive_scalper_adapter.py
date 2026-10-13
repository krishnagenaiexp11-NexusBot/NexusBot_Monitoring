"""
strategies/aggressive_scalper_adapter.py
Adapter wrapping the existing AggressiveScalper into the V2BaseStrategy interface.

Does NOT rewrite the proven core logic — only adapts it.
"""
import numpy as np
import pandas as pd

from strategies.v2_base_strategy import V2BaseStrategy
from strategies.aggressive_scalper import AggressiveScalper


class AggressiveScalperAdapter(V2BaseStrategy):

    STRATEGY_NAME     = "Aggressive Scalper"
    SUPPORTED_REGIMES = ["TRENDING", "VOLATILE"]

    def __init__(self, params: dict | None = None):
        defaults = AggressiveScalper.default_params
        self.params = {**defaults, **(params or {})}
        self._inner = AggressiveScalper(self.params)

    # ── Identity ──────────────────────────────────────────────────────────────

    def get_strategy_name(self) -> str:
        return self.STRATEGY_NAME

    def get_supported_regimes(self) -> list:
        return self.SUPPORTED_REGIMES

    def get_default_parameters(self) -> dict:
        return dict(AggressiveScalper.default_params)

    # ── Delegation to inner strategy ──────────────────────────────────────────

    def prepare_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Delegates to AggressiveScalper.prepare_indicators (proven logic)."""
        return self._inner.prepare_indicators(df)

    def generate_signal(self, df: pd.DataFrame) -> dict:
        """Delegates to AggressiveScalper.generate_signal (proven logic)."""
        result = self._inner.generate_signal(df)
        # Normalise to V2 format
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
        Aggressive Scalper excels in fast momentum + directional trending.
        Secondary fit in volatile sessions.
        """
        regime_label = regime.get("regime", "RANGING")
        trend_str    = float(regime.get("trend_strength", 0.0))
        direction    = regime.get("direction", "NEUTRAL")

        if regime_label == "TRENDING":
            # Good but requires very fast momentum — not as suited as Elder Swing
            base = 45.0 + min(trend_str * 0.25, 15.0)
            if direction != "NEUTRAL":
                base += 5.0
            return float(np.clip(base, 0, 100))
        elif regime_label == "VOLATILE":
            vol_score = float(regime.get("volatility_score", 50.0))
            return float(np.clip(40.0 + vol_score * 0.25, 0, 80))
        elif regime_label == "RANGING":
            return 20.0
        else:  # LOW_VOLATILITY
            return 10.0

    # ── Backtest ──────────────────────────────────────────────────────────────

    def _create_parameterised_instance(self, params: dict):
        """Use the proven AggressiveScalper for actual backtesting."""
        return AggressiveScalper(params)

    @classmethod
    def __new_with_params__(cls, params: dict):
        return cls(params)
