import math


class RiskManager:
    def __init__(self, balance: float = 10_000.0, risk_percent: float = 1.0, max_parallel_positions: int = 3, strategy_params: dict | None = None):
        self.balance = float(balance)
        self.risk_percent = float(risk_percent)
        self.max_parallel_positions = int(max_parallel_positions)
        self.strategy_params = strategy_params or {}

        # Risk protection state
        self.consecutive_losses = 0
        self.current_day = None
        self.day_start_balance = float(balance)
        self.daily_losses_blocked = False

    def position_size(self, entry: float, stop_loss: float) -> float:
        risk_amount = self.balance * (self.risk_percent / 100)
        risk_per_unit = abs(entry - stop_loss)
        if risk_amount <= 0 or risk_per_unit <= 0:
            return 0.0
        size = math.floor((risk_amount / risk_per_unit) * 1000) / 1000
        return max(size, 0.0)

    def can_open(self, open_positions: list[dict], timestamp=None) -> bool:
        if len(open_positions) >= self.max_parallel_positions:
            return False

        # Consecutive loss brake
        loss_brake = int(self.strategy_params.get("consecutive_loss_brake", 0))
        if loss_brake > 0 and self.consecutive_losses >= loss_brake:
            return False

        # Daily max loss limit
        if timestamp and self.strategy_params.get("daily_max_loss_pct", 0.0) > 0.0:
            import pandas as pd
            try:
                dt = pd.to_datetime(timestamp)
                day_str = dt.strftime("%Y-%m-%d")
                if self.current_day != day_str:
                    self.current_day = day_str
                    self.day_start_balance = self.balance
                    self.daily_losses_blocked = False

                daily_loss_pct = (self.day_start_balance - self.balance) / self.day_start_balance * 100
                if daily_loss_pct >= float(self.strategy_params.get("daily_max_loss_pct", 0.0)):
                    self.daily_losses_blocked = True
            except Exception:
                pass

            if self.daily_losses_blocked:
                return False

        return True

    def record_trade_outcome(self, closed_trade: dict, timestamp=None) -> None:
        profit = closed_trade.get("profit", 0.0)
        if profit < 0:
            self.consecutive_losses += 1
        elif profit > 0:
            self.consecutive_losses = 0

        # Update daily max loss check immediately upon trade closure
        if timestamp and self.strategy_params.get("daily_max_loss_pct", 0.0) > 0.0:
            import pandas as pd
            try:
                dt = pd.to_datetime(timestamp)
                day_str = dt.strftime("%Y-%m-%d")
                if self.current_day != day_str:
                    self.current_day = day_str
                    self.day_start_balance = self.balance
                    self.daily_losses_blocked = False

                daily_loss_pct = (self.day_start_balance - self.balance) / self.day_start_balance * 100
                if daily_loss_pct >= float(self.strategy_params.get("daily_max_loss_pct", 0.0)):
                    self.daily_losses_blocked = True
            except Exception:
                pass

    def update_balance(self, profit: float) -> None:
        self.balance += float(profit)
