"""
deployment/strategy_memory.py
Strategy memory tracking systems mapping recent outcomes, cooldowns, and decay metrics.
"""
import time
from typing import Dict, Any


class StrategyMemorySystem:
    """
    Manages deterministic feedback loops per strategy.
    Strategies query this to adjust their fit score based on recent performance.
    """

    def __init__(self):
        self.memory: Dict[str, Dict[str, Any]] = {}

    def _get_or_create(self, strategy_name: str) -> Dict[str, Any]:
        if strategy_name not in self.memory:
            self.memory[strategy_name] = {
                "recent_losses": 0,
                "recent_wins": 0,
                "false_breakouts": 0,
                "cooldown_until": 0.0,
                "consecutive_losses": 0,
                "suppression_count": 0,
            }
        return self.memory[strategy_name]

    def record_loss(self, strategy_name: str) -> None:
        """Records a trade failure."""
        mem = self._get_or_create(strategy_name)
        mem["recent_losses"] += 1
        mem["consecutive_losses"] += 1
        mem["recent_wins"] = 0
        
        # Trigger cooldown on 2 consecutive losses
        if mem["consecutive_losses"] >= 2:
            mem["cooldown_until"] = time.time() + 300.0  # 5 minutes cooldown

    def record_win(self, strategy_name: str) -> None:
        """Records a trade success."""
        mem = self._get_or_create(strategy_name)
        mem["recent_wins"] += 1
        mem["consecutive_losses"] = 0

    def record_false_breakout(self, strategy_name: str) -> None:
        """Records a breakout failure."""
        mem = self._get_or_create(strategy_name)
        mem["false_breakouts"] += 1

    def record_suppression(self, strategy_name: str) -> None:
        """Records a strategy signal suppression."""
        mem = self._get_or_create(strategy_name)
        mem["suppression_count"] += 1

    def get_confidence_decay(self, strategy_name: str) -> float:
        """
        Calculates confidence score deduction (penalty) based on memory metrics.
        """
        if strategy_name not in self.memory:
            return 0.0
            
        mem = self.memory[strategy_name]
        
        # Check cooldown
        if time.time() < mem["cooldown_until"]:
            return 30.0  # Heavy penalty during cooldown
            
        # Deduct based on recent losses and false breakouts
        loss_penalty = mem["recent_losses"] * 8.0
        breakout_penalty = mem["false_breakouts"] * 5.0
        suppress_penalty = min(mem["suppression_count"] * 2.0, 10.0)
        
        return min(loss_penalty + breakout_penalty + suppress_penalty, 50.0)
        
    def check_cooldown(self, strategy_name: str) -> bool:
        """Returns True if the strategy is currently in cooldown."""
        if strategy_name not in self.memory:
            return False
        return time.time() < self.memory[strategy_name]["cooldown_until"]
