"""
engine/strategy_registry.py
Central registry of all available V2 strategies.

Import strategies here - not inside the tournament engine.
Add new strategies to AVAILABLE_STRATEGIES only.
"""
from strategies.elder_swing import ElderSwingStrategy
from strategies.breakout_hunter import BreakoutHunterStrategy
from strategies.aggressive_scalper_adapter import AggressiveScalperAdapter
from strategies.mean_reversion import MeanReversionStrategy
from strategies.spike_catcher_adapter import SpikeCatcherAdapter
from strategies.momentum_continuation import MomentumContinuationStrategy
from strategies.compression_breakout import CompressionBreakoutStrategy
from strategies.liquidity_sweep_reversal import LiquiditySweepReversalStrategy
from strategies.session_breakout import SessionBreakoutStrategy
from strategies.structure_shift import StructureShiftStrategy
from strategies.exhaustion_reversal import ExhaustionReversalStrategy
from strategies.trap_reversal import TrapReversalStrategy
from strategies.fvg_reaction import FVGReactionStrategy
from strategies.dead_cat_bounce import DeadCatBounceStrategy
from strategies.absorption import AbsorptionStrategy


AVAILABLE_STRATEGIES = [
    ElderSwingStrategy(),
    BreakoutHunterStrategy(),
    AggressiveScalperAdapter(),
    MeanReversionStrategy(),
    SpikeCatcherAdapter(),
    MomentumContinuationStrategy(),
    CompressionBreakoutStrategy(),
    LiquiditySweepReversalStrategy(),
    SessionBreakoutStrategy(),
    StructureShiftStrategy(),
    ExhaustionReversalStrategy(),
    TrapReversalStrategy(),
    FVGReactionStrategy(),
    DeadCatBounceStrategy(),
    AbsorptionStrategy(),
]

_MARKET_STATE_FALLBACKS = {
    "COMPRESSED": ["COMPRESSED", "LOW_VOLATILITY", "RANGING"],
    "EXHAUSTED": ["EXHAUSTED", "TRENDING", "RANGING"],
    "SESSION_VOLATILITY": ["SESSION_VOLATILITY", "VOLATILE", "TRENDING"],
    "REVERSAL": ["REVERSAL", "RANGING", "TRENDING"],
    "TRAP_ENVIRONMENT": ["TRAP_ENVIRONMENT", "RANGING", "VOLATILE"],
    "HIGH_LIQUIDITY_HUNT": ["HIGH_LIQUIDITY_HUNT", "VOLATILE", "RANGING"],
    "PANIC": ["PANIC", "VOLATILE", "TRENDING"],
    "ABSORPTION": ["ABSORPTION", "RANGING", "TRENDING"],
}


def get_strategy_by_name(name: str):
    """Returns the first strategy whose name matches (case-insensitive)."""
    for strat in AVAILABLE_STRATEGIES:
        if strat.get_strategy_name().lower() == name.lower():
            return strat
    raise ValueError(f"Strategy '{name}' not found in registry.")


def list_strategy_names() -> list:
    return [s.get_strategy_name() for s in AVAILABLE_STRATEGIES]


def list_registered_strategies() -> list:
    """Returns the instantiated strategy registry."""
    return list(AVAILABLE_STRATEGIES)


def get_eligible_strategies(market_state: str | None, regime: str | None = None) -> list:
    """
    Returns the strategies eligible for the given V3 market state.

    Backward compatibility:
      - If a strategy does not implement V3 market states, its legacy
        supported regimes are used as fallback.
      - If no strategy matches, the full registry is returned.
    """
    candidate_states = _expand_candidate_states(market_state, regime)
    eligible = [s for s in AVAILABLE_STRATEGIES if _strategy_supports_any_state(s, candidate_states)]
    return eligible or list_registered_strategies()


def _expand_candidate_states(market_state: str | None, regime: str | None) -> list:
    ordered = []
    for value in (market_state, regime):
        if value and value not in ordered:
            ordered.append(value)
    if market_state:
        for value in _MARKET_STATE_FALLBACKS.get(market_state, []):
            if value not in ordered:
                ordered.append(value)
    return ordered


def _strategy_supports_any_state(strategy, candidate_states: list) -> bool:
    supported_states = []
    if hasattr(strategy, "get_supported_market_states"):
        try:
            supported_states = list(strategy.get_supported_market_states() or [])
        except Exception:
            supported_states = []

    supported_regimes = list(strategy.get_supported_regimes() or [])
    allowed = {str(item).upper() for item in supported_states + supported_regimes}
    for state in candidate_states:
        if str(state).upper() in allowed:
            return True
    return False
