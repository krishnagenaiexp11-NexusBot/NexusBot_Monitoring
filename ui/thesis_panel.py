"""
ui/thesis_panel.py
NexusBot V3 — Trade Thesis Panel
Visualizes core trade thesis and operational execution parameters in a dense Bloomberg-style grid.
"""
import streamlit as st


def render_trade_thesis(state, engine, orch_ctx) -> None:
    """
    Renders the Trade Thesis component.
    """
    st.markdown("#### 📜 Institutional Trade Thesis")

    # Extract values defensively
    h4 = orch_ctx.h4_structure if orch_ctx else {}
    ctx = st.session_state.get("mtf_context", {}) or {}
    sess = orch_ctx.session_context if orch_ctx else {}
    risk = orch_ctx.institutional_risk if orch_ctx else {}
    ready = orch_ctx.execution_readiness if orch_ctx else {}
    conf = orch_ctx.confidence_hierarchy if orch_ctx else {}
    
    bias = ctx.get("h1_structure", {}).get("structure_direction", "NEUTRAL")
    deploy_state = state.engine_state
    confidence_val = conf.get("weighted_confidence_score", 50.0)
    exec_qual = ready.get("readiness_score", 50.0)
    stress_idx = getattr(state, "stress_level", "LOW")
    liq_state = sess.get("session_liquidity", "NORMAL")
    struct_state = ctx.get("h1_structure", {}).get("macro_regime", "RANGING")
    session_personality = getattr(state, "market_personality", "SMOOTH_TREND")
    risk_state = risk.get("risk_level", "MODERATE")
    
    # Calculate invalidation level (e.g. SL or structural swing high/low)
    last_price = state.last_price or 0.0
    if bias == "BULLISH" or bias == "BUY":
        invalidation_level = last_price * 0.992
    elif bias == "BEARISH" or bias == "SELL":
        invalidation_level = last_price * 1.008
    else:
        invalidation_level = last_price

    lifecycle_state = "WATCHING SETUP"
    if state.active_positions:
        lifecycle_state = "ACTIVE OPERATION"
    elif state.engine_state == "EMERGENCY":
        lifecycle_state = "EMERGENCY RECOVERY"
    elif state.engine_state == "LOCKED":
        lifecycle_state = "DRAWDOWN LIMIT LOCKOUT"

    bias_colors = {"BULLISH": "#22c55e", "BUY": "#22c55e", "BEARISH": "#ef4444", "SELL": "#ef4444", "NEUTRAL": "#cbd5e1"}
    b_color = bias_colors.get(bias.upper(), "#cbd5e1")
    
    # Render grid using compact html
    st.markdown(
        f"""
        <div style="background: rgba(17, 24, 39, 0.8); border: 1px solid #1e293b; border-radius: 8px; padding: 14px; font-family: 'Inter', sans-serif;">
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; font-size: 0.78rem;">
                <div style="border-bottom: 1px solid #1e293b; padding-bottom: 6px;">
                    <span style="color: #64748b; display: block; text-transform: uppercase; font-size: 0.6rem; letter-spacing: 0.5px;">Bias Direction</span>
                    <strong style="color: {b_color}; font-size: 0.9rem;">{bias}</strong>
                </div>
                <div style="border-bottom: 1px solid #1e293b; padding-bottom: 6px;">
                    <span style="color: #64748b; display: block; text-transform: uppercase; font-size: 0.6rem; letter-spacing: 0.5px;">Deployment State</span>
                    <strong style="color: #f8fafc; font-size: 0.9rem;">{deploy_state}</strong>
                </div>
                <div style="border-bottom: 1px solid #1e293b; padding-bottom: 6px;">
                    <span style="color: #64748b; display: block; text-transform: uppercase; font-size: 0.6rem; letter-spacing: 0.5px;">Orchestration Confidence</span>
                    <strong style="color: #3b82f6; font-size: 0.9rem;">{confidence_val:.1f}%</strong>
                </div>
                <div style="border-bottom: 1px solid #1e293b; padding-bottom: 6px;">
                    <span style="color: #64748b; display: block; text-transform: uppercase; font-size: 0.6rem; letter-spacing: 0.5px;">Execution Quality</span>
                    <strong style="color: #eab308; font-size: 0.9rem;">{exec_qual:.1f}%</strong>
                </div>
                <div style="border-bottom: 1px solid #1e293b; padding-bottom: 6px;">
                    <span style="color: #64748b; display: block; text-transform: uppercase; font-size: 0.6rem; letter-spacing: 0.5px;">Stress Index</span>
                    <strong style="color: #f59e0b; font-size: 0.85rem;">{stress_idx}</strong>
                </div>
                <div style="border-bottom: 1px solid #1e293b; padding-bottom: 6px;">
                    <span style="color: #64748b; display: block; text-transform: uppercase; font-size: 0.6rem; letter-spacing: 0.5px;">Liquidity State</span>
                    <strong style="color: #10b981; font-size: 0.85rem;">{liq_state}</strong>
                </div>
                <div style="border-bottom: 1px solid #1e293b; padding-bottom: 6px;">
                    <span style="color: #64748b; display: block; text-transform: uppercase; font-size: 0.6rem; letter-spacing: 0.5px;">Structure Phase</span>
                    <strong style="color: #a855f7; font-size: 0.85rem;">{struct_state}</strong>
                </div>
                <div style="border-bottom: 1px solid #1e293b; padding-bottom: 6px;">
                    <span style="color: #64748b; display: block; text-transform: uppercase; font-size: 0.6rem; letter-spacing: 0.5px;">Session Personality</span>
                    <strong style="color: #cbd5e1; font-size: 0.85rem;">{session_personality.replace('_', ' ')}</strong>
                </div>
                <div>
                    <span style="color: #64748b; display: block; text-transform: uppercase; font-size: 0.6rem; letter-spacing: 0.5px;">Risk State</span>
                    <strong style="color: #ef4444; font-size: 0.85rem;">{risk_state}</strong>
                </div>
                <div>
                    <span style="color: #64748b; display: block; text-transform: uppercase; font-size: 0.6rem; letter-spacing: 0.5px;">Invalidation Level</span>
                    <strong style="color: #ec4899; font-size: 0.85rem;">{invalidation_level:.2f}</strong>
                </div>
            </div>
            <div style="margin-top: 12px; padding-top: 8px; border-top: 1px solid #1e293b; font-size: 0.72rem; color: #94a3b8; display: flex; justify-content: space-between; align-items: center;">
                <span>Lifecycle Status:</span>
                <strong style="color: #3b82f6;">{lifecycle_state}</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
