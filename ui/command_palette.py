"""
ui/command_palette.py
NexusBot V3 — Command Palette Component
Handles Ctrl+K keyboard shortcut hook, command bar rendering, and action dispatch.
"""
import streamlit as st


def render_command_palette(state, engine) -> None:
    """
    Renders the Command Palette bar and hooks keyboard shortcuts.
    """
    # 1. Keyboard Shortcut Hook (Ctrl+K / Cmd+K)
    st.components.v1.html(
        """
        <script>
        var parent_doc = window.parent.document;
        
        // Listen to keydown on parent window
        window.parent.addEventListener("keydown", function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
                e.preventDefault();
                // Find command input element by placeholder text
                var inputs = Array.from(parent_doc.querySelectorAll("input"));
                var cmdInput = inputs.find(el => el.placeholder && el.placeholder.includes("Ctrl+K"));
                if (cmdInput) {
                    cmdInput.focus();
                    cmdInput.select();
                }
            }
        });
        </script>
        """,
        height=0,
        width=0
    )

    # 2. Command Palette Bar
    st.markdown("##### ⌨️ Command Palette")
    
    if "command_palette_seq" not in st.session_state:
        st.session_state["command_palette_seq"] = 0
        
    cmd_key = f"command_palette_input_{st.session_state['command_palette_seq']}"
    cmd_val = st.text_input(
        "Execute command",
        placeholder="Type command... (Ctrl+K)",
        label_visibility="collapsed",
        key=cmd_key
    )
    
    # Process Command
    if cmd_val:
        # Clear input immediately on submit by incrementing seq
        st.session_state["command_palette_seq"] += 1
        clean_cmd = cmd_val.strip().lower()
        
        state.event_bus.emit(f"Command entered: {cmd_val}", "DEBUG")
        
        if clean_cmd == "/analysis":
            st.session_state["active_workspace_sel"] = "Analysis Lab"
            st.success("Switching to Analysis Lab...")
            st.rerun()

        elif clean_cmd == "/dashboard":
            st.session_state["active_workspace_sel"] = "Dashboard View"
            st.success("Switching to Dashboard View...")
            st.rerun()
            
        elif clean_cmd == "/live":
            st.session_state["active_workspace_sel"] = "Live Trade Center"
            st.success("Switching to Live Trade Center...")
            st.rerun()
            
        elif clean_cmd == "/optimize":
            st.session_state["active_workspace_sel"] = "Optimizer Lab"
            st.success("Switching to Optimizer Lab...")
            st.rerun()

        elif clean_cmd == "/settings":
            st.session_state["active_workspace_sel"] = "Settings"
            st.success("Switching to Settings...")
            st.rerun()
            
        elif clean_cmd == "/pause":
            state.set_engine_state("PAUSED")
            st.warning("Engine loops paused.")
            st.rerun()
            
        elif clean_cmd == "/resume":
            state.set_engine_state("SAFE")
            st.success("Engine loops resumed.")
            st.rerun()
            
        elif clean_cmd == "/flatten":
            # Close all positions
            for pos in list(state.active_positions):
                candle_dict = {"close": state.last_price, "high": state.last_price, "low": state.last_price, "open": state.last_price}
                closed = engine.trade_manager.close_position(pos, candle_dict, state.last_price, "emergency_flattening")
                state.remove_position(pos["ticket"])
                engine.balance += closed["profit"]
                state.record_trade_outcome(closed["profit"])
            state.set_engine_state("EMERGENCY")
            st.error("EMERGENCY SHUTDOWN: All positions flattened.")
            st.rerun()
            
        elif clean_cmd == "/reset":
            state.reset_daily_stats()
            st.success("Daily limits and safety locks reset.")
            st.rerun()
            
        else:
            st.error(f"Unknown command: '{cmd_val}'. Type '/' to see options.")
            
    # Command Cheat Sheet Help
    with st.expander("❓ Command Cheat Sheet", expanded=False):
        st.markdown(
            """
            * `/analysis` - Open regime market analysis lab
            * `/dashboard` - Open multi-symbol strategy dashboard
            * `/live` - Switch to operational Live Trade Center
            * `/optimize` - Run parameter sweeps and Monte Carlo simulation
            * `/settings` - Open runtime settings and connections
            * `/pause` - Pause loop execution
            * `/resume` - Resume loop execution
            * `/flatten` - Emergency close all positions & pause engine
            * `/reset` - Reset daily statistics and clear lockout gates
            """
        )
