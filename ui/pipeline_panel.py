"""
ui/pipeline_panel.py
NexusBot V3 — 19-Engine Execution Pipeline Panel
Visualizes all 19 engines and execution flows in a premium grid layout.
"""
import streamlit as st
from typing import Dict, Any, List
from textwrap import dedent


def render_execution_pipeline(state, engine, orch_ctx) -> None:
    """
    Renders the co-equal 19-Engine Execution Pipeline diagnostics and stages.
    """
    st.markdown("<h3 style='margin-top:20px;'>⛓️ Execution Intelligence Pipeline</h3>", unsafe_allow_html=True)
    
    # Retrieve snapshot for presentation
    from deployment.engine_runtime import get_global_runtime
    runtime = get_global_runtime()
    snapshot = runtime.snapshot_store.get_snapshot()
    
    diagnostics = st.session_state.get("pipeline_diagnostics") or getattr(snapshot, "engine_diagnostics", {})
    flow = st.session_state.get("pipeline_flow") or getattr(snapshot, "pipeline_flow", [])
    
    # Fallback if snapshot is empty (e.g. before initial run)
    if not diagnostics or not flow:
        if not orch_ctx:
            st.warning("⚠️ No pipeline execution context in memory. Run the intelligence pipeline in the Analysis Lab to populate detailed diagnostics.")
            return
        # Dynamically compile fallback using runtime's parsing logic
        try:
            diagnostics = runtime.orchestration._compile_engine_diagnostics(orch_ctx)
            flow = runtime.orchestration._compile_pipeline_flow(orch_ctx)
        except Exception:
            st.warning("Pipeline context is still warming up. Download data or run the intelligence pipeline to populate detailed diagnostics.")
            return

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. Pipeline Flow Visualization
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("##### 📡 Pipeline Stages Flow")
    
    flow_html = '<div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between;align-items:center;background:rgba(17,24,39,0.85);border:1px solid #1e293b;border-radius:8px;padding:14px;margin-bottom:25px;">'
    for idx, stage in enumerate(flow):
        status = stage.get("status", "PASS")
        name = stage.get("name", "Unknown")
        latency = stage.get("latency", "0.0ms")
        
        dot_color = "#22c55e" if status == "PASS" else ("#f59e0b" if status == "WARNING" else ("#64748b" if status == "BLOCKED" else "#ef4444"))
        bg_glow = f"box-shadow: 0 0 10px {dot_color}44;"
        
        flow_html += (
            f'<div style="background:#0b111e;border:1px solid #334155;border-radius:6px;padding:6px 12px;min-width:110px;text-align:center;{bg_glow}">'
            f'<div style="font-size:0.72rem;font-weight:700;color:#f1f5f9;">{name}</div>'
            f'<div style="display:flex;align-items:center;justify-content:center;gap:5px;margin-top:4px;">'
            f'<span style="display:inline-block;width:6px;height:6px;background:{dot_color};border-radius:50%;"></span>'
            f'<span style="font-size:0.62rem;color:{dot_color};font-weight:800;text-transform:uppercase;">{status}</span>'
            f'</div>'
            f'<div style="font-size:0.60rem;color:#64748b;font-family:monospace;margin-top:2px;">{latency}</div>'
            f'</div>'
        )
        
        # Add connectors between steps
        if idx < len(flow) - 1:
            flow_html += '<div style="color: #475569; font-size: 1.15rem; font-weight: 700;">→</div>'
            
    flow_html += "</div>"
    st.markdown(flow_html, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. 19 individual Engine grid
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("##### ⚙️ Modular Intelligence Diagnostics")
    
    # Setup previous confidences in session state for tracking deltas
    if "prev_engine_confidences" not in st.session_state:
        st.session_state["prev_engine_confidences"] = {}
        
    prev_confs = st.session_state["prev_engine_confidences"]
    
    cols = st.columns(3)
    engine_names = list(diagnostics.keys())
    
    for idx, name in enumerate(engine_names):
        col = cols[idx % 3]
        eng_data = diagnostics[name]
        
        state_val = eng_data.get("state", "PASSIVE")
        confidence = float(eng_data.get("confidence", 50.0))
        contribution = float(eng_data.get("score_contribution", 0.0))
        penalties = float(eng_data.get("penalties", 0.0))
        contradictions = int(eng_data.get("contradictions", 0))
        latency = eng_data.get("latency", "0.0ms")
        details = eng_data.get("details", "")
        
        # Calculate delta
        prev_conf = prev_confs.get(name, confidence)
        delta = confidence - prev_conf
        prev_confs[name] = confidence # update for next run
        
        if delta > 0:
            delta_str = f"<span style='color:#22c55e;font-size:0.68rem;font-weight:700;'>▲ +{delta:.1f}%</span>"
        elif delta < 0:
            delta_str = f"<span style='color:#ef4444;font-size:0.68rem;font-weight:700;'>▼ {delta:.1f}%</span>"
        else:
            delta_str = "<span style='color:#64748b;font-size:0.68rem;'>— 0.0%</span>"
            
        # Badge color mappings
        badge_colors = {
            "ACTIVE": "#22c55e",
            "PASSIVE": "#3b82f6",
            "BLOCKED": "#ef4444",
            "INVALIDATED": "#dc2626",
            "COOLING": "#f59e0b",
            "WATCHING": "#8b5cf6"
        }
        badge_color = badge_colors.get(state_val.upper(), "#64748b")
        
        with col:
            # Render a custom HTML card for premium styling
            card_html = (
                f'<div style="background:rgba(17,24,39,0.7);border:1px solid #1e293b;border-radius:8px;padding:12px;margin-bottom:15px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">'
                f'<span style="font-size:0.8rem;font-weight:700;color:#f8fafc;max-width:70%;line-height:1.2;">{name}</span>'
                f'<span style="background:{badge_color}22;border:1px solid {badge_color}44;color:{badge_color};font-size:0.62rem;font-weight:800;padding:2px 8px;border-radius:12px;text-transform:uppercase;">{state_val}</span>'
                f'</div>'
                f'<div style="display:flex;justify-content:space-between;margin-bottom:10px;">'
                f'<div><span style="font-size:0.65rem;color:#64748b;display:block;text-transform:uppercase;">Confidence</span>'
                f'<strong style="font-size:0.95rem;color:#cbd5e1;">{confidence:.1f}%</strong> {delta_str}</div>'
                f'<div style="text-align:right;"><span style="font-size:0.65rem;color:#64748b;display:block;text-transform:uppercase;">Latency</span>'
                f'<strong style="font-size:0.85rem;color:#cbd5e1;font-family:monospace;">{latency}</strong></div>'
                f'</div>'
                f'<div style="display:flex;justify-content:space-between;border-top:1px solid #1e293b;padding-top:8px;margin-bottom:8px;font-size:0.72rem;color:#cbd5e1;">'
                f'<span>Contribution: <strong style="color:#22c55e;">+{contribution:.1f}</strong></span>'
                f'<span>Penalties: <strong style="color:#ef4444;">-{penalties:.1f}</strong></span>'
                f'<span>Conflicts: <strong style="color:#eab308;">{contradictions}</strong></span>'
                f'</div></div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)
            
            with st.expander("🔍 Diagnostics & Score Decomposition", expanded=False):
                st.markdown(f"**Diagnostic logs:**\n`{details}`")
                
                # Render score bar
                pct = min(100.0, max(0.0, confidence))
                st.markdown(dedent(f"""
                <div style="margin-top: 6px;">
                    <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:#94a3b8; margin-bottom: 3px;">
                        <span>Fit score decomposition</span>
                        <strong style="color:#fff;">{confidence:.1f}/100</strong>
                    </div>
                    <div style="background:#1e293b; border-radius:4px; height:6px; overflow:hidden;">
                        <div style="width: {pct:.1f}%; background: linear-gradient(90deg, #3b82f6, #22c55e); height:100%;"></div>
                    </div>
                </div>
                """), unsafe_allow_html=True)
