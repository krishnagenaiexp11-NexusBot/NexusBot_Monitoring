"""
storage/decision_trace.py
Decision Trace Engine saving complete execution decision reasoning chain details.
"""
import os
import json
from datetime import datetime, timezone
from typing import Dict, Any


class DecisionTraceEngine:
    """
    Saves serializable execution traces mapping raw inputs to final trade actions.
    """

    @staticmethod
    def log_trace(
        symbol: str,
        timeframe: str,
        market_state: Dict[str, Any],
        personality: str,
        stress_level: str,
        rankings: list,
        confidence_model: Dict[str, Any],
        risk_governance: Dict[str, Any],
        permission: bool,
        final_decision: str
    ) -> str:
        """
        Extracts all parameters and writes trace log to results/decision_traces/.
        """
        os.makedirs("results/decision_traces", exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()

        trace_payload = {
            "timestamp": timestamp,
            "symbol": symbol,
            "timeframe": timeframe,
            "market_state": market_state,
            "personality": personality,
            "stress_level": stress_level,
            "tournament_rankings": rankings,
            "confidence_model": confidence_model,
            "risk_governance": risk_governance,
            "deployment_permission": permission,
            "final_decision": final_decision
        }

        filename = f"results/decision_traces/trace_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
        try:
            with open(filename, "w") as f:
                json.dump(trace_payload, f, indent=4)
        except Exception:
            pass
            
        return filename
