"""
ui/execution_panel.py
Presentational panel for live execution signal cards and read-only positions list.
"""
import streamlit as st


def render_execution_signal_card(active_candidates: list) -> None:
    """
    Renders the overlay-style Live Execution Signal Card.
    """
    st.markdown("#### 📡 Live Execution Signal Card")
    
    if not active_candidates:
        st.markdown(
            '<div style="background:#0f172a;border:1px dashed #1e293b;border-radius:8px;'
            'padding:20px;text-align:center;color:#475569;font-size:0.85rem;">'
            'No candidate signals generated in this timeframe. Engine is standby.</div>',
            unsafe_allow_html=True
        )
        return

    for cand in active_candidates:
        direction = cand.get("direction", "NEUTRAL")
        strategy = cand.get("strategy", "Unknown")
        confidence = cand.get("confidence", 0.0)
        reasons = cand.get("reasons", [])
        
        # Color schemes
        if direction in ("BUY", "BULLISH", "UP"):
            bg_color = "linear-gradient(135deg, #064e3b, #0f172a)"
            border_color = "#10b981"
            txt_color = "#10b981"
            icon = "🐂"
        elif direction in ("SELL", "BEARISH", "DOWN"):
            bg_color = "linear-gradient(135deg, #7f1d1d, #0f172a)"
            border_color = "#ef4444"
            txt_color = "#ef4444"
            icon = "🐻"
        else:
            bg_color = "#111827"
            border_color = "#334155"
            txt_color = "#94a3b8"
            icon = "◆"
            
        reasons_list = "".join(f"<li>• {r}</li>" for r in reasons)
        
        st.markdown(
            f"""
            <div style="background: {bg_color}; border: 2px solid {border_color}; border-radius: 12px;
                        padding: 16px; margin-bottom: 12px; box-shadow: 0 0 15px {border_color}22;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 0.75rem; color: #94a3b8; letter-spacing: 2px; font-weight: 700;">EXECUTION SIGNAL</span>
                    <span style="font-size: 0.7rem; color: #fff; background: {border_color}; padding: 2px 8px; border-radius: 12px; font-weight: 700;">
                        READY
                    </span>
                </div>
                <h3 style="color: #f8fafc; margin: 8px 0 2px 0; font-size: 1.3rem; font-weight: 800;">
                    {icon} {direction} — {strategy}
                </h3>
                <div style="font-size: 1.6rem; font-weight: 900; color: {txt_color}; margin-bottom: 8px;">
                    {confidence:.1f}% <span style="font-size: 0.8rem; color: #64748b; font-weight: 500;">Confidence Score</span>
                </div>
                <div style="border-top: 1px solid #1e293b; padding-top: 8px; font-size: 0.82rem; color: #cbd5e1;">
                    <strong style="color: #94a3b8;">Trigger Conditions:</strong>
                    <ul style="list-style-type: none; padding-left: 0; margin-top: 4px; margin-bottom: 0;">
                        {reasons_list or "<li>• Indicators aligned in favor</li>"}
                    </ul>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )


def render_position_command_center(active_positions: list) -> None:
    """
    Renders the Position Command Center (read-only listing with mapped action buttons).
    """
    st.markdown("#### 📂 Live Position Command Center")
    
    if not active_positions:
        st.markdown(
            '<div style="background:#0f172a;border:1px dashed #1e293b;border-radius:8px;'
            'padding:30px;text-align:center;color:#475569;font-size:0.85rem;">'
            'No active open positions. Deployed strategies are monitoring markets.</div>',
            unsafe_allow_html=True
        )
        return

    for pos in active_positions:
        ticket = pos.get("ticket")
        strategy = pos.get("strategy", "Unknown")
        direction = pos.get("direction", "BUY")
        entry_price = float(pos.get("entry_price", 0.0))
        sl = pos.get("sl", 0.0)
        tp = pos.get("tp", 0.0)
        lot = float(pos.get("lot") or pos.get("qty", 0.01))
        live_pnl = float(pos.get("live_pnl", 0.0))
        confidence = pos.get("confidence", 0.0)
        regime = pos.get("regime_at_entry", "N/A")
        
        pnl_color = "#22c55e" if live_pnl >= 0 else "#ef4444"
        dir_color = "#22c55e" if direction == "BUY" else "#ef4444"
        
        # We split the card layout to let the presentational layer display the data,
        # but place the close button on the right using a clean Streamlit column wrapper.
        card_col, btn_col = st.columns([5, 1.2])
        
        with card_col:
            # Calculate price-to-exit progress bar
            current_price = entry_price
            if st.session_state.get("live_state") and st.session_state["live_state"].last_price:
                current_price = st.session_state["live_state"].last_price
                
            progress_pct = 50.0
            if sl and tp and (tp != sl):
                if direction == "BUY":
                    progress_pct = (current_price - sl) / (tp - sl) * 100.0
                else:
                    progress_pct = (sl - current_price) / (sl - tp) * 100.0
            progress_pct = max(0.0, min(100.0, progress_pct))
            sl_display = f"{float(sl):.5f}" if sl else "N/A"
            tp_display = f"{float(tp):.5f}" if tp else "N/A"
            
            st.markdown(
                f"""
                <div style="background: #111827; border-left: 4px solid {pnl_color}; border-radius: 8px;
                            padding: 12px 16px; margin-bottom: 10px; border-top: 1px solid #1e293b;
                            border-right: 1px solid #1e293b; border-bottom: 1px solid #1e293b;">
                    <div style="display: flex; justify-content: space-between;">
                        <div>
                            <strong style="color: #f1f5f9; font-size: 0.95rem;">#{ticket} {strategy}</strong><br>
                            <span style="font-weight: 700; color: {dir_color}; font-size: 0.8rem;">{direction}</span>
                            <span style="color: #64748b; font-size: 0.75rem;"> @ {entry_price:.5f} | {lot:.2f} lots</span>
                        </div>
                        <div style="text-align: right;">
                            <span style="color: {pnl_color}; font-size: 1.15rem; font-weight: 900;">${live_pnl:+.2f}</span><br>
                            <span style="color: #64748b; font-size: 0.7rem;">Entry Conf: {confidence:.0f}%</span>
                        </div>
                    </div>
                    
                    <!-- Lifecycle Progress Bar -->
                    <div style="margin-top: 10px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; font-size: 0.7rem; color: #64748b; margin-bottom: 2px;">
                            <span>SL ({sl_display})</span>
                            <span style="color: #cbd5e1; font-weight: 600;">Last: {current_price:.5f}</span>
                            <span>TP ({tp_display})</span>
                        </div>
                        <div style="background: #1e293b; border-radius: 4px; height: 6px; position: relative; overflow: hidden; border: 1px solid #334155;">
                            <div style="background: linear-gradient(90deg, #ef4444 0%, #3b82f6 50%, #22c55e 100%); width: 100%; height: 100%;"></div>
                            <div style="position: absolute; left: {progress_pct}%; top: 0; width: 4px; height: 100%; background: #ffffff; box-shadow: 0 0 5px #fff; transform: translateX(-50%);"></div>
                        </div>
                    </div>
                    
                    <div style="display: flex; gap: 15px; margin-top: 6px; border-top: 1px solid #1e293b; padding-top: 6px; font-size: 0.72rem; color: #94a3b8;">
                        <span>SL: <strong style="color: #ef4444;">{f"{sl:.5f}" if sl else "None"}</strong></span>
                        <span>TP: <strong style="color: #22c55e;">{f"{tp:.5f}" if tp else "None"}</strong></span>
                        <span>Regime at Entry: <strong style="color: #e2e8f0;">{regime}</strong></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            
        with btn_col:
            # Add vertical spacer to center button
            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
            if st.button("✖ Close", key=f"btn_close_pos_{ticket}", use_container_width=True):
                # Set session state intent for manual close routing (read-only UI constraint)
                st.session_state["manual_close_intent"] = ticket
                st.rerun()
