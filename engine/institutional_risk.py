"""
engine/institutional_risk.py
Institutional Risk Engine for NexusBot V3.

Calculates operational risk parameters:
- Trend exhaustion probability
- Fake breakout probability
- Liquidity vacuum risk
- Structural reversal risk

Outputs a risk_score and risk_level (LOW / MODERATE / HIGH / CRITICAL).
Fully deterministic — no AI.
"""
import numpy as np


class InstitutionalRiskEngine:
    """
    Computes a multi-factor institutional risk assessment.
    Used to co-weight against readiness — high risk can veto setups.
    """

    def analyze(
        self,
        h4_structure: dict,
        session_context: dict,
        signal_quality: dict,
        regime_transition: dict,
        market_memory: dict,
    ) -> dict:
        """
        Computes institutional risk parameters.

        Returns:
            {
                "risk_score"             : float (0-100),
                "risk_level"             : "LOW | MODERATE | HIGH | CRITICAL",
                "exhaustion_probability" : float (0-100),
                "fake_breakout_prob"     : float (0-100),
                "liquidity_vacuum_risk"  : float (0-100),
                "risk_factors"           : list[str]
            }
        """
        h4  = h4_structure or {}
        sess = session_context or {}
        sq   = signal_quality or {}
        trans = regime_transition or {}
        mem  = market_memory or {}

        risk_factors = []
        component_risks = []

        # ── 1. Trend Exhaustion Risk ──────────────────────────────────────────
        exhaustion_risk = float(h4.get("exhaustion_risk", 50.0))
        trend_age       = int(h4.get("trend_age", 0))
        macro_str       = float(h4.get("macro_strength", 0.0))

        # Combine H4 exhaustion with trend age
        age_factor = min(trend_age / 40.0, 1.0) * 30.0   # max +30 for age
        exhaustion_prob = float(np.clip(exhaustion_risk + age_factor - max(0.0, macro_str - 20.0) * 0.3, 5.0, 95.0))

        if exhaustion_prob > 70.0:
            risk_factors.append(
                f"🔴 Trend Exhaustion: {exhaustion_prob:.0f}% probability — "
                f"trend is {trend_age} candles old, ADX={macro_str:.0f}"
            )
        elif exhaustion_prob > 50.0:
            risk_factors.append(
                f"🟡 Trend Fatigue: {exhaustion_prob:.0f}% probability — "
                "late-stage trend characteristics"
            )

        component_risks.append(exhaustion_prob)

        # ── 2. Fake Breakout Probability ────────────────────────────────────────
        compression_ph = bool(trans.get("compression_phase", False))
        breakout_load  = float(trans.get("breakout_loading", 0.0))
        vol_quality    = sq.get("volume_quality", "MODERATE")
        rsi_div        = bool(sq.get("rsi_divergence", False))

        fake_bkout_prob = 15.0   # base
        if compression_ph and breakout_load > 40.0:
            fake_bkout_prob += breakout_load * 0.3   # loading increases fakeout risk
        if vol_quality == "WEAK":
            fake_bkout_prob += 25.0   # no volume = likely fakeout
        elif vol_quality == "MODERATE":
            fake_bkout_prob += 8.0
        if rsi_div:
            fake_bkout_prob += 15.0   # divergence increases trap risk
        fake_bkout_prob = float(np.clip(fake_bkout_prob, 5.0, 90.0))

        if fake_bkout_prob > 60.0:
            risk_factors.append(
                f"🔴 Fake Breakout Risk: {fake_bkout_prob:.0f}% — "
                "compression release without volume confirmation"
            )
        elif fake_bkout_prob > 40.0:
            risk_factors.append(
                f"🟡 Breakout Quality Warning: {fake_bkout_prob:.0f}% fake probability"
            )

        component_risks.append(fake_bkout_prob)

        # ── 3. Liquidity Vacuum Risk ────────────────────────────────────────────
        liquidity   = sess.get("session_liquidity", "MEDIUM")
        liq_acc     = float(sess.get("liquidity_acceleration", 1.0))
        current_session = sess.get("current_session", "ASIAN")
        is_overlap  = bool(sess.get("is_overlap", False))

        liq_vacuum_risk = 10.0   # base
        if liquidity == "LOW":
            liq_vacuum_risk += 45.0
        elif liquidity == "MEDIUM":
            liq_vacuum_risk += 15.0
        if liq_acc < 0.7:
            liq_vacuum_risk += 20.0   # volume contracting
        if current_session == "ASIAN" and not is_overlap:
            liq_vacuum_risk += 10.0   # thin market hours
        if is_overlap:
            liq_vacuum_risk -= 15.0   # overlap = liquidity present
        liq_vacuum_risk = float(np.clip(liq_vacuum_risk, 5.0, 90.0))

        if liq_vacuum_risk > 55.0:
            risk_factors.append(
                f"🔴 Liquidity Vacuum: {liq_vacuum_risk:.0f}% risk — "
                f"session={current_session}, liq_acc={liq_acc:.2f}"
            )
        elif liq_vacuum_risk > 35.0:
            risk_factors.append(
                f"🟡 Thin Liquidity Warning ({liq_vacuum_risk:.0f}%) — "
                f"reduced execution quality in {current_session}"
            )

        component_risks.append(liq_vacuum_risk)

        # ── 4. Market Instability Risk ──────────────────────────────────────────
        stability = float(mem.get("market_stability", 50.0))
        regime_switches = max(0, 10 - int((stability - 10.0) / 9.0))  # estimate switches
        instability_risk = float(np.clip(100.0 - stability, 10.0, 90.0))

        if instability_risk > 60.0:
            risk_factors.append(
                f"🔴 Market Instability: {instability_risk:.0f}% — "
                "frequent regime switches detected"
            )

        component_risks.append(instability_risk)

        # ── Composite Risk Score ──────────────────────────────────────────────
        # Weighted: exhaustion and liquidity vacuum are highest concern
        risk_score = (
            exhaustion_prob  * 0.35 +
            fake_bkout_prob  * 0.25 +
            liq_vacuum_risk  * 0.25 +
            instability_risk * 0.15
        )
        risk_score = float(np.clip(risk_score, 0.0, 100.0))

        # ── Risk Level Classification ──────────────────────────────────────────
        if risk_score >= 70.0:
            risk_level = "CRITICAL"
        elif risk_score >= 50.0:
            risk_level = "HIGH"
        elif risk_score >= 30.0:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"

        return {
            "risk_score":             round(risk_score, 1),
            "risk_level":             risk_level,
            "exhaustion_probability": round(exhaustion_prob, 1),
            "fake_breakout_prob":     round(fake_bkout_prob, 1),
            "liquidity_vacuum_risk":  round(liq_vacuum_risk, 1),
            "risk_factors":           risk_factors,
        }
