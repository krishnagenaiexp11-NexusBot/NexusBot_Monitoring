"""
ui/deployment_panels.py
Deployment Candidate UI panels.
"""
import json
import streamlit as st


_GRADE_COLORS = {
    "UNSAFE":       "#ef4444",
    "EXPERIMENTAL": "#f59e0b",
    "PROMISING":    "#3b82f6",
    "ROBUST":       "#22c55e",
    "RARE":         "#a855f7",
    "UNKNOWN":      "#94a3b8",
}


def render_deployment_panel(candidate: dict) -> None:
    """
    Renders the Deployment Candidate profile card.

    Args:
        candidate : Output from generate_candidate()
    """
    if not candidate:
        st.info("Generate a Deployment Candidate first.")
        return

    strategy    = candidate.get("strategy",          "Unknown")
    symbol      = candidate.get("symbol",            "UNKNOWN")
    dep_score   = float(candidate.get("deployment_score", 0.0))
    grade       = candidate.get("grade",             "UNKNOWN")
    parameters  = candidate.get("parameters",        {})
    val_metrics = candidate.get("validation_metrics",{})
    warnings    = candidate.get("warnings",          [])
    ready       = bool(candidate.get("ready_for_deployment", False))
    generated   = candidate.get("generated_at",     "")

    grade_color = _GRADE_COLORS.get(grade, "#94a3b8")

    # ── Profile card ─────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#1e293b,#0f172a);
                    border:1px solid {grade_color};border-radius:14px;
                    padding:20px 24px;margin-bottom:16px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="color:#94a3b8;font-size:0.75rem;text-transform:uppercase;
                                letter-spacing:1px;">{symbol}</div>
                    <div style="color:#f1f5f9;font-size:1.5rem;font-weight:800;">{strategy}</div>
                </div>
                <div style="text-align:right;">
                    <div style="color:#94a3b8;font-size:0.75rem;">Deployment Score</div>
                    <div style="color:{grade_color};font-size:2rem;font-weight:900;">{dep_score:.1f}</div>
                    <div style="background:{grade_color};color:#fff;padding:2px 10px;
                                border-radius:10px;font-weight:700;font-size:0.8rem;
                                display:inline-block;">{grade}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Key metrics row ───────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Val Profit Factor",  f"{val_metrics.get('profit_factor',   0.0):.2f}")
    c2.metric("Val Win Rate",       f"{val_metrics.get('win_rate_pct',    0.0):.1f}%")
    c3.metric("Val Max Drawdown",   f"{val_metrics.get('max_drawdown_pct',0.0):.1f}%")
    c4.metric("Val Trades",         str(val_metrics.get("trades",         0)))

    # ── Ready status ──────────────────────────────────────────────────────────
    if ready:
        st.success("✅ **Ready for deployment** — All validation checks passed.")
    elif warnings:
        st.warning(f"⚠️ Deployment candidate has {len(warnings)} warning(s). Review before deploying.")
    else:
        st.info("ℹ️ Score below deployment threshold. Run Full Validation for better candidates.")

    # ── Parameters ───────────────────────────────────────────────────────────
    st.markdown("##### Recommended Parameters")
    key_params = {k: v for k, v in parameters.items() if k in ("sl_atr", "tp_atr", "cooldown")}
    p1, p2, p3 = st.columns(3)
    p1.metric("SL ATR Multiplier", str(key_params.get("sl_atr",  "–")))
    p2.metric("TP ATR Multiplier", str(key_params.get("tp_atr",  "–")))
    p3.metric("Cooldown Candles",  str(key_params.get("cooldown","–")))

    # ── Advanced expander ─────────────────────────────────────────────────────
    with st.expander("Full Parameter Set", expanded=False):
        st.json(candidate.get("full_parameters", parameters))

    with st.expander("Validation Warnings", expanded=bool(warnings)):
        if warnings:
            for w in warnings:
                st.warning(w)
        else:
            st.success("No validation warnings.")

    # ── Export ────────────────────────────────────────────────────────────────
    st.markdown("##### Export")
    json_str = json.dumps(candidate, indent=2, ensure_ascii=False)
    st.download_button(
        label     = "⬇️ Export Deployment Profile (JSON)",
        data      = json_str,
        file_name = f"nexusbot_{strategy.lower().replace(' ', '_')}_{symbol}.json",
        mime      = "application/json",
        key       = "download_deployment_profile",
    )

    if generated:
        st.caption(f"Generated: {generated}")


def render_saved_profiles_panel(profiles: list) -> None:
    """
    Renders the list of saved deployment profiles from storage.
    """
    if not profiles:
        st.info("No saved deployment profiles yet.")
        return

    st.markdown(f"**{len(profiles)} saved profile(s)**")
    for profile in profiles:
        grade_color = _GRADE_COLORS.get(profile.grade, "#94a3b8")
        with st.expander(
            f"[{profile.grade}] {profile.strategy} | {profile.symbol} | "
            f"Score: {profile.deployment_score:.1f} | {profile.generated_at[:10]}",
            expanded=False,
        ):
            c1, c2 = st.columns(2)
            c1.metric("Deployment Score", f"{profile.deployment_score:.1f}")
            c2.metric("Grade", profile.grade)
            st.json(profile.parameters)
