"""
ui/tournament_panel.py
Presentational panel for strategy tournament standings and confidence explainability.
"""
import streamlit as st


def _score_bar(label: str, value: float, color: str, max_val: float = 100.0) -> str:
    pct = min(value / max_val * 100.0, 100.0)
    return f"""
    <div style="margin-bottom: 10px;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
            <span style="font-size: 0.82rem; color: #94a3b8; font-weight: 500;">{label}</span>
            <span style="font-size: 0.82rem; color: #cbd5e1; font-weight: 700;">{value:.1f}</span>
        </div>
        <div style="background: #1e293b; border-radius: 4px; height: 6px; overflow: hidden; border: 1px solid #334155;">
            <div style="background: {color}; width: {pct:.1f}%; height: 100%;"></div>
        </div>
    </div>
    """


def render_tournament_panel(latest_tournament: list, rejected_strategies: dict, state = None) -> None:
    """
    Renders Strategy Competition Standings and Explanatory Analytics.
    """
    st.markdown("#### 🏆 Strategy Tournament Standings")
    
    if not latest_tournament:
        st.markdown(
            '<div style="background:#0f172a;border:1px dashed #1e293b;border-radius:8px;'
            'padding:20px;text-align:center;color:#475569;font-size:0.85rem;">'
            'No tournament rankings computed yet. Wait for Loop 2 Analytical Cycle.</div>',
            unsafe_allow_html=True
        )
        return

    fatigue_scores = state.fatigue_scores if (state and hasattr(state, "fatigue_scores")) else {}

    # List ranking
    for idx, item in enumerate(latest_tournament, 1):
        name = item.get("strategy")
        score = item.get("market_fit_score", 0.0)
        supported = item.get("supported", False)
        
        # State logic based on fatigue and regime support
        fatigue = fatigue_scores.get(name, 0.0)
        
        if fatigue > 50.0:
            state_label = "BLOCKED"
            state_color = "#dc2626"
            bg_color = "rgba(220, 38, 38, 0.05)"
            border_color = "rgba(220, 38, 38, 0.2)"
        elif fatigue > 10.0:
            state_label = "COOLDOWN"
            state_color = "#d97706"
            bg_color = "rgba(217, 119, 6, 0.05)"
            border_color = "rgba(217, 119, 6, 0.2)"
        elif not supported:
            state_label = "SUPPRESSED"
            state_color = "#4b5563"
            bg_color = "rgba(75, 85, 99, 0.05)"
            border_color = "rgba(75, 85, 99, 0.2)"
        elif idx == 1:
            state_label = "ACTIVE"
            state_color = "#16a34a"
            bg_color = "linear-gradient(135deg, #14532d, #0f172a)"
            border_color = "#22c55e"
        else:
            state_label = "WATCHLIST"
            state_color = "#2563eb"
            bg_color = "#0f172a"
            border_color = "#1e293b"
            
        # Draw the card
        st.markdown(
            f"""
            <div style="background: {bg_color}; border: 1px solid {border_color}; border-radius: 8px;
                        padding: 12px 16px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center;">
                    <span style="font-weight: 800; font-size: 1.1rem; color: #64748b; margin-right: 12px;">#{idx}</span>
                    <div>
                        <strong style="color: #f1f5f9; font-size: 0.95rem;">{name}</strong><br>
                        <span style="font-size: 0.75rem; color: #94a3b8;">
                            Fatigue: {fatigue:.0f} | Regime Match: {"Yes" if supported else "No"}
                        </span>
                    </div>
                </div>
                <div style="text-align: right; display: flex; align-items: center; gap: 15px;">
                    <div>
                        <span style="font-size: 0.65rem; font-weight: 700; color: {state_color};
                                     background: {state_color}22; padding: 2px 8px; border-radius: 12px; border: 1px solid {state_color}44;">
                            {state_label}
                        </span>
                    </div>
                    <div>
                        <span style="font-weight: 800; font-size: 1.2rem; color: #3b82f6;">{score:.1f}</span>
                        <span style="font-size: 0.7rem; color: #475569; display: block;">FIT</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Rejection list
    if rejected_strategies:
        with st.expander("🚫 Tournament Rejection Log"):
            for strat_name, reason in rejected_strategies.items():
                st.markdown(
                    f"""
                    <div style="background: #111827; border: 1px solid #1e293b; border-radius: 6px; padding: 8px 12px; margin-bottom: 6px;">
                        <span style="color: #ef4444; font-weight: 700; font-size: 0.85rem;">❌ {strat_name}</span><br>
                        <span style="color: #94a3b8; font-size: 0.78rem;">Reason: {reason}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )


