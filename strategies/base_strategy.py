from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    metadata = {
        "name": "Base Strategy",
        "description": "Shared strategy contract",
        "risk_level": "N/A",
        "recommended_markets": [],
        "supported_timeframes": [],
        "version": "1.0.0",
    }

    default_params = {
        "risk_percent": 1.0,
        "max_parallel_positions": 3,
        "atr_period": 14,
        "ema_fast": 9,
        "ema_slow": 20,
        "supertrend_period": 10,
        "supertrend_multiplier": 3.0,
        "sl_atr_multiplier": 1.7,
        "tp_atr_multiplier": 2.1,
        "breakeven_atr": 1.0,
        "trailing_start_atr": 1.2,
        "trailing_step_atr": 1.0,
        "partial_close_enabled": True,
        "partial_close_progress": 0.55,
        "partial_close_pct": 0.25,
        "monitor_roll_progress": 0.30,
        "ema_slowing_lookback": 1,
        "fresh_signal_only": True,
        "entry_cooldown_candles": 3,
        "monitor_roll_enabled": False,
        "candle_strength_threshold": 0.1,
        "session_filter_enabled": False,
        "allowed_hours": [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22],
        "spread": 0.0,
        "commission_per_unit": 0.0,
        "min_atr_threshold": 0.0,
        "consecutive_loss_brake": 0,
        "daily_max_loss_pct": 0.0,
    }

    def __init__(self, params: dict | None = None):
        self.params = {**self.default_params, **(params or {})}

    @abstractmethod
    def prepare_indicators(self, df):
        raise NotImplementedError

    @abstractmethod
    def generate_signal(self, df):
        raise NotImplementedError

    @abstractmethod
    def calculate_sl_tp(self, price, atr, direction):
        raise NotImplementedError

    def validate_entry(self, df):
        if df.empty:
            return False
        row = df.iloc[-1]
        if not self._is_in_session(row["timestamp"]):
            return False
        if not self._validate_candle_strength(row):
            return False
        if not self._validate_min_atr(row):
            return False
        return True

    @abstractmethod
    def should_exit(self, position, candle):
        raise NotImplementedError

    def monitor_and_roll(self, position, candle) -> bool:
        if not self.params.get("monitor_roll_enabled", False):
            return False
        side = 1 if position["direction"] == "BUY" else -1
        progress = ((candle["close"] - position["entry_price"]) * side) / max(abs(position["tp"] - position["entry_price"]), 1e-9)
        ema_slowing = candle.get("ema_slowing", False)
        return progress >= self.params["monitor_roll_progress"] and ema_slowing

    def _is_in_session(self, timestamp) -> bool:
        if not self.params.get("session_filter_enabled", False):
            return True
        import pandas as pd
        dt = pd.to_datetime(timestamp)
        if dt.tzinfo is not None:
            hour = dt.tz_convert("UTC").hour
        else:
            hour = dt.hour
        return hour in self.params.get("allowed_hours", [])

    def _validate_candle_strength(self, row) -> bool:
        threshold = self.params.get("candle_strength_threshold", 0.0)
        if threshold <= 0.0:
            return True
        atr_val = row.get("atr", 0.0) or 0.0
        if atr_val <= 0.0:
            return True
        body = abs(row["close"] - row["open"])
        return body > atr_val * threshold

    def _validate_min_atr(self, row) -> bool:
        min_atr = self.params.get("min_atr_threshold", 0.0)
        if min_atr <= 0.0:
            return True
        atr_val = row.get("atr", 0.0) or 0.0
        return atr_val >= min_atr

    def _atr_sl_tp(self, price, atr, direction):
        if direction == "BUY":
            return price - atr * self.params["sl_atr_multiplier"], price + atr * self.params["tp_atr_multiplier"]
        return price + atr * self.params["sl_atr_multiplier"], price - atr * self.params["tp_atr_multiplier"]

    def _last_ready(self, df, required):
        if df.empty:
            return False
        row = df.iloc[-1]
        return not row[required].isna().any()

    def get_genome(self) -> dict:
        return {
            "entry_logic": [
                "EMA Fast vs Slow Crossover",
                "Supertrend Directional Alignment"
            ] + ([f"HTF EMA Confirmation ({self.params.get('htf_timeframe')})"] if self.params.get("htf_confirmation_enabled") else []),
            "filters": (
                [f"RSI Momentum (> {self.params.get('rsi_buy_min')} BUY, < {self.params.get('rsi_sell_max')} SELL)"] if self.params.get("rsi_buy_min") else []
            ) + (
                [f"ADX Trend Strength (> {self.params.get('adx_threshold')})"] if self.params.get("adx_threshold") else []
            ) + (
                [f"Session Filter ({self.params.get('allowed_hours')})"] if self.params.get("session_filter_enabled") else []
            ) + (
                ["Candle Strength Filter"] if self.params.get("candle_strength_threshold", 0.0) > 0.0 else []
            ),
            "risk_logic": [
                f"Risk percent: {self.params.get('risk_percent')}%",
                f"Max parallel positions: {self.params.get('max_parallel_positions')}",
                f"Consecutive loss brake: {self.params.get('consecutive_loss_brake')}",
                f"Daily max loss: {self.params.get('daily_max_loss_pct')}%"
            ] + (
                [f"Spread protection (< {self.params.get('max_spread_atr_ratio')} ATR)"] if self.params.get("max_spread_atr_ratio") else []
            ),
            "exit_logic": [
                f"Take profit ATR: {self.params.get('tp_atr_multiplier')}x",
                f"Stop loss ATR: {self.params.get('sl_atr_multiplier')}x"
            ] + (
                [f"Breakeven ATR: {self.params.get('breakeven_atr')}x"] if self.params.get("breakeven_atr") else []
            ) + (
                [f"Trailing stop step ATR: {self.params.get('trailing_step_atr')}x"] if self.params.get("trailing_step_atr") else []
            ) + (
                ["Monitor and Roll"] if self.params.get("monitor_roll_enabled") else []
            )
        }
