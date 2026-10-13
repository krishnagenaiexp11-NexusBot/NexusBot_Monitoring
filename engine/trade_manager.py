from copy import deepcopy


class TradeManager:
    def __init__(self, event_bus=None):
        self.event_bus = event_bus

    def manage(self, position: dict, candle: dict, strategy, index: int) -> dict:
        updated = deepcopy(position)
        atr = candle.get("atr", 0) or 0
        price = candle["close"]
        direction = updated["direction"]
        side = 1 if direction == "BUY" else -1
        move = (price - updated["entry_price"]) * side

        if atr <= 0:
            self._emit("⚠ ATR invalid, skipping position management")
            return updated

        # Breakeven adjustment
        if not updated.get("breakeven_done") and move >= strategy.params["breakeven_atr"] * atr:
            updated["sl"] = updated["entry_price"]
            updated["breakeven_done"] = True
            updated["sl_type"] = "breakeven"
            self._emit("BREAKEVEN MOVED")

        # Trailing stop adjustment
        if move >= strategy.params["trailing_start_atr"] * atr:
            trail_sl = price - side * strategy.params["trailing_step_atr"] * atr
            if (direction == "BUY" and trail_sl > updated["sl"]) or (direction == "SELL" and trail_sl < updated["sl"]):
                updated["sl"] = trail_sl
                updated["sl_type"] = "trailing_stop"
                self._emit("TRAILING STOP UPDATED")

        progress = self._tp_progress(updated, price)
        if strategy.params.get("partial_close_enabled", True) and not updated.get("partial_closed") and progress >= strategy.params["partial_close_progress"]:
            close_qty = updated["qty"] * strategy.params["partial_close_pct"]
            realized = close_qty * move
            updated["qty"] -= close_qty
            updated["realized_profit"] = updated.get("realized_profit", 0.0) + realized
            updated["partial_closed"] = True
            self._emit("PARTIAL CLOSE EXECUTED")

        if strategy.should_exit(updated, candle):
            updated["force_exit"] = True
            updated["exit_reason"] = "strategy_exit"

        if strategy.monitor_and_roll(updated, candle):
            updated["force_exit"] = True
            updated["exit_reason"] = "monitor_and_roll"
            updated["roll_signal"] = direction
            self._emit("MONITOR AND ROLL EXIT")

        return updated

    def hit_exit(self, position: dict, candle: dict, strategy=None) -> tuple[bool, float | None, str | None]:
        spread = float(strategy.params.get("spread", 0.0)) if strategy else 0.0
        
        if position.get("force_exit"):
            exit_price = candle["close"] if position["direction"] == "BUY" else (candle["close"] + spread)
            return True, exit_price, position.get("exit_reason", "strategy_exit")
            
        if position["direction"] == "BUY":
            if candle["low"] <= position["sl"]:
                return True, position["sl"], position.get("sl_type", "stop_loss")
            if candle["high"] >= position["tp"]:
                return True, position["tp"], "take_profit"
        else:
            # SELL position checks are based on Ask price (Bid candle + spread)
            if candle["high"] + spread >= position["sl"]:
                return True, position["sl"], position.get("sl_type", "stop_loss")
            if candle["low"] + spread <= position["tp"]:
                return True, position["tp"], "take_profit"
                
        return False, None, None

    def close_position(self, position: dict, candle: dict, exit_price: float, reason: str, strategy=None) -> dict:
        side = 1 if position["direction"] == "BUY" else -1
        gross_profit = position.get("realized_profit", 0.0) + position["qty"] * (exit_price - position["entry_price"]) * side
        
        # Commission calculation
        commission_per_unit = float(strategy.params.get("commission_per_unit", 0.0)) if strategy else 0.0
        commission = position["qty"] * commission_per_unit
        profit = gross_profit - commission
        
        # Trade duration calculation
        import pandas as pd
        duration_min = 0.0
        try:
            entry_dt = pd.to_datetime(position["entry_time"])
            exit_dt = pd.to_datetime(candle["timestamp"])
            duration_min = float((exit_dt - entry_dt).total_seconds() / 60.0)
        except Exception:
            pass

        closed = deepcopy(position)
        closed.update({
            "status": "CLOSED",
            "exit_time": candle["timestamp"],
            "exit_price": exit_price,
            "profit": profit,
            "commission": commission,
            "exit_reason": reason,
            "trade_duration_minutes": duration_min,
        })
        self._emit(f"POSITION CLOSED: {reason.upper()} | P/L {profit:.2f} (Comm: {commission:.2f})")
        return closed

    def _tp_progress(self, position: dict, price: float) -> float:
        target = abs(position["tp"] - position["entry_price"])
        if target <= 0:
            return 0.0
        side = 1 if position["direction"] == "BUY" else -1
        return max((price - position["entry_price"]) * side / target, 0.0)

    def _emit(self, message: str) -> None:
        if self.event_bus:
            self.event_bus.emit(message)
