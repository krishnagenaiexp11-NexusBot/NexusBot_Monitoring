"""
deployment/market_stress.py
Market Stress Index modeling spread dynamics, volatility expansions, and signal contradictions.
"""
from typing import Dict, Any


class MarketStressIndex:
    """
    Computes overall market stress to adjust risk profiles and block execution during extreme events.
    """

    @staticmethod
    def calculate_stress(
        volatility_ratio: float,
        spread_pts: float,
        max_spread: float,
        conflict_count: int = 0,
        failed_breakouts: int = 0
    ) -> Dict[str, Any]:
        """
        Computes the stress score and level.
        """
        stress_score = 0.0
        
        # Volatility factor
        stress_score += max(0.0, volatility_ratio - 1.0) * 30.0
        
        # Spread factor
        spread_ratio = spread_pts / max(1e-9, max_spread)
        stress_score += spread_ratio * 30.0
        
        # Contradictions / Conflict factors
        stress_score += conflict_count * 10.0
        
        # Failed breakouts
        stress_score += failed_breakouts * 15.0
        
        # Cap score
        stress_score = max(0.0, min(100.0, stress_score))
        
        # Resolve level
        if stress_score >= 75.0:
            level = "EXTREME"
        elif stress_score >= 50.0:
            level = "HIGH"
        elif stress_score >= 25.0:
            level = "MODERATE"
        else:
            level = "LOW"
            
        # Impact flags
        scalping_eligible = level in ("LOW", "MODERATE")
        deployment_allowed = level != "EXTREME"
        
        # Sizing multiplier
        if level == "LOW":
            risk_multiplier = 1.0
        elif level == "MODERATE":
            risk_multiplier = 0.8
        elif level == "HIGH":
            risk_multiplier = 0.5
        else: # EXTREME
            risk_multiplier = 0.0
            
        return {
            "stress_score": float(stress_score),
            "stress_level": level,
            "scalping_eligible": scalping_eligible,
            "deployment_allowed": deployment_allowed,
            "risk_multiplier": float(risk_multiplier)
        }
