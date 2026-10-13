"""
deployment/deployment_governor.py
Deployment Governor regulating capital scaling, exposure limits, and preservation overrides.
"""
from typing import Dict, Any


class DeploymentGovernor:
    """
    Supervises risk scaling, concurrent deployment capacity, and capital protection thresholds.
    """

    def __init__(self, max_concurrent: int = 2, max_drawdown_limit: float = 5.0):
        self.max_concurrent = max_concurrent
        self.max_drawdown_limit = max_drawdown_limit

    def evaluate_deployment(
        self,
        active_positions_count: int,
        daily_drawdown_pct: float,
        stress_level: str,
        confidence: float,
        session: str,
        base_risk_per_trade: float = 0.5
    ) -> Dict[str, Any]:
        """
        Determines execution permissions and risk scaling factor.
        """
        deployment_permitted = True
        reason = "All checks passed"
        risk_scaling = 1.0

        # 1. Capital Preservation check
        # If drawdown exceeds 3%, active capital preservation mode: cut size by 50%
        capital_preservation = False
        if daily_drawdown_pct >= 3.0:
            capital_preservation = True
            risk_scaling *= 0.5
            reason = "Capital Preservation Mode active (drawdown >= 3%)"

        # 2. Maximum concurrent trades
        if active_positions_count >= self.max_concurrent:
            deployment_permitted = False
            reason = "Max concurrent deployments reached"
            return {
                "deployment_permitted": False,
                "reason": reason,
                "risk_scaling": 0.0,
                "capital_preservation": capital_preservation
            }

        # 3. Stress scaling
        if stress_level == "EXTREME":
            deployment_permitted = False
            reason = "Extreme market stress lockout"
            risk_scaling = 0.0
        elif stress_level == "HIGH":
            risk_scaling *= 0.5
            if not capital_preservation:
                reason = "High stress risk reduction"

        # 4. Session risk restrictions
        # Limit Asian session breakouts
        if session == "ASIAN" and confidence < 65.0:
            deployment_permitted = False
            reason = "Asian session requires confidence >= 65%"

        # Final risk size
        final_risk = base_risk_per_trade * risk_scaling

        return {
            "deployment_permitted": deployment_permitted,
            "reason": reason,
            "risk_scaling": float(risk_scaling),
            "final_risk_percent": float(final_risk),
            "capital_preservation": capital_preservation
        }
