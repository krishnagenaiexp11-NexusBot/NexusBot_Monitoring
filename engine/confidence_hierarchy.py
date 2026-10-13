"""
engine/confidence_hierarchy.py
Confidence Hierarchy Engine for NexusBot V3.

Enforces structural weights on timeframe signals, preventing lower-timeframe
noise from overriding macro structure. Produces a weighted confidence score
and applies weak-signal penalties for noisy / misaligned lower timeframes.

Fully deterministic — no AI.
"""
import numpy as np


class ConfidenceHierarchyEngine:
    """
    Computes a weighted confidence score based on the institutional timeframe trust ladder.

    Weights (from plan):
      H4 Macro Structure     : 1.00
      H1 Context             : 0.90
      Session Liquidity      : 0.85
      M15 Execution          : 0.80
      Candlestick (Signal Q) : 0.65
      M5 Timing              : 0.45
    """

    HIERARCHY_WEIGHTS = {
        "h4":           1.00,
        "h1":           0.90,
        "session":      0.85,
        "m15":          0.80,
        "candlestick":  0.65,
        "m5":           0.45,
    }

    def compute(
        self,
        h4_structure: dict,
        mtf_context: dict,
        session_context: dict,
        signal_quality: dict,
        m5_execution: dict,
    ) -> dict:
        """
        Computes the hierarchically-weighted confidence score.

        Returns:
            {
                "weighted_confidence_score" : float (0-100),
                "weak_signal_penalty"       : float (0-20),
                "layer_scores"              : dict,
                "confidence_level"          : "HIGH | MODERATE | LOW | MINIMAL"
            }
        """
        h4 = h4_structure or {}
        ctx = mtf_context or {}
        sess = session_context or {}
        sq = signal_quality or {}
        m5 = m5_execution or {}

        # ── Layer Scores (normalize each to 0-100) ─────────────────────────────

        # H4: direction present + strength + low exhaustion
        macro_dir = h4.get("macro_direction", "NEUTRAL")
        macro_str = float(h4.get("macro_strength", 0.0))
        exhaustion = float(h4.get("exhaustion_risk", 50.0))
        h4_raw = 0.0
        if macro_dir != "NEUTRAL":
            h4_raw += 40.0
        h4_raw += min(macro_str, 50.0)  # ADX capped contribution
        h4_raw += max(0.0, 50.0 - exhaustion) * 0.2  # exhaustion drag
        h4_score = float(np.clip(h4_raw, 0.0, 100.0))

        # H1: alignment score
        h1_score = float(np.clip(ctx.get("alignment_score", 50.0), 0.0, 100.0))

        # Session: liquidity mapping
        liq = sess.get("session_liquidity", "MEDIUM")
        if liq == "HIGH":
            sess_score = 90.0
        elif liq == "MEDIUM":
            sess_score = 60.0
        else:
            sess_score = 20.0
        if sess.get("is_overlap", False):
            sess_score = min(sess_score + 10.0, 100.0)

        # M15: pullback quality + trigger
        m15_struct = ctx.get("m15_execution", {})
        pq = float(m15_struct.get("pullback_quality", 0.5))
        trigger = bool(m15_struct.get("trigger_ready", False))
        m15_score = pq * 70.0 + (30.0 if trigger else 0.0)
        m15_score = float(np.clip(m15_score, 0.0, 100.0))

        # Candlestick / Signal Quality
        candle_score = float(np.clip(sq.get("signal_quality_score", 50.0), 0.0, 100.0))

        # M5
        m5_score = float(np.clip(m5.get("m5_timing_score", 50.0), 0.0, 100.0))

        layer_scores = {
            "h4_score":      round(h4_score, 1),
            "h1_score":      round(h1_score, 1),
            "session_score": round(sess_score, 1),
            "m15_score":     round(m15_score, 1),
            "candle_score":  round(candle_score, 1),
            "m5_score":      round(m5_score, 1),
        }

        # ── Weighted Confidence ────────────────────────────────────────────────
        W = self.HIERARCHY_WEIGHTS
        total_weight = sum(W.values())

        weighted_sum = (
            h4_score   * W["h4"]          +
            h1_score   * W["h1"]          +
            sess_score * W["session"]      +
            m15_score  * W["m15"]         +
            candle_score * W["candlestick"] +
            m5_score   * W["m5"]
        )

        weighted_confidence_score = float(np.clip(weighted_sum / total_weight, 0.0, 100.0))

        # ── Weak Signal Penalty ────────────────────────────────────────────────
        # Penalty if lower-timeframe signals are weak but higher are strong
        weak_signal_penalty = 0.0
        if h4_score > 60.0 and m5_score < 30.0:
            weak_signal_penalty += 8.0  # H4 strong but M5 noise
        if h1_score > 60.0 and m15_score < 30.0:
            weak_signal_penalty += 7.0  # H1 strong but M15 weak
        if candle_score < 25.0:
            weak_signal_penalty += 5.0  # candlestick confirmation absent
        weak_signal_penalty = float(np.clip(weak_signal_penalty, 0.0, 20.0))

        # Apply penalty
        final_score = float(np.clip(weighted_confidence_score - weak_signal_penalty, 0.0, 100.0))

        # ── Confidence Level ───────────────────────────────────────────────────
        if final_score >= 70.0:
            confidence_level = "HIGH"
        elif final_score >= 50.0:
            confidence_level = "MODERATE"
        elif final_score >= 30.0:
            confidence_level = "LOW"
        else:
            confidence_level = "MINIMAL"

        return {
            "weighted_confidence_score": round(final_score, 1),
            "weak_signal_penalty": round(weak_signal_penalty, 1),
            "layer_scores": layer_scores,
            "confidence_level": confidence_level,
        }