def render_explainability_panel(winner_strategy: dict) -> None:
    """
    Renders Confidence Explainability components of the winner.
    """
    st.markdown("#### 🔬 Strategy Explainability Panel")
    
    if not winner_strategy:
        st.markdown(
            '<div style="background:#0f172a;border:1px dashed #1e293b;border-radius:8px;'
            'padding:20px;text-align:center;color:#475569;font-size:0.85rem;">'
            'No strategy selected for explainability breakdown.</div>',
            unsafe_allow_html=True
        )
        return

    name = winner_strategy.get("strategy", "N/A")
    score_breakdown = winner_strategy.get("score_breakdown", {})
    confidence_breakdown = winner_strategy.get("confidence_breakdown", {})

    st.markdown(
        f"""
        <div style="background: #111827; border: 1px solid #1e293b; border-radius: 8px; padding: 14px; margin-bottom: 12px;">
            <span style="font-size: 0.72rem; color: #3b82f6; letter-spacing: 1.5px; font-weight: 700; text-transform: uppercase;">WINNER AT ENTRY</span>
            <div style="font-size: 1.15rem; font-weight: 800; color: #f1f5f9; margin-top: 2px;">{name}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if confidence_breakdown:
        st.markdown("**Confidence Factors breakdown:**")
        bars_html = ""
        bars_html += _score_bar("Trend Strength Match", float(confidence_breakdown.get("trend_strength", 0.0)), "#3b82f6")
        bars_html += _score_bar("M15/H1 Volatility Alignment", float(confidence_breakdown.get("volatility_alignment", 0.0)), "#eab308")
        bars_html += _score_bar("H4 Structure Quality", float(confidence_breakdown.get("structure_quality", 0.0)), "#10b981")
        bars_html += _score_bar("M5 Execution Readiness", float(confidence_breakdown.get("execution_readiness", 0.0)), "#ec4899")
        bars_html += _score_bar("Timing Alignment", float(confidence_breakdown.get("timing_alignment", 0.0)), "#8b5cf6")
        st.markdown(bars_html, unsafe_allow_html=True)
        
    if score_breakdown:
        fatigue_pen = abs(float(score_breakdown.get("fatigue_pen", 0.0)))
        noise_pen = abs(float(score_breakdown.get("noise_pen", 0.0)))
        lateness_pen = abs(float(score_breakdown.get("lateness_pen", 0.0)))
        total_pen = fatigue_pen + noise_pen + lateness_pen
        
        if total_pen > 0:
            st.markdown(f"**Applied Penalties:** `-{total_pen:.1f} pts`")
            penalties_html = ""
            if fatigue_pen > 0:
                penalties_html += _score_bar("Trend Fatigue Penalty", fatigue_pen, "#ef4444", 30.0)
            if noise_pen > 0:
                penalties_html += _score_bar("High Noise Penalty", noise_pen, "#ef4444", 30.0)
            if lateness_pen > 0:
                penalties_html += _score_bar("Lateness Penalty", lateness_pen, "#ef4444", 30.0)
            st.markdown(penalties_html, unsafe_allow_html=True)
        else:
            st.success("✅ No score penalties applied.")
