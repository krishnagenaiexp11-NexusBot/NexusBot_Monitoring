"""
deployment/execution_quality.py
Execution Quality Engine evaluating spread, slippage, and microstructure risk profiles.
"""
import random
from typing import Dict, Any


class ExecutionQualityEngine:
    """
    Evaluates execution safety metrics to control deployment permission and sizing.
    """

    @staticmethod
    def evaluate_quality(
        spread: float,
        max_spread: float,
        volatility_ratio: float,
        latency_ms: float = 50.0
    ) -> Dict[str, Any]:
        """
        Computes execution quality parameters.
        """
        # 1. Spread stability check
        spread_ratio = spread / max(1e-9, max_spread)
        
        # 2. Slippage probability
        if spread_ratio > 0.8 or volatility_ratio > 2.0:
            slippage_risk = "HIGH"
            slip_prob = 0.7
        elif spread_ratio > 0.5 or volatility_ratio > 1.3:
            slippage_risk = "MEDIUM"
            slip_prob = 0.3
        else:
            slippage_risk = "LOW"
            slip_prob = 0.05
            
        # 3. Microstructure stability calculation
        # Latency penalty
        latency_penalty = max(0.0, (latency_ms - 100.0) / 10.0) if latency_ms > 100.0 else 0.0
        
        # Score calculation
        quality_score = 100.0 - (spread_ratio * 40.0) - (volatility_ratio * 15.0) - latency_penalty
        quality_score = max(0.0, min(100.0, quality_score))
        
        # Permission logic
        deployment_permission = True
        if spread > max_spread:
            deployment_permission = False
        if quality_score < 40.0:
            deployment_permission = False
            
        # Mock microstructure parameters
        microstructure_state = {
            "absorption_active": volatility_ratio > 1.8,
            "sweep_velocity": "HIGH" if volatility_ratio > 1.5 else "NORMAL",
            "wick_aggression": "HIGH" if volatility_ratio > 2.0 else "NORMAL",
        }
        
        return {
            "execution_quality_score": float(quality_score),
            "slippage_risk": slippage_risk,
            "slippage_probability": float(slip_prob),
            "deployment_permission": deployment_permission,
            "microstructure_state": microstructure_state,
            "execution_stability": float(max(0.0, quality_score - 10.0))
        }
