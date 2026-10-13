"""
ui/safety_panel.py
Presentational panel for circuit breakers, manual safety controls, and live event logging.
"""
import streamlit as st


def render_safety_panel(
    engine_state: str,
    spread: float,
    max_spread: float,
    volatility: str,
    drawdown: float,
    max_drawdown: float,
    consecutive_losses: int,
    max_losses: int,
    deployment_mode: str
) -> None:
    """
    Renders the Safety & Circuit Breaker status dashboard.
    """
    st.markdown("#### 🚨 Safety & Circuit Breakers")
    
    # State-based style
    state_colors = {
        "SAFE": "#3b82f6",
        "ARMED": "#f59e0b",
        "ACTIVE": "#22c55e",
        "PAUSED": "#64748b",
        "LOCKED": "#ef4444",
        "EMERGENCY": "#dc2626"
    }
    state_color = state_colors.get(engine_state, "#94a3b8")
    
    st.markdown(
        f"""
        <div style="background: #0f172a; border: 2px solid {state_color}; border-radius: 10px;
                    padding: 12px; text-align: center; font-weight: 800; font-size: 1.15rem; color: {state_color}; margin-bottom: 15px;">
            SYSTEM STATE: {engine_state}
        </div>
        """,
        unsafe_allow_html=True
    )

    # Circuit breakers
    spread_ok = spread <= max_spread
    vol_ok = volatility not in ("HIGH", "PANIC")
    drawdown_ok = drawdown < max_drawdown
    losses_ok = consecutive_losses < max_losses
    
    def _status_card(label: str, value_str: str, ok: bool):
        color = "#22c55e" if ok else "#ef4444"
        bg = "rgba(34, 197, 94, 0.03)" if ok else "rgba(239, 68, 68, 0.03)"
        dot = "🟢" if ok else "🚨"
        return f"""
        <div style="background: {bg}; border: 1px solid {color}44; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px;
                    display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 0.8rem; color: #cbd5e1; font-weight: 500;">{label}</span>
            <span style="font-size: 0.8rem; color: {color}; font-weight: 700;">{dot} {value_str}</span>
        </div>
        """

    cols = st.columns(2)
    with cols[0]:
        st.markdown(_status_card("Spread Broker Fit", f"{spread:.1f}/{max_spread:.1f} pts", spread_ok), unsafe_allow_html=True)
        st.markdown(_status_card("Market Volatility", volatility, vol_ok), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(_status_card("Daily Max Drawdown", f"{drawdown:.2f}%/{max_drawdown:.1f}%", drawdown_ok), unsafe_allow_html=True)
        st.markdown(_status_card("Consecutive Losses", f"{consecutive_losses}/{max_losses}", losses_ok), unsafe_allow_html=True)

    st.markdown("##### 🎛️ Safety Controls Override")
    
    # Render layout controls
    c_col1, c_col2 = st.columns(2)
    with c_col1:
        if engine_state == "PAUSED":
            if st.button("▶ Resume Trading", use_container_width=True, type="secondary"):
                st.session_state["manual_safety_action"] = "RESUME"
                st.rerun()
        else:
            if st.button("⏸ Pause Trading", use_container_width=True, type="secondary"):
                st.session_state["manual_safety_action"] = "PAUSE"
                st.rerun()
                
        # Dropdown selection for deployment mode
        modes = ["ADVISORY", "SEMI_AUTO", "LIVE"]
        idx = modes.index(deployment_mode) if deployment_mode in modes else 0
        selected_mode = st.selectbox("Execution Mode", modes, index=idx, key="safety_execution_mode_sel")
        if selected_mode != deployment_mode:
            st.session_state["manual_mode_change"] = selected_mode
            st.rerun()

    with c_col2:
        if st.button("🚨 Flatten & LOCK", use_container_width=True, type="primary"):
            st.session_state["manual_safety_action"] = "EMERGENCY_FLATTEN"
            st.rerun()
            
        if st.button("🔄 Reset Safety Locks", use_container_width=True):
            st.session_state["manual_safety_action"] = "RESET_SAFETY"
            st.rerun()


def render_event_stream(events: list) -> None:
    """
    Renders the live terminal operational Event log feed.
    """
    st.markdown("#### 📡 Live Execution Event Feed")
    
    if not events:
        st.code("[system] Event stream console ready. Standby.", language="bash")
        return

    # Render events in reverse-chronological order in a scrollable console style
    log_lines = []
    for evt in reversed(events):
        lvl = evt.get("level", "INFO")
        msg = evt.get("message", "")
        t = evt.get("timestamp", "")
        
        # Color coding level prefixes
        lvl_prefix = f"[{lvl}]"
        log_lines.append(f"[{t}] {lvl_prefix} {msg}")
        
    st.text_area(
        label="Operational logs log console",
        value="\n".join(log_lines),
        height=180,
        disabled=True,
        label_visibility="collapsed"
    )
