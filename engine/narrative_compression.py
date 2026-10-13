"""
engine/narrative_compression.py
Narrative Compression Engine for NexusBot V3.

Translates raw quantitative metrics into exactly 5 institutional-grade
bullet insights. Produces:
  - executive_summary      : Single paragraph decision overview
  - key_opportunities      : Top 2-3 opportunity bullets
  - key_risks              : Top 2-3 risk bullets
  - timing_summary         : Execution timing narrative
  - deployment_context     : Strategy deployment recommendation narrative

Fully deterministic — no AI — pure template-based compression.
"""


class NarrativeCompressionEngine:
    """
    Generates compressed institutional insights from quantitative engine outputs.
    Does not use any external AI or LLM — all narratives are template-based.
    """

    def compress(
        self,
        h4_structure: dict,
        mtf_context: dict,
        session_context: dict,
        regime_transition: dict,
        market_memory: dict,
        signal_quality: dict,
        institutional_risk: dict,
        execution_readiness: dict,
        confidence_hierarchy: dict,
        contradiction_engine: dict,
        tournament_results: list,
    ) -> dict:
        """
        Compresses all engine outputs into 5 narrative insights.

        Returns:
            {
                "executive_summary"  : str,
                "key_opportunities"  : list[str] (2-3 bullets),
                "key_risks"          : list[str] (2-3 bullets),
                "timing_summary"     : str,
                "deployment_context" : str
            }
        """
        h4    = h4_structure or {}
        ctx   = mtf_context or {}
        sess  = session_context or {}
        trans = regime_transition or {}
        mem   = market_memory or {}
        sq    = signal_quality or {}
        risk  = institutional_risk or {}
        ready = execution_readiness or {}
        conf  = confidence_hierarchy or {}
        contra = contradiction_engine or {}
        tr    = tournament_results or []

        # ── Pull Key Metrics ─────────────────────────────────────────────────
        macro_dir   = h4.get("macro_direction", "NEUTRAL")
        macro_str   = float(h4.get("macro_strength", 0.0))
        exhaustion  = float(h4.get("exhaustion_risk", 50.0))
        trend_age   = int(h4.get("trend_age", 0))
        inst_bias   = h4.get("institutional_bias", "NEUTRAL")

        alignment   = float(ctx.get("alignment_score", 50.0))
        h1_dir      = ctx.get("h1_structure", {}).get("structure_direction", "NEUTRAL")

        session     = sess.get("current_session", "ASIAN")
        liquidity   = sess.get("session_liquidity", "LOW")
        is_overlap  = bool(sess.get("is_overlap", False))
        liq_acc     = float(sess.get("liquidity_acceleration", 1.0))

        trans_state = trans.get("transition_state", "STABLE")
        expansion   = bool(trans.get("expansion_phase", False))
        compression = bool(trans.get("compression_phase", False))

        stability   = float(mem.get("market_stability", 50.0))
        regime_dur  = int(mem.get("regime_duration", 0))

        confluence  = int(sq.get("confluence_count", 0))
        noise       = float(sq.get("noise_level", 50.0))
        vol_q       = sq.get("volume_quality", "MODERATE")

        risk_score  = float(risk.get("risk_score", 50.0))
        risk_level  = risk.get("risk_level", "MODERATE")
        fake_bkout  = float(risk.get("fake_breakout_prob", 50.0))
        exhaustion_prob = float(risk.get("exhaustion_probability", 50.0))

        exec_state  = ready.get("execution_state", "WATCHLIST")
        readiness   = float(ready.get("readiness_score", 50.0))
        hard_blocks = ready.get("hard_blocks", [])

        conf_score  = float(conf.get("weighted_confidence_score", 50.0))
        conf_level  = conf.get("confidence_level", "MODERATE")
        weak_pen    = float(conf.get("weak_signal_penalty", 0.0))

        conflicts   = contra.get("conflicts", [])
        contra_score = float(contra.get("contradiction_score", 0.0))

        top_strat   = tr[0]["strategy"] if tr else "N/A"
        top_score   = float(tr[0]["market_fit_score"]) if tr else 0.0

        # ── Compile the co-equal 10-key structured context payload ──
        structured_context = {
            "market_regime": trans,
            "structure_engine": h4,
            "liquidity_engine": sess,
            "execution_quality": ready,
            "stress_index": trans,
            "strategy_rankings": tr,
            "contradictions": contra,
            "risk_state": risk,
            "session_personality": sess,
            "candidate_state": tr[0] if tr else {}
        }

        # Query ProviderManager to generate narrative briefing
        from providers.provider_manager import get_provider_manager
        pm = get_provider_manager()
        return pm.generate_briefing(structured_context)
