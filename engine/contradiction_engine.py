"""
engine/contradiction_engine.py
Contradiction Detection Engine for NexusBot V3.

Detects critical structural conflicts across timeframe layers:
- Volatility vs Trend conflicts
- Breakout loading without volume support
- Direction divergence between H4 and M15 RSI
- Session liquidity contraction during high-conviction setups

Outputs a contradiction_score and deployment_penalty.
Fully deterministic — no AI.
"""
import numpy as np


class ContradictionEngine:
    """
    Identifies structural contradictions between signal layers.

    A contradiction occurs when two or more market signals that should
    reinforce each other are actively opposing each other — indicating
    false setups, wash signals, or transitional market noise.
    """

    def analyze(
        self,
        h4_structure: dict,
        session_context: dict,
        signal_quality: dict,
        m5_execution: dict,
        regime_transition: dict,
        mtf_context: dict,
    ) -> dict:
        """
        Detects and scores contradictions across all signal layers.

        Returns:
            {
                "contradiction_score" : float (0-100, higher = more contradictions),
                "deployment_penalty"  : float (0-30, subtracted from readiness),
                "conflicts"           : list[str] (human-readable conflict descriptions),
                "conflict_count"      : int
            }
        """
        conflicts = []
        raw_penalty = 0.0

        h4 = h4_structure or {}
        sess = session_context or {}
        sq = signal_quality or {}
        m5 = m5_execution or {}
        trans = regime_transition or {}
        ctx = mtf_context or {}

        macro_dir = h4.get("macro_direction", "NEUTRAL")
        macro_str = float(h4.get("macro_strength", 0.0))
        exhaustion = float(h4.get("exhaustion_risk", 50.0))
        trend_age  = int(h4.get("trend_age", 0))

        liquidity   = sess.get("session_liquidity", "MEDIUM")
        liq_acc     = float(sess.get("liquidity_acceleration", 1.0))

        noise_level = float(sq.get("noise_level", 50.0))
        rsi_div     = bool(sq.get("rsi_divergence", False))
        vol_quality = sq.get("volume_quality", "MODERATE")
        confluence  = int(sq.get("confluence_count", 0))

        m5_dir      = m5.get("micro_direction", "NEUTRAL")
        mom_aligned = bool(m5.get("momentum_aligned", False))
        vol_confirm = bool(m5.get("volume_confirmation", False))

        expansion_ph   = bool(trans.get("expansion_phase", False))
        compression_ph = bool(trans.get("compression_phase", False))
        breakout_load  = float(trans.get("breakout_loading", 0.0))
        transition_st  = trans.get("transition_state", "STABLE")

        h1_struct = ctx.get("h1_structure", {})
        h1_dir = h1_struct.get("structure_direction", "NEUTRAL")
        alignment_score = float(ctx.get("alignment_score", 50.0))

        # ── C1: Bullish structure + declining momentum ───────────────────────────
        if macro_dir == "BULLISH" and macro_str < 20.0 and exhaustion > 60.0:
            conflicts.append(
                "C1 — BULLISH H4 structure but ADX declining and exhaustion elevated: "
                f"strength={macro_str:.0f}, exhaustion={exhaustion:.0f}%"
            )
            raw_penalty += 12.0

        # ── C2: Breakout loading without volume support ──────────────────────────
        if compression_ph and breakout_load > 50.0 and vol_quality == "WEAK":
            conflicts.append(
                f"C2 — Compression breakout loading ({breakout_load:.0f}%) but volume is WEAK: "
                "potential fake breakout risk"
            )
            raw_penalty += 10.0

        # ── C3: H4 direction opposes H1 direction ───────────────────────────────
        if macro_dir not in ["NEUTRAL"] and h1_dir not in ["NEUTRAL"]:
            if macro_dir != h1_dir:
                conflicts.append(
                    f"C3 — H4 direction ({macro_dir}) conflicts with H1 structure ({h1_dir}): "
                    "cross-timeframe directional split"
                )
                raw_penalty += 15.0

        # ── C4: M5 micro direction opposes H1 ────────────────────────────────────
        if m5_dir != "NEUTRAL" and h1_dir != "NEUTRAL" and m5_dir != h1_dir:
            conflicts.append(
                f"C4 — M5 micro direction ({m5_dir}) opposes H1 macro ({h1_dir}): "
                "counter-trend micro setup"
            )
            raw_penalty += 8.0

        # ── C5: RSI Divergence detected ──────────────────────────────────────────
        if rsi_div:
            conflicts.append(
                "C5 — RSI divergence active: price momentum and RSI disagree — "
                "potential reversal or fakeout"
            )
            raw_penalty += 10.0

        # ── C6: High noise during expansion phase ─────────────────────────────────
        if expansion_ph and noise_level > 70.0:
            conflicts.append(
                f"C6 — Expansion phase active but noise level is high ({noise_level:.0f}/100): "
                "choppy expansion movement"
            )
            raw_penalty += 6.0

        # ── C7: Extreme trend age (late cycle) ────────────────────────────────────
        if trend_age > 30 and macro_dir != "NEUTRAL":
            conflicts.append(
                f"C7 — Trend is {trend_age} candles old ({macro_dir}): "
                "potential late-cycle entry — exhaustion risk elevated"
            )
            raw_penalty += 7.0

        # ── C8: Low liquidity during high-conviction setup ────────────────────────
        if liquidity == "LOW" and alignment_score > 70.0:
            conflicts.append(
                f"C8 — Strong MTF alignment ({alignment_score:.0f}/100) but session liquidity is LOW: "
                "spread inflation risk"
            )
            raw_penalty += 5.0

        # ── C9: Transition state mismatch ─────────────────────────────────────────
        if transition_st == "TREND_EXHAUSTION" and macro_dir != "NEUTRAL" and confluence >= 3:
            conflicts.append(
                "C9 — Regime transition shows TREND_EXHAUSTION but indicators still bullish: "
                "structural top/bottom formation risk"
            )
            raw_penalty += 8.0

        # ── Aggregate Scores ──────────────────────────────────────────────────────
        conflict_count = len(conflicts)
        contradiction_score = float(np.clip(raw_penalty * 3.0, 0.0, 100.0))
        deployment_penalty  = float(np.clip(raw_penalty, 0.0, 30.0))

        return {
            "contradiction_score": round(contradiction_score, 1),
            "deployment_penalty": round(deployment_penalty, 1),
            "conflicts": conflicts,
            "conflict_count": conflict_count,
        }
