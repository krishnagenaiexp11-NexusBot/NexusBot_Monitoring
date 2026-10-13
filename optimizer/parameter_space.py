"""
optimizer/parameter_space.py
Per-strategy search spaces for V2 optimizer.

Broader ranges than V1 research/search_space.py to cover all V2 strategies.
"""

# ── Shared parameters (apply to all strategies) ───────────────────────────────
SHARED_SPACE = {
    "sl_atr_multiplier":      [1.2, 1.4, 1.6, 1.8, 2.0, 2.4, 2.8, 3.2],
    "tp_atr_multiplier":      [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
    "entry_cooldown_candles": [2, 4, 6, 8, 10, 12, 15],
    "breakeven_atr":          [1.0, 1.2, 1.5, 2.0],
    "trailing_step_atr":      [0.5, 0.8, 1.0, 1.5],
}

# ── Strategy-specific spaces (merged with SHARED_SPACE during sweeps) ─────────
STRATEGY_SPACES = {
    "Elder Swing": {
        **SHARED_SPACE,
        "adx_threshold": [18.0, 22.0, 25.0, 28.0, 32.0],
    },
    "Breakout Hunter": {
        **SHARED_SPACE,
        "atr_expansion_mult":    [1.2, 1.3, 1.5, 1.8, 2.0],
        "volume_spike_mult":     [1.5, 1.8, 2.0, 2.5, 3.0],
        "compression_threshold": [0.7, 0.8, 0.9],
    },
    "Aggressive Scalper": {
        **SHARED_SPACE,
        "adx_threshold": [18.0, 20.0, 24.0, 28.0, 32.0],
    },
    "Mean Reversion": {
        **SHARED_SPACE,
        "rsi_oversold":             [25.0, 30.0, 32.0, 35.0],
        "rsi_overbought":           [65.0, 68.0, 70.0, 75.0],
        "adx_ceiling":              [18.0, 22.0, 24.0, 28.0],
        "vwap_deviation_atr_mult":  [1.0, 1.2, 1.5, 2.0],
    },
    "Spike Catcher": {
        **SHARED_SPACE,
        "volume_spike_mult":     [1.5, 2.0, 2.5, 3.0],
        "atr_expansion_mult":    [1.3, 1.5, 1.8, 2.0],
    },
}


def get_space_for_strategy(strategy_name: str) -> dict:
    """Returns the parameter search space for a given strategy name."""
    return dict(STRATEGY_SPACES.get(strategy_name, SHARED_SPACE))
