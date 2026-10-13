"""
strategies/v2_base_strategy.py
Abstract base class for all NexusBot V2 strategies.

Key contract:
  - All strategies inherit from V2BaseStrategy.
  - All indicator computation is delegated to engine.feature_engineering.
  - run_backtest() uses the EXISTING BacktestEngine - there is ONE truth engine.
"""
from abc import ABC, abstractmethod
import pandas as pd


class MetadataDescriptor:
    def __get__(self, instance, owner):
        name = getattr(owner, "STRATEGY_NAME", owner.__name__)
        doc = getattr(owner, "__doc__", "") or name
        return {
            "name": name,
            "description": doc.strip(),
            "version": "1.0.0",
            "risk_level": "MEDIUM"
        }


class V2BaseStrategy(ABC):
    metadata = MetadataDescriptor()

    def __setattr__(self, name, value):
        if name == "params" and isinstance(value, dict):
            base = {
                "risk_percent": 1.0,
                "max_parallel_positions": 3,
                "sl_atr_multiplier": 1.7,
                "tp_atr_multiplier": 2.1,
                "breakeven_atr": 1.0,
                "trailing_start_atr": 1.2,
                "trailing_step_atr": 1.0,
                "partial_close_enabled": True,
                "partial_close_progress": 0.55,
                "partial_close_pct": 0.25,
                "spread": 0.0,
                "commission_per_unit": 0.0,
            }
            value = {**base, **value}
        super().__setattr__(name, value)

    """
    Abstract base for NexusBot V2 strategies.

    Subclasses MUST implement:
      - get_strategy_name()
      - get_supported_regimes()
      - get_default_parameters()
      - prepare_indicators(df)        - call compute_features() + any extras
      - generate_signal(df)           - return dict with 'signal' key
      - score_market_fit(regime)      - return float 0-100
      - calculate_sl_tp(price, atr, direction)
      - should_exit(position, candle)

    V3 hooks are optional and default-safe:
      - get_supported_market_states()
      - validate_context(ctx)
      - build_execution_candidate(ctx)

    run_backtest() is implemented here using the existing BacktestEngine.
    """

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Human-readable name, e.g. 'Elder Swing'."""

    @abstractmethod
    def get_supported_regimes(self) -> list:
        """
        List of regime strings this strategy performs well in.
        e.g. ['TRENDING'] or ['VOLATILE', 'TRENDING']
        """

    def get_supported_market_states(self) -> list:
        """
        Optional V3 state support contract.

        Default behavior preserves backward compatibility by using the
        legacy supported regimes as the strategy's supported market states.
        """
        return list(self.get_supported_regimes() or [])

    @abstractmethod
    def get_default_parameters(self) -> dict:
        """
        Returns the default parameter dict for this strategy.
        Must be a flat dict of numeric / bool values.
        """

    @abstractmethod
    def prepare_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Returns a feature-enriched copy of `df`.
        MUST call engine.feature_engineering.compute_features(df) first,
        then add any strategy-specific columns on top.
        """

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> dict:
        """
        Returns a signal dict:
        {
            "signal"   : "BUY" | "SELL" | "HOLD",
            "strength" : int   0-100,
            "reasons"  : list[str],
        }
        `df` is the full history up to the current candle (feature-engineered).
        """

    @abstractmethod
    def score_market_fit(self, regime: dict) -> float:
        """
        Given a regime dict from MarketRegimeEngine.detect(), returns a
        market-fit score (0-100) for this strategy.
        Used by the tournament engine to rank strategies.
        """

    def validate_context(self, ctx) -> bool:
        """
        Optional V3 eligibility hook.

        Default implementation is permissive so existing strategies remain
        operational until they opt into richer context-aware validation.
        """
        return True

    def build_execution_candidate(self, ctx) -> dict | None:
        """
        Optional V3 execution candidate hook.

        Default implementation returns None so strategies can continue to
        participate in tournament ranking without providing live candidates.
        """
        return None

    def monitor_and_roll(self, position: dict, candle: dict) -> bool:
        """
        Optional monitoring and roll logic. Default returns False.
        Can be overridden or enabled via parameters.
        """
        if not self.params.get("monitor_roll_enabled", False):
            return False
        side = 1 if position["direction"] == "BUY" else -1
        progress = ((candle["close"] - position["entry_price"]) * side) / max(abs(position["tp"] - position["entry_price"]), 1e-9)
        ema_slowing = candle.get("ema_slowing", False)
        return progress >= self.params.get("monitor_roll_progress", 0.3) and ema_slowing

    @abstractmethod
    def calculate_sl_tp(self, price: float, atr: float, direction: str):
        """Returns (stop_loss, take_profit) prices."""

    @abstractmethod
    def should_exit(self, position: dict, candle: dict) -> bool:
        """
        Returns True if the strategy's exit logic says to close `position`
        at the current `candle`.
        """

    def run_backtest(
        self,
        df: pd.DataFrame,
        params: dict | None = None,
        starting_balance: float = 10_000.0,
    ) -> dict:
        """
        Runs a full backtest using the existing BacktestEngine.
        This is the ONE truth engine - no lightweight fake loops.
        """
        from engine.backtest_engine import BacktestEngine
        from engine.event_bus import EventBus

        merged_params = {**self.get_default_parameters(), **(params or {})}
        strategy_instance = self._create_parameterised_instance(merged_params)

        bus = EventBus()
        engine = BacktestEngine(strategy_instance, starting_balance=starting_balance, event_bus=bus)
        return engine.run(df)

    def _create_parameterised_instance(self, params: dict):
        """
        Default: re-instantiate self.__class__ with given params.
        Adapters may override this to wrap legacy strategies instead.
        """
        return self.__class__.__new_with_params__(params)

    @classmethod
    def __new_with_params__(cls, params: dict):
        """
        Factory: create a fully-initialised instance with the given params dict.
        Subclasses that do not override __init__ can use this as-is.
        """
        instance = cls.__new__(cls)
        instance.params = params
        return instance

    def _atr_sl_tp(self, price: float, atr: float, direction: str) -> tuple:
        """Standard ATR-based SL/TP calculation using this strategy's params."""
        sl_mult = self.params.get("sl_atr_multiplier", 1.8)
        tp_mult = self.params.get("tp_atr_multiplier", 3.5)
        if direction == "BUY":
            return price - atr * sl_mult, price + atr * tp_mult
        return price + atr * sl_mult, price - atr * tp_mult

    def _is_in_session(self, timestamp) -> bool:
        """Check if timestamp falls inside the strategy's allowed trading hours."""
        if not self.params.get("session_filter_enabled", False):
            return True
        try:
            dt = pd.to_datetime(timestamp)
            hour = dt.hour if dt.tzinfo is None else dt.tz_convert("UTC").hour
            return hour in self.params.get("allowed_hours", list(range(24)))
        except Exception:
            return True

    def _last_ready(self, df: pd.DataFrame, required: list) -> bool:
        """Returns True only if all required columns exist and are non-NaN on the last row."""
        if df.empty:
            return False
        row = df.iloc[-1]
        return all(col in row.index and not pd.isna(row[col]) for col in required)
