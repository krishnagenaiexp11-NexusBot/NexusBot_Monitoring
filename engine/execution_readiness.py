"""
engine/execution_readiness.py
Execution Readiness Engine for NexusBot V3.

Combines M5 precision timing, signal quality, execution clock, H4 macro
structure, and session context to compute a unified readiness score and
execution state (READY / WATCHLIST / AVOID).

Fully deterministic — no AI.
"""
import numpy as np


class ExecutionReadinessEngine:
    """
    Computes execution readiness by synthesizing all Phase 2 and Phase 3 signals.

    Inputs are the output dicts from each engine. This is the final
    pre-tournament gate that determines if conditions are valid for strategy
    ranking to proceed.
    """

    # Weight table for readiness calculation
    WEIGHTS = {
        "h4_structure":    0.25,   # Macro foundation — highest weight
        "session_context": 0.20,   # Liquidity is critical for execution
        "signal_quality":  0.25,   # Signal cleanliness
        "m5_timing":       0.15,   # Micro precision
        "execution_clock": 0.15,   # Time-based window quality
    }

    def compute(
        self,
        h4_structure: dict,
        session_context: dict,
        signal_quality: dict,
        m5_execution: dict,
        execution_clock: dict,
    ) -> dict:
        """
        Computes unified execution readiness.

        Args:
            h4_structure     : Output from H4StructureEngine.analyze()
            session_context  : Output from SessionContextEngine.analyze()
            signal_quality   : Output from SignalQualityEngine.analyze()
            m5_execution     : Output from M5ExecutionEngine.analyze()
            execution_clock  : Output from ExecutionClock.analyze()

        Returns:
            {
                "readiness_score" : float (0-100),
                "execution_state" : "READY | WATCHLIST | AVOID",
                "readiness_gates" : list[str]  (reasons for current state),
                "hard_blocks"     : list[str]  (critical blockers)
            }
        """
        gates = []
        hard_blocks = []

        # ── Layer 1 — H4 Macro Foundation ──────────────────────────────────────
        macro_direction = h4_structure.get("macro_direction", "NEUTRAL")
        macro_strength = float(h4_structure.get("macro_strength", 0.0))
        exhaustion_risk = float(h4_structure.get("exhaustion_risk", 50.0))

        h4_score = 0.0
        if macro_direction != "NEUTRAL":
            h4_score += 40.0
        if macro_strength >= 25.0:
            h4_score += 30.0
        elif macro_strength >= 18.0:
            h4_score += 15.0
        if exhaustion_risk < 60.0:
            h4_score += 30.0
        elif exhaustion_risk >= 80.0:
            hard_blocks.append(f"⚠ H4 Exhaustion Risk: {exhaustion_risk:.0f}% — setup is late-cycle")

        h4_score = float(np.clip(h4_score, 0.0, 100.0))

        if macro_direction == "NEUTRAL":
            gates.append("H4: Neutral macro structure — directional bias missing")

        # ── Layer 2 — Session Liquidity ─────────────────────────────────────────
        session_liquidity = session_context.get("session_liquidity", "LOW")
        is_overlap = session_context.get("is_overlap", False)
        liquidity_acc = float(session_context.get("liquidity_acceleration", 1.0))
        current_session = session_context.get("current_session", "ASIAN")

        session_score = 0.0
        if session_liquidity == "HIGH":
            session_score = 90.0
        elif session_liquidity == "MEDIUM":
            session_score = 60.0
        else:
            session_score = 20.0
            gates.append(f"Session: Low liquidity ({current_session}) — avoid precision entries")

        if is_overlap:
            session_score = min(session_score + 10.0, 100.0)

        if liquidity_acc >= 1.2:
            session_score = min(session_score + 5.0, 100.0)

        # ── Layer 3 — Signal Quality ────────────────────────────────────────────
        signal_q_score = float(signal_quality.get("signal_quality_score", 0.0))
        rsi_div = signal_quality.get("rsi_divergence", False)
        confluence = int(signal_quality.get("confluence_count", 0))

        if rsi_div:
            hard_blocks.append("⚡ RSI Divergence detected — price and momentum disagree")
        if confluence < 2:
            gates.append(f"Signal: Only {confluence}/6 indicators aligned — weak confluence")

        # ── Layer 4 — M5 Timing ─────────────────────────────────────────────────
        m5_score = float(m5_execution.get("m5_timing_score", 0.0))
        momentum_aligned = m5_execution.get("momentum_aligned", False)

        if not momentum_aligned:
            gates.append("M5: Micro momentum not aligned with H1 direction")

        # ── Layer 5 — Execution Clock ────────────────────────────────────────────
        clock_score = float(execution_clock.get("timing_score", 0.0))
        is_premium = execution_clock.get("is_premium_window", False)
        exec_timing = execution_clock.get("execution_timing", "SUBOPTIMAL")

        if exec_timing == "SUBOPTIMAL":
            gates.append("Clock: Outside premium session window — increased slippage risk")

        # ── Weighted Readiness Score ─────────────────────────────────────────────
        readiness_score = (
            h4_score   * self.WEIGHTS["h4_structure"]    +
            session_score * self.WEIGHTS["session_context"] +
            signal_q_score * self.WEIGHTS["signal_quality"]  +
            m5_score   * self.WEIGHTS["m5_timing"]       +
            clock_score * self.WEIGHTS["execution_clock"]
        )

        # Hard block penalty
        readiness_score -= len(hard_blocks) * 15.0
        readiness_score = float(np.clip(readiness_score, 0.0, 100.0))

        # ── Execution State Classification ───────────────────────────────────────
        if len(hard_blocks) >= 2 or readiness_score < 30.0:
            execution_state = "AVOID"
        elif readiness_score >= 60.0 and len(hard_blocks) == 0:
            execution_state = "READY"
        else:
            execution_state = "WATCHLIST"

        return {
            "readiness_score": round(readiness_score, 1),
            "execution_state": execution_state,
            "readiness_gates": gates,
            "hard_blocks": hard_blocks,
        }
