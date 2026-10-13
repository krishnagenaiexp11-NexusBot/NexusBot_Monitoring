import pandas as pd

from engine.event_bus import EventBus
from engine.execution_engine import ExecutionEngine
from engine.risk_manager import RiskManager
from engine.trade_manager import TradeManager
from utils.metrics import calculate_metrics


class BacktestEngine:
    def __init__(self, strategy, starting_balance: float = 10_000.0, event_bus: EventBus | None = None):
        self.strategy = strategy
        self.starting_balance = starting_balance
        self.event_bus = event_bus or EventBus()
        self.risk = RiskManager(starting_balance, strategy.params["risk_percent"], strategy.params["max_parallel_positions"], strategy.params)
        self.execution = ExecutionEngine(self.event_bus)
        self.trade_manager = TradeManager(self.event_bus)

    def run(self, df: pd.DataFrame) -> dict:
        prepared = self.strategy.prepare_indicators(df)

        # Safety net: ensure columns required for snapshots are present
        from utils.indicators import rsi, adx, atr
        if "rsi" not in prepared.columns:
            prepared["rsi"] = rsi(prepared["close"], 14)
        if "adx" not in prepared.columns:
            prepared["adx"] = adx(prepared, 14)
        if "atr" not in prepared.columns:
            prepared["atr"] = atr(prepared, 14)
        if "momentum" not in prepared.columns:
            prepared["momentum"] = prepared["close"].diff(3).fillna(0.0)
        if "volume_mean" not in prepared.columns:
            prepared["volume_mean"] = prepared["volume"].rolling(20).mean().fillna(prepared["volume"])
        if "atr_mean" not in prepared.columns:
            prepared["atr_mean"] = prepared["atr"].rolling(20).mean().fillna(prepared["atr"])

        open_positions = []
        trades = []
        equity_rows = []
        rejected_signals = []
        last_signal = "HOLD"
        last_entry_index = -10**9

        self.event_bus.emit("BACKTEST STARTED")
        for i in range(50, len(prepared)):
            history = prepared.iloc[: i + 1]
            candle = history.iloc[-1].to_dict()

            still_open = []
            for position in open_positions:
                managed = self.trade_manager.manage(position, candle, self.strategy, i)
                hit, exit_price, reason = self.trade_manager.hit_exit(managed, candle, self.strategy)
                if hit:
                    closed = self.trade_manager.close_position(managed, candle, exit_price, reason, self.strategy)
                    trades.append(closed)
                    self.risk.update_balance(closed["profit"])
                    if hasattr(self.risk, "record_trade_outcome"):
                        self.risk.record_trade_outcome(closed, candle["timestamp"])
                else:
                    still_open.append(managed)
            open_positions = still_open

            signal_data = self.strategy.generate_signal(history)
            if isinstance(signal_data, dict):
                signal = signal_data["signal"]
                signal_strength = signal_data.get("strength", 100)
                entry_reasons = signal_data.get("reasons", [])
                rejections = signal_data.get("rejections", [])
                base_direction = signal_data.get("base_direction", "HOLD")
            else:
                signal = signal_data
                signal_strength = 100
                entry_reasons = []
                rejections = []
                base_direction = "HOLD"

            # Record strategy-level rejections
            if signal == "HOLD" and rejections:
                rejected_signals.append({
                    "timestamp": str(candle["timestamp"]),
                    "signal": base_direction,
                    "rejection_reasons": rejections
                })

            if signal in {"BUY", "SELL"}:
                risk_allowed = self.risk.can_open(open_positions, candle["timestamp"])
                cooldown_allowed = self._entry_gate(signal, last_signal, i, last_entry_index)

                if not risk_allowed or not cooldown_allowed:
                    reasons = []
                    if not risk_allowed:
                        brake = int(self.risk.strategy_params.get("consecutive_loss_brake", 0))
                        if brake > 0 and self.risk.consecutive_losses >= brake:
                            reasons.append("consecutive_loss_brake")
                        elif self.risk.daily_losses_blocked:
                            reasons.append("daily_max_loss_brake")
                        else:
                            reasons.append("max_parallel_positions")
                    if not cooldown_allowed:
                        reasons.append("cooldown_block" if i - last_entry_index < int(self.strategy.params.get("entry_cooldown_candles", 0)) else "not_fresh_signal")

                    rejected_signals.append({
                        "timestamp": str(candle["timestamp"]),
                        "signal": signal,
                        "rejection_reasons": reasons
                    })

                if risk_allowed and cooldown_allowed:
                    atr_val = candle.get("atr", 0) or 0
                    if atr_val > 0:
                        self.event_bus.emit(f"{signal} SIGNAL DETECTED | Strength: {signal_strength}")
                        spread = float(self.strategy.params.get("spread", 0.0))
                        simulated_entry = candle["close"]
                        if signal == "BUY":
                            simulated_entry += spread
                        elif signal == "SELL":
                            simulated_entry -= spread

                        sl, _ = self.strategy.calculate_sl_tp(simulated_entry, atr_val, signal)
                        qty = self.risk.position_size(simulated_entry, sl)
                        if qty > 0:
                            self.event_bus.emit("RISK CHECK PASSED")
                            open_positions.append(self.execution.open_position(
                                self.strategy, signal, candle, qty,
                                signal_strength=signal_strength,
                                entry_reasons=entry_reasons
                            ))
                            last_entry_index = i
                        else:
                            rejected_signals.append({
                                "timestamp": str(candle["timestamp"]),
                                "signal": signal,
                                "rejection_reasons": ["zero_position_size"]
                            })
                    else:
                        self.event_bus.emit(f"⚠ {signal} SIGNAL IGNORED: ATR invalid")
                        rejected_signals.append({
                            "timestamp": str(candle["timestamp"]),
                            "signal": signal,
                            "rejection_reasons": ["atr_invalid"]
                        })
            last_signal = signal

            unrealized = sum(self._unrealized(position, candle["close"], float(self.strategy.params.get("spread", 0.0))) for position in open_positions)
            equity_rows.append({"timestamp": candle["timestamp"], "equity": self.risk.balance + unrealized})

        last_candle = prepared.iloc[-1].to_dict()
        for position in open_positions:
            closed = self.trade_manager.close_position(position, last_candle, last_candle["close"], "end_of_backtest", self.strategy)
            trades.append(closed)
            self.risk.update_balance(closed["profit"])

        # Post-process trades to flag outliers
        import numpy as np
        profits = [t["profit"] for t in trades]
        if len(profits) > 2:
            std_dev = float(np.std(profits))
            mean_profit = float(np.mean(profits))
            for t in trades:
                entry_atr = t.get("atr", 0.0) or 0.0
                price_move = abs(t["exit_price"] - t["entry_price"])
                is_outlier_profit = abs(t["profit"] - mean_profit) > 3 * std_dev if std_dev > 0 else False
                is_outlier_size = price_move > 3 * entry_atr if entry_atr > 0 else False
                t["outlier_flag"] = 1 if (is_outlier_profit or is_outlier_size) else 0
        else:
            for t in trades:
                t["outlier_flag"] = 0

        equity_curve = pd.DataFrame(equity_rows)
        if equity_curve.empty:
            equity_curve = pd.DataFrame([{"timestamp": prepared.iloc[-1]["timestamp"], "equity": self.starting_balance}])
        metrics = calculate_metrics(trades, equity_curve, self.starting_balance)
        self.event_bus.emit("BACKTEST FINISHED")
        return {
            "data": prepared,
            "trades": trades,
            "equity_curve": equity_curve,
            "metrics": metrics,
            "events": self.event_bus.latest(),
            "rejected_signals": rejected_signals
        }

    def _unrealized(self, position: dict, price: float, spread: float = 0.0) -> float:
        side = 1 if position["direction"] == "BUY" else -1
        # When closing a position:
        # BUY close is at Bid (price)
        # SELL close is at Ask (price + spread)
        exit_price = price if position["direction"] == "BUY" else (price + spread)
        return position["qty"] * (exit_price - position["entry_price"]) * side + position.get("realized_profit", 0.0)

    def _entry_gate(self, signal: str, last_signal: str, index: int, last_entry_index: int) -> bool:
        cooldown = int(self.strategy.params.get("entry_cooldown_candles", 0))
        if index - last_entry_index < cooldown:
            return False
        if self.strategy.params.get("fresh_signal_only", True):
            return signal != last_signal
        return True
