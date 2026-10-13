"""
storage/decision_logger.py
Decision Logging Engine for NexusBot V3.

Persists regime classification, strategy eligibility, tournament standings,
and execution candidates to results/regime_logs/ for observability and replay.
"""
import os
import json
from datetime import datetime


class DecisionLogger:
    """
    Handles persisting quantitative analysis states and tournament decisions
    to local files for auditability and historical replay.
    """

    @staticmethod
    def log_decision(symbol: str, timeframe: str, ctx) -> str:
        """
        Extracts all analysis parameters from the OrchestrationContext and
        writes a JSON log payload to results/regime_logs/.
        """
        os.makedirs("results/regime_logs", exist_ok=True)
        timestamp = datetime.now().isoformat()

        # Unpack context safely
        h4 = getattr(ctx, "h4_structure", {}) or {}
        h1 = getattr(ctx, "h1_structure", {}) or {}
        session = getattr(ctx, "session_context", {}) or {}
        readiness = getattr(ctx, "execution_readiness", {}) or {}
        m15 = getattr(ctx, "m15_execution", {}) or {}
        m5 = getattr(ctx, "m5_precision", {}) or {}
        risk = getattr(ctx, "institutional_risk", {}) or {}

        # Resolve market state and regime flags
        market_state = h1.get("macro_regime", "RANGING")
        regime_flags = [market_state]
        if session.get("session_liquidity") == "HIGH":
            regime_flags.append("SESSION_VOLATILITY")
        if h4.get("macro_direction") != "NEUTRAL":
            regime_flags.append("TRENDING")

        payload = {
            "timestamp": timestamp,
            "symbol": symbol,
            "timeframe": timeframe,
            "market_state": market_state,
            "regime_flags": list(set(regime_flags)),
            "volatility_state": {
                "volatility_state": h1.get("volatility_state", "NORMAL"),
                "atr_ratio": h1.get("_atr_ratio", 1.0)
            },
            "liquidity_state": {
                "session_liquidity": session.get("session_liquidity", "MEDIUM"),
                "is_overlap": session.get("is_overlap", False)
            },
            "structure_state": {
                "macro_direction": h4.get("macro_direction", "NEUTRAL"),
                "trend_persistence": h4.get("trend_persistence", 0.0) or h1.get("trend_persistence", 0.0)
            },
            "eligibility": {
                "eligible": [],
                "rejected": {}
            },
            "tournament": {
                "winner": "None",
                "market_fit_score": 0.0,
                "ranking": []
            },
            "candidates": []
        }

        # Resolve strategy eligibility and reasons
        from engine.strategy_registry import AVAILABLE_STRATEGIES
        for s in AVAILABLE_STRATEGIES:
            name = s.get_strategy_name()
            try:
                if s.validate_context(ctx):
                    payload["eligibility"]["eligible"].append(name)
                    cand = s.build_execution_candidate(ctx)
                    if cand:
                        payload["candidates"].append(cand)
                else:
                    reason = "Context parameters did not meet eligibility filters"
                    # Tailor specific reasons based on current indicators
                    if name == "Momentum Continuation":
                        if h4.get("macro_direction", "NEUTRAL") == "NEUTRAL":
                            reason = "Neutral macro trend direction"
                        elif float(h4.get("trend_persistence", 0.0) or h1.get("trend_persistence", 0.0)) < 0.6:
                            reason = "Weak trend persistence"
                    elif name == "Compression Breakout":
                        if h1.get("volatility_state") == "HIGH":
                            reason = "Volatility already expanded (HIGH state)"
                    elif name == "Liquidity Sweep Reversal":
                        if float(h4.get("macro_strength", 0.0)) >= 35.0:
                            reason = "Continuation trend too strong for reversals"
                    elif name == "Session Breakout":
                        if session.get("session_liquidity", "MEDIUM") == "LOW":
                            reason = "Dead session hours / Low liquidity"
                    elif name == "Structure Shift":
                        if h4.get("macro_direction", "NEUTRAL") == "NEUTRAL":
                            reason = "No structural break or shift detected"
                    elif name == "Mean Reversion":
                        if h1.get("macro_regime") == "TRENDING":
                            reason = "Trending regime active; cannot reversion trade"
                    
                    payload["eligibility"]["rejected"][name] = reason
            except Exception as e:
                payload["eligibility"]["rejected"][name] = f"Validation Error: {e}"

        # Tournament logging
        results = getattr(ctx, "tournament_results", [])
        if results:
            from engine.strategy_tournament import StrategyTournamentEngine
            payload["tournament"]["ranking"] = StrategyTournamentEngine.strip_internal_fields(results)
            winner = results[0]
            payload["tournament"]["winner"] = winner.get("strategy", "None")
            payload["tournament"]["market_fit_score"] = winner.get("market_fit_score", 0.0)

        # Output JSON
        filename = f"results/regime_logs/log_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
        with open(filename, "w") as f:
            json.dump(payload, f, indent=4)
        return filename
