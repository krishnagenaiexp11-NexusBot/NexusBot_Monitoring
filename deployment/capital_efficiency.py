"""
deployment/capital_efficiency.py
Capital Efficiency Engine calculating dynamic position sizes and execution grades.
"""
from typing import Dict, Any


class CapitalEfficiencyEngine:
    """
    Computes lot sizes and capital ratings based on multi-factor market and strategy stats.
    """

    @staticmethod
    def calculate_sizing(
        balance: float,
        entry_price: float,
        stop_loss: float,
        confidence: float,
        quality_score: float,
        stress_level: str,
        governor_risk_pct: float
    ) -> Dict[str, Any]:
        """
        Calculates execution lot sizes.
        """
        if stop_loss == 0.0 or entry_price == stop_loss:
            # Fallback to simple sizing if SL is not defined
            raw_lots = 0.01
            rating = "F"
            return {
                "lots": raw_lots,
                "rating": rating,
                "risk_amount_usd": 0.0,
                "reason": "Invalid or missing Stop Loss parameter"
            }

        # Calculate risk amount in cash (USD)
        risk_cash = balance * (governor_risk_pct / 100.0)
        
        # Calculate SL distance
        sl_distance = abs(entry_price - stop_loss)
        
        # Standard FX lot size calculation: lots = risk_amount / sl_distance
        # Let's assume standard broker contract sizes for gold / forex
        # For gold, 1 lot = 100 ounces. 1 USD change on 1 lot = 100 USD risk.
        # For simplicity, we model: lots = risk_cash / (sl_distance * contract_size)
        # Assuming contract size = 100 (standard gold contract size / Gold mapper multiplier)
        contract_size = 100.0
        raw_lots = risk_cash / max(1e-9, sl_distance * contract_size)
        
        # Clamp lots to standard min/max
        lots = max(0.01, min(10.0, raw_lots))
        lots = round(lots, 2)
        
        # Determine capital efficiency rating
        # A: high confidence, low stress, high execution quality
        # B: high quality but moderate stress or lower confidence
        # C: low quality or high stress
        # F: zero risk allowed
        if governor_risk_pct == 0.0 or stress_level == "EXTREME":
            rating = "F"
        elif quality_score >= 80.0 and confidence >= 68.0 and stress_level == "LOW":
            rating = "A"
        elif quality_score >= 60.0 and confidence >= 55.0 and stress_level in ("LOW", "MODERATE"):
            rating = "B"
        else:
            rating = "C"

        return {
            "lots": float(lots),
            "rating": rating,
            "risk_amount_usd": float(risk_cash),
            "sl_distance_points": float(sl_distance),
            "reason": f"Sized for ${risk_cash:.2f} risk over {sl_distance:.2f} SL distance"
        }
