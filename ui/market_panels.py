"""
ui/market_panels.py
Market Regime + Multi-Timeframe Context UI panels.
"""
import streamlit as st


# ── Colour helpers ────────────────────────────────────────────────────────────

_REGIME_COLORS = {
    "TRENDING":       "#22c55e",   # green
    "VOLATILE":       "#f59e0b",   # amber
    "RANGING":        "#3b82f6",   # blue
    "LOW_VOLATILITY": "#94a3b8",   # slate
}

_DIR_COLORS = {
    "BULLISH": "#22c55e",
    "BEARISH": "#ef4444",
    "NEUTRAL": "#94a3b8",
}

_DIR_ICONS = {
    "BULLISH": "▲",
    "BEARISH": "▼",
    "NEUTRAL": "◆",
}


def _badge(label: str, color: str, icon: str = "") -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:3px 10px;'
        f'border-radius:12px;font-weight:700;font-size:0.85rem;">'
        f'{icon} {label}</span>'
    )


# ── Main panel ────────────────────────────────────────────────────────────────

def render_regime_panel(regime: dict, context: dict | None = None) -> None:
    """
    Renders the Market Regime panel in the Streamlit UI.

    Args:
        regime  : Output from MarketRegimeEngine.detect()
        context : Output from build_multi_timeframe_context() [optional]
    """
    if not regime:
        st.warning("No regime data available. Upload a dataset first.")
        return

    regime_label = regime.get("regime",    "UNKNOWN")
    direction    = regime.get("direction", "NEUTRAL")
    trend_str    = float(regime.get("trend_strength",       0.0))
    vol_score    = float(regime.get("volatility_score",     50.0))
    brk_prob     = float(regime.get("breakout_probability", 0.5))
    persistence  = float(regime.get("trend_persistence",    0.5))

    regime_color = _REGIME_COLORS.get(regime_label, "#94a3b8")
    dir_color    = _DIR_COLORS.get(direction, "#94a3b8")
    dir_icon     = _DIR_ICONS.get(direction, "◆")

    # ── Header badges ─────────────────────────────────────────────────────────
    col_a, col_b, col_c = st.columns([1.4, 1.2, 1])
    with col_a:
        st.markdown(_badge(regime_label, regime_color), unsafe_allow_html=True)
    with col_b:
        st.markdown(_badge(direction, dir_color, dir_icon), unsafe_allow_html=True)
    if context:
        with col_c:
            align = float(context.get("alignment_score", 50.0))
            align_color = "#22c55e" if align >= 65 else ("#f59e0b" if align >= 40 else "#ef4444")
            st.markdown(_badge(f"MTF Align {align:.0f}", align_color), unsafe_allow_html=True)

    st.markdown("")

    # ── Core metrics ──────────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Trend Strength (ADX)", f"{trend_str:.1f}")
    m2.metric("Volatility Score",     f"{vol_score:.1f}/100")
    m3.metric("Breakout Probability", f"{brk_prob * 100:.0f}%")
    m4.metric("Trend Persistence",    f"{persistence * 100:.0f}%")

    # ── Context label ─────────────────────────────────────────────────────────
    if context:
        label = context.get("context_label", "")
        if label:
            st.caption(f"🔍 Context: **{label}**")

    # ── Advanced expander ────────────────────────────────────────────────────
    with st.expander("Advanced Regime Metrics", expanded=False):
        if context:
            m15 = context.get("m15_behavior", {})
            st.markdown("##### M15 Micro Behavior")
            b1, b2, b3 = st.columns(3)
            b1.metric("Pullback Quality",  f"{m15.get('pullback_quality',  0.5) * 100:.0f}/100")
            b2.metric("Breakout Strength", f"{m15.get('breakout_strength', 0.5) * 100:.0f}/100")
            b3.metric("Momentum Quality",  f"{m15.get('momentum_quality',  0.5) * 100:.0f}/100")

        st.markdown("##### Raw Regime Indicators")
        raw_data = {
            "ADX":               regime.get("_adx",               "N/A"),
            "ATR Ratio":         regime.get("_atr_ratio",         "N/A"),
            "Compression Score": regime.get("_compression_score", "N/A"),
        }
        for k, v in raw_data.items():
            if v != "N/A":
                st.write(f"**{k}:** {v}")
