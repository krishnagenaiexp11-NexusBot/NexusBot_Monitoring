"""
ui/institutional_dashboard.py
Institutional Decision Intelligence Dashboard for NexusBot V3.

Implements a 5-Tier Progressive Disclosure dashboard:
  Tier 1 — Executive Command Center (readiness, risk, timing co-equal)
  Tier 2 — Key Intelligence Insights (narrative compression — 5 bullets)
  Tier 3 — Strategy War Room (tournament cards + contradiction penalties)
  Tier 4 — Market Diagnostics (transitions, sessions, memory, saturation)
  Tier 5 — Raw Quant Lab (hidden indicators, full logs)

Uses glassmorphism, animated badges, and color-coded severity indicators.
"""
import streamlit as st
from engine.orchestration_context import OrchestrationContext


# ── Color Constants ────────────────────────────────────────────────────────────
_RISK_COLORS = {
    "CRITICAL": "#dc2626",
    "HIGH":     "#f59e0b",
    "MODERATE": "#3b82f6",
    "LOW":      "#22c55e",
}

_STATE_COLORS = {
    "READY":     "#22c55e",
    "WATCHLIST": "#f59e0b",
    "AVOID":     "#ef4444",
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

_CONF_COLORS = {
    "HIGH":     "#22c55e",
    "MODERATE": "#3b82f6",
    "LOW":      "#f59e0b",
    "MINIMAL":  "#ef4444",
}


def _badge(label: str, color: str, icon: str = "", large: bool = False) -> str:
    size = "1rem" if large else "0.80rem"
    pad = "6px 16px" if large else "3px 10px"
    return (
        f'<span style="background:{color};color:#fff;padding:{pad};'
        f'border-radius:14px;font-weight:700;font-size:{size};'
        f'display:inline-block;margin:2px;letter-spacing:0.5px;">'
        f'{icon} {label}</span>'
    )


def _score_bar(label: str, value: float, color: str, max_val: float = 100.0) -> str:
    pct = min(value / max_val * 100.0, 100.0)
    return f"""
<div style="margin-bottom:10px;">
  <div style="display:flex;justify-content:space-between;margin-bottom:3px;">
    <span style="font-size:0.82rem;color:#94a3b8;">{label}</span>
    <span style="font-size:0.82rem;color:#e2e8f0;font-weight:700;">{value:.1f}</span>
  </div>
  <div style="background:#1e293b;border-radius:6px;height:8px;overflow:hidden;">
    <div style="width:{pct:.1f}%;background:{color};height:8px;border-radius:6px;
         transition:width 0.3s ease;"></div>
  </div>
</div>"""


def render_institutional_dashboard(ctx: OrchestrationContext) -> None:
    """
    Renders the full 5-Tier NexusBot V3 Institutional Dashboard.
    """
    if ctx is None:
        st.warning("No analysis context available. Run the intelligence pipeline first.")
        return

    # Unpack context sections
    h1   = ctx.h1_structure or {}
    h4   = ctx.h4_structure or {}
    sess = ctx.session_context or {}
    mem  = ctx.market_memory or {}
    trans = ctx.regime_transition or {}
    sq   = ctx.signal_quality or {}
    ready = ctx.execution_readiness or {}
    conf = ctx.confidence_hierarchy or {}
    risk = ctx.institutional_risk or {}
    contra = ctx.contradiction_engine or {}
    sat  = ctx.signal_saturation or {}
    candle = ctx.candlestick_intelligence or {}
    narr = ctx.narrative_compression or {}
    m5   = ctx.m5_precision or {}
    clock = ctx.execution_clock or {}
    explainer = ctx.market_explainer or {}
    tournament = ctx.tournament_results or []

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 1 — EXECUTIVE COMMAND CENTER
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("### 🎯 Tier 1 — Executive Command Center")

    exec_col1, exec_col2, exec_col3 = st.columns([1.2, 1.2, 1])

    with exec_col1:
        # Execution Readiness Panel
        exec_state  = ready.get("execution_state", "WATCHLIST")
        readiness   = float(ready.get("readiness_score", 0.0))
        state_color = _STATE_COLORS.get(exec_state, "#94a3b8")

        st.markdown(
            f"""<div style="background:linear-gradient(135deg,#0f172a,#1e293b);
            border:2px solid {state_color};border-radius:14px;padding:20px;
            box-shadow:0 0 20px {state_color}33;">
            <div style="font-size:0.75rem;color:#94a3b8;letter-spacing:2px;
            text-transform:uppercase;margin-bottom:8px;">EXECUTION READINESS</div>
            <div style="font-size:2.8rem;font-weight:900;color:{state_color};
            line-height:1;">{readiness:.0f}<span style="font-size:1rem;color:#64748b;">/100</span></div>
            <div style="margin-top:10px;">
            {_badge(exec_state, state_color, "🟢" if exec_state=="READY" else ("🟡" if exec_state=="WATCHLIST" else "🔴"), large=True)}
            </div></div>""",
            unsafe_allow_html=True,
        )

    with exec_col2:
        # Institutional Risk Panel
        risk_level  = risk.get("risk_level", "MODERATE")
        risk_score  = float(risk.get("risk_score", 50.0))
        risk_color  = _RISK_COLORS.get(risk_level, "#94a3b8")

        st.markdown(
            f"""<div style="background:linear-gradient(135deg,#0f172a,#1e293b);
            border:2px solid {risk_color};border-radius:14px;padding:20px;
            box-shadow:0 0 20px {risk_color}33;">
            <div style="font-size:0.75rem;color:#94a3b8;letter-spacing:2px;
            text-transform:uppercase;margin-bottom:8px;">INSTITUTIONAL RISK</div>
            <div style="font-size:2.8rem;font-weight:900;color:{risk_color};
            line-height:1;">{risk_score:.0f}<span style="font-size:1rem;color:#64748b;">/100</span></div>
            <div style="margin-top:10px;">
            {_badge(risk_level, risk_color, "💀" if risk_level in ["CRITICAL","HIGH"] else "✅", large=True)}
            </div></div>""",
            unsafe_allow_html=True,
        )

    with exec_col3:
        # Confidence Hierarchy Panel
        conf_score  = float(conf.get("weighted_confidence_score", 0.0))
        conf_level  = conf.get("confidence_level", "MODERATE")
        conf_color  = _CONF_COLORS.get(conf_level, "#94a3b8")
        st.markdown(
            f"""<div style="background:linear-gradient(135deg,#0f172a,#1e293b);
            border:2px solid {conf_color};border-radius:14px;padding:20px;
            box-shadow:0 0 20px {conf_color}33;">
            <div style="font-size:0.75rem;color:#94a3b8;letter-spacing:2px;
            text-transform:uppercase;margin-bottom:8px;">CONFIDENCE</div>
            <div style="font-size:2.8rem;font-weight:900;color:{conf_color};
            line-height:1;">{conf_score:.0f}<span style="font-size:1rem;color:#64748b;">/100</span></div>
            <div style="margin-top:10px;">
            {_badge(conf_level, conf_color, "⭐", large=True)}
            </div></div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Second row: H4 Macro + Session + Contradiction co-equal
    meta_c1, meta_c2, meta_c3, meta_c4 = st.columns(4)

    macro_dir = h4.get("macro_direction", "NEUTRAL")
    macro_str = float(h4.get("macro_strength", 0.0))
    inst_bias = h4.get("institutional_bias", "NEUTRAL")
    macro_color = _DIR_COLORS.get(macro_dir, "#94a3b8")

    with meta_c1:
        st.metric("H4 Macro Direction", f"{_DIR_ICONS.get(macro_dir,'◆')} {macro_dir}")
        st.caption(f"ADX={macro_str:.0f} | {inst_bias.replace('_',' ')}")

    with meta_c2:
        session = sess.get("current_session", "ASIAN").replace("_", "/")
        liquidity = sess.get("session_liquidity", "LOW")
        liq_color = "#22c55e" if liquidity == "HIGH" else ("#f59e0b" if liquidity == "MEDIUM" else "#ef4444")
        st.metric("Session", session)
        st.caption(f"Liquidity: {liquidity}")

    with meta_c3:
        contra_score = float(contra.get("contradiction_score", 0.0))
        n_conflicts  = int(contra.get("conflict_count", 0))
        contra_color = "#ef4444" if contra_score > 50 else ("#f59e0b" if contra_score > 25 else "#22c55e")
        st.metric("Contradictions", f"{n_conflicts} detected")
        st.caption(f"Penalty score: {contra_score:.0f}/100")

    with meta_c4:
        exec_timing = clock.get("execution_timing", "SUBOPTIMAL")
        timing_score = float(clock.get("timing_score", 0.0))
        is_premium = bool(clock.get("is_premium_window", False))
        t_color = "#22c55e" if is_premium else ("#f59e0b" if exec_timing == "ACCEPTABLE" else "#94a3b8")
        st.metric("Timing Window", exec_timing)
        st.caption(f"Score: {timing_score:.0f}/100 {'⭐' if is_premium else ''}")

    st.divider()

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 2 — KEY INTELLIGENCE INSIGHTS (Narrative Compression)
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("### 💡 Tier 2 — Institutional Intelligence Briefing")

    if narr:
        exec_summary = narr.get("executive_summary", "")
        if exec_summary:
            st.info(exec_summary)

        narr_col1, narr_col2 = st.columns(2)

        with narr_col1:
            st.markdown("#### 📈 Key Opportunities")
            for opp in narr.get("key_opportunities", []):
                st.markdown(opp)

        with narr_col2:
            st.markdown("#### ⚠️ Key Risks")
            for r in narr.get("key_risks", []):
                st.markdown(r)

        st.markdown(f"**⏰ Timing:** {narr.get('timing_summary','')}")
        deploy_ctx = narr.get("deployment_context", "")
        if deploy_ctx:
            deploy_color = "#22c55e22" if "ADVISED" in deploy_ctx else ("#ef444422" if "AVOID" in deploy_ctx else "#3b82f622")
            st.markdown(
                f'<div style="background:{deploy_color};border-radius:10px;padding:14px 18px;'
                f'border-left:4px solid {"#22c55e" if "ADVISED" in deploy_ctx else ("#ef4444" if "AVOID" in deploy_ctx else "#3b82f6")};">'
                f'{deploy_ctx}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("Narrative compression not yet computed.")

    st.divider()

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 3 — STRATEGY WAR ROOM
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("### 🏆 Tier 3 — Strategy War Room")

    if tournament:
        war_col1, war_col2 = st.columns([1.5, 1])

        with war_col1:
            # Winner card
            winner = tournament[0]
            win_name  = winner.get("strategy", "N/A")
            win_score = float(winner.get("market_fit_score", 0.0))
            supported = winner.get("supported", False)
            breakdown = winner.get("score_breakdown", {})

            st.markdown(
                f"""<div style="background:linear-gradient(135deg,#172554,#0f172a);
                border:2px solid #3b82f6;border-radius:14px;padding:20px;
                box-shadow:0 0 20px #3b82f640;margin-bottom:14px;">
                <div style="font-size:0.75rem;color:#60a5fa;letter-spacing:2px;
                text-transform:uppercase;">🏆 TOURNAMENT WINNER</div>
                <div style="font-size:1.8rem;font-weight:900;color:#f8fafc;margin:6px 0;">{win_name}</div>
                <div style="font-size:2.4rem;font-weight:900;color:#3b82f6;">{win_score:.1f}
                <span style="font-size:1rem;color:#64748b;">/100</span></div>
                {_badge("REGIME MATCH" if supported else "REGIME MISMATCH",
                       "#22c55e" if supported else "#f59e0b")}
                </div>""",
                unsafe_allow_html=True,
            )

            # Score breakdown bars
            if breakdown:
                st.markdown("**Score Breakdown:**")
                st.markdown(
                    _score_bar("Base Strategy Fit", float(breakdown.get("base", 0.0)), "#3b82f6") +
                    _score_bar("H4 Macro Bonus", float(breakdown.get("h4_bonus", 0.0)), "#22c55e", 20.0) +
                    _score_bar("H1 Alignment Bonus", float(breakdown.get("h1_bonus", 0.0)), "#10b981", 25.0) +
                    _score_bar("M15 Execution Bonus", float(breakdown.get("m15_bonus", 0.0)), "#6366f1", 20.0) +
                    _score_bar("Session Bonus", float(breakdown.get("session_bonus", 0.0)), "#8b5cf6", 10.0),
                    unsafe_allow_html=True,
                )
                # Penalties
                pen_total = abs(float(breakdown.get("fatigue_pen", 0.0))) + abs(float(breakdown.get("noise_pen", 0.0))) + abs(float(breakdown.get("lateness_pen", 0.0)))
                if pen_total > 0:
                    st.markdown(
                        _score_bar(f"Active Penalties (−{pen_total:.1f})", pen_total, "#ef4444", 30.0),
                        unsafe_allow_html=True,
                    )

        with war_col2:
            # Contradiction overlay
            st.markdown("**⚡ Active Conflicts:**")
            conflicts = contra.get("conflicts", [])
            if conflicts:
                for c in conflicts[:4]:
                    st.markdown(
                        f'<div style="background:#1e293b;border-left:3px solid #ef4444;'
                        f'padding:8px 12px;border-radius:6px;font-size:0.80rem;color:#fca5a5;'
                        f'margin-bottom:6px;">{c[:100]}{"..." if len(c)>100 else ""}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.success("No structural conflicts detected.")

            # Signal Saturation
            st.markdown("**📡 Signal Saturation:**")
            eff = int(sat.get("effective_signal_count", 0))
            raw = int(sat.get("raw_signal_count", 0))
            sat_lvl = sat.get("saturation_level", "NORMAL")
            sat_color = "#22c55e" if sat_lvl == "NORMAL" else ("#f59e0b" if sat_lvl == "MODERATE" else "#ef4444")
            st.markdown(
                f'<div style="background:#1e293b;border-radius:10px;padding:12px 16px;">'
                f'<div style="color:#94a3b8;font-size:0.78rem;">Raw Signals: <b style="color:#e2e8f0;">{raw}</b> → '
                f'Effective: <b style="color:#22c55e;">{eff}</b></div>'
                f'<div style="margin-top:6px;">{_badge(sat_lvl, sat_color)}</div>'
                f'<div style="color:#94a3b8;font-size:0.75rem;margin-top:4px;">Saturation penalty: -{sat.get("saturation_penalty",0):.0f} pts</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        with st.expander("📋 Full Strategy Rankings", expanded=False):
            for item in tournament:
                rank = item.get("rank", "?")
                name = item.get("strategy", "N/A")
                score = float(item.get("market_fit_score", 0.0))
                match = item.get("regime_match", False)
                color = "#22c55e" if rank == 1 else ("#3b82f6" if rank == 2 else "#94a3b8")
                
                conf_break = item.get("confidence_breakdown", {})
                conf_break_str = ""
                if conf_break:
                    conf_break_str = f"Trend: {conf_break.get('trend_strength',0.0):.0f}% | Vol: {conf_break.get('volatility_alignment',0.0):.0f}% | Str: {conf_break.get('structure_quality',0.0):.0f}% | Ready: {conf_break.get('execution_readiness',0.0):.0f}% | Time: {conf_break.get('timing_alignment',0.0):.0f}%"

                st.markdown(
                    f'<div style="background:#111827;border-radius:8px;padding:10px 14px;margin-bottom:6px;">'
                    f'<div style="display:flex;align-items:center;justify-content:space-between;">'
                    f'<span style="color:{color};font-weight:700;">#{rank} {name}</span>'
                    f'<span>'
                    f'{_badge("FIT MATCH" if match else "MISMATCH", "#22c55e" if match else "#94a3b8")}'
                    f'<b style="color:#e2e8f0;font-size:1.1rem;margin-left:10px;">{score:.1f}</b>'
                    f'</span>'
                    f'</div>'
                    f'{f"<div style=\'font-size:0.75rem;color:#3b82f6;margin-top:4px;border-top:1px solid #1e293b;padding-top:4px;\'>{conf_break_str}</div>" if conf_break_str else ""}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # ═══════════════════════════════════════════════════════════════════════
        # TIER 3.5 — AUTO TRADE DEPLOYMENT COMMAND CENTER
        # ═══════════════════════════════════════════════════════════════════════
        st.markdown("### 🚀 Tier 3.5 — Auto Trade Deployment")

        # ── session state defaults ────────────────────────────────────────────
        for _k, _v in {
            "atde_mode":         "ADVISORY",
            "atde_profile":      "Momentum Moderate",
            "atde_strategy":     "Momentum Continuation",
            "atde_active":       False,
            "atde_positions":    [],
            "atde_drawdown":     0.0,
            "atde_consec_loss":  0,
            "atde_last_strat":   None,
        }.items():
            if _k not in st.session_state:
                st.session_state[_k] = _v

        # ── load profiles ─────────────────────────────────────────────────────
        from deployment.deployment_profile import get_preset, PRESETS, AutoTradeDeploymentProfile
        from runtime.deployment_profile import load_all_profiles
        from engine.strategy_registry import list_strategy_names, get_strategy_by_name

        _all_profiles = list(PRESETS.keys())
        _custom_map: dict = {}
        try:
            for _sp in load_all_profiles():
                _cn = f"Custom: {_sp.strategy} ({_sp.profile_id})"
                _all_profiles.append(_cn)
                _rc = (_sp.parameters.get("minimum_confidence")
                       or _sp.full_parameters.get("minimum_confidence")
                       or _sp.deployment_score or 50.0)
                _as = _sp.parameters.get("allowed_sessions",
                       _sp.full_parameters.get("allowed_sessions",
                       ["LONDON", "NEW_YORK", "ASIAN", "NY_OVERLAP"]))
                _custom_map[_cn] = AutoTradeDeploymentProfile(
                    name=_cn,
                    minimum_confidence=float(_rc),
                    max_spread=float(_sp.parameters.get("spread", _sp.full_parameters.get("spread", 25.0))),
                    max_positions=int(_sp.parameters.get("max_parallel_positions", _sp.full_parameters.get("max_parallel_positions", 2))),
                    allowed_sessions=_as if isinstance(_as, list) else ["LONDON", "NEW_YORK", "ASIAN", "NY_OVERLAP"],
                    risk_per_trade=float(_sp.parameters.get("risk_percent", _sp.full_parameters.get("risk_percent", 0.5)))
                )
        except Exception:
            pass

        if st.session_state["atde_profile"] not in _all_profiles:
            st.session_state["atde_profile"] = _all_profiles[0]
        _pcfg = _custom_map.get(st.session_state["atde_profile"]) or get_preset(st.session_state["atde_profile"])

        # ── market state helpers ───────────────────────────────────────────────
        _h4_raw = h4.get("macro_direction", "NEUTRAL")
        _h1_raw = h1.get("structure_direction", h1.get("macro_direction", "NEUTRAL"))
        _mkt_dir = "BUY"  if (_h4_raw if _h4_raw != "NEUTRAL" else _h1_raw) in ("BULLISH", "BUY")  else \
                   "SELL" if (_h4_raw if _h4_raw != "NEUTRAL" else _h1_raw) in ("BEARISH", "SELL") else "NEUTRAL"
        _atr_val = float(h1.get("_atr", h1.get("atr", 15.0)))

        with st.expander("⚙️ Deployment Command Center", expanded=True):

            # ── ROW 1 : three settings columns ────────────────────────────────
            _cc1, _cc2, _cc3 = st.columns([1.1, 1, 1])

            with _cc1:
                st.markdown("##### ⚙️ Settings")
                st.session_state["atde_mode"] = st.selectbox(
                    "Mode", ["ADVISORY", "SEMI_AUTO", "LIVE"],
                    index=["ADVISORY", "SEMI_AUTO", "LIVE"].index(st.session_state["atde_mode"]),
                    key="atde_mode_sel"
                )
                st.session_state["atde_profile"] = st.selectbox(
                    "Profile", _all_profiles,
                    index=_all_profiles.index(st.session_state["atde_profile"]),
                    key="atde_profile_sel"
                )
                _pcfg = _custom_map.get(st.session_state["atde_profile"]) or get_preset(st.session_state["atde_profile"])

                _min_conf = st.number_input("Min Confidence (%)", 0.0, 100.0,
                    float(_pcfg.minimum_confidence), 1.0, key="atde_min_conf")
                _max_sp   = st.number_input("Max Spread (pts)", 0.0, 500.0,
                    float(_pcfg.max_spread), 1.0, key="atde_max_sp")
                _lot      = st.number_input("Lot Size", 0.01, 10.0,
                    max(0.01, float(_pcfg.risk_per_trade)), 0.01, key="atde_lot")

                _strat_list = list_strategy_names()
                if st.session_state["atde_strategy"] not in _strat_list:
                    st.session_state["atde_strategy"] = _strat_list[0]
                st.session_state["atde_strategy"] = st.selectbox(
                    "Target Strategy", _strat_list,
                    index=_strat_list.index(st.session_state["atde_strategy"]),
                    key="atde_strat_sel"
                )
                st.session_state["atde_active"] = st.checkbox(
                    "Enable Engine", st.session_state["atde_active"], key="atde_enable")
                _ec = "#22c55e" if st.session_state["atde_active"] else "#ef4444"
                _et = "🟢 RUNNING" if st.session_state["atde_active"] else "🔴 STOPPED"
                st.markdown(
                    f'<div style="background:#0f172a;border:1px solid {_ec};border-radius:8px;'
                    f'padding:7px;text-align:center;font-weight:700;color:{_ec};font-size:0.82rem;">'
                    f'{_et}</div>', unsafe_allow_html=True)

            with _cc2:
                st.markdown("##### 🚨 Circuit Breakers")
                _sp_val    = float(h1.get("_spread_pts", _max_sp - 3.0))
                _sp_ok     = _sp_val <= _max_sp
                _dd_ok     = st.session_state["atde_drawdown"] < 5.0
                _cl_ok     = st.session_state["atde_consec_loss"] < 3
                _vol_ratio = float(h1.get("_atr_ratio", 1.0))
                _vol_ok    = _vol_ratio <= 2.5
                _all_ok    = _sp_ok and _dd_ok and _cl_ok and _vol_ok

                for _lbl, _val_str, _ok in [
                    ("Spread",         f"{_sp_val:.0f} / {_max_sp:.0f} pts",              _sp_ok),
                    ("Volatility",     f"{h1.get('volatility_state','NORMAL')} ({_vol_ratio:.2f}x)", _vol_ok),
                    ("Daily Drawdown", f"{st.session_state['atde_drawdown']:.2f}% / 5%",  _dd_ok),
                    ("Consec Losses",  f"{st.session_state['atde_consec_loss']} / 3",     _cl_ok),
                ]:
                    _cc = "#22c55e" if _ok else "#ef4444"
                    st.markdown(
                        f'<div style="background:#0f172a;border-left:3px solid {_cc};'
                        f'border-radius:5px;padding:6px 10px;margin-bottom:5px;'
                        f'display:flex;justify-content:space-between;">'
                        f'<span style="color:#94a3b8;font-size:0.79rem;">{_lbl}</span>'
                        f'<span style="color:{_cc};font-size:0.79rem;font-weight:700;">{"✅" if _ok else "🚨"} {_val_str}</span>'
                        f'</div>', unsafe_allow_html=True)

                if _all_ok:
                    st.success("✅ All circuits clear")
                else:
                    st.error("🚨 CIRCUIT BREAKER — Trading locked")

                if st.button("🚨 Flatten All Positions", key="atde_flatten", use_container_width=True):
                    st.session_state["atde_positions"]  = []
                    st.session_state["atde_drawdown"]   = 0.0
                    st.session_state["atde_consec_loss"] = 0
                    st.session_state["atde_last_strat"] = None
                    st.success("All cleared.")

            with _cc3:
                st.markdown("##### 📡 Intent Queue")

                if not st.session_state["atde_active"]:
                    st.info("Engine stopped. Enable to activate.")
                elif not tournament:
                    st.warning("No tournament data yet.")
                elif not _all_ok:
                    st.error("Circuits locked. No orders.")
                else:
                    _w       = tournament[0]
                    _wname   = _w.get("strategy", "Unknown")
                    _wscore  = float(_w.get("market_fit_score", 0.0))
                    _above   = _wscore >= _min_conf
                    _dup     = st.session_state["atde_last_strat"] == _wname
                    _maxed   = len(st.session_state["atde_positions"]) >= _pcfg.max_positions
                    _canDep  = _above and not _dup and not _maxed

                    _ic = "#22c55e" if _canDep else "#ef4444"
                    _il = ("READY" if _canDep else
                           "MAX POSITIONS" if _maxed else
                           "DUPLICATE" if _dup else "BELOW THRESHOLD")
                    _dir_c = "#22c55e" if _mkt_dir == "BUY" else "#ef4444" if _mkt_dir == "SELL" else "#94a3b8"

                    st.markdown(
                        f'<div style="background:#0f172a;border:1px solid {_ic}44;border-radius:10px;padding:11px;">'
                        f'<div style="font-size:0.70rem;color:#94a3b8;letter-spacing:1px;">TOURNAMENT WINNER</div>'
                        f'<div style="font-size:1.0rem;font-weight:800;color:#f1f5f9;margin:2px 0;">{_wname}</div>'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'<span style="color:#94a3b8;font-size:0.77rem;">Conf <b style="color:#e2e8f0;">{_wscore:.1f}%</b>'
                        f' / min <b style="color:#64748b;">{_min_conf:.1f}%</b></span>'
                        f'<span style="background:{_ic};color:#fff;font-size:0.68rem;font-weight:700;'
                        f'padding:2px 8px;border-radius:8px;">{_il}</span></div>'
                        f'<div style="font-size:0.75rem;color:#94a3b8;margin-top:5px;">'
                        f'Dir: <b style="color:{_dir_c};">{_mkt_dir}</b>'
                        f' &nbsp;·&nbsp; Lot: <b style="color:#e2e8f0;">{_lot:.2f}</b>'
                        f' &nbsp;·&nbsp; ATR: <b style="color:#e2e8f0;">{_atr_val:.2f}</b>'
                        f'</div></div>', unsafe_allow_html=True)

                    # ── helper: place order + build position record ───────────
                    def _do_place():
                        from runtime.mt5_connector import MT5Connector
                        _sym = st.session_state.get("runtime_symbol", "UNKNOWN")
                        _conn = MT5Connector()
                        _conn.initialize()

                        # live entry price from MT5 tick, fallback to last h1 close
                        _entry = 0.0
                        try:
                            if not _conn.is_simulated:
                                import MetaTrader5 as _mt5lib
                                _tick = _mt5lib.symbol_info_tick(_sym)
                                if _tick:
                                    _entry = float(_tick.ask if _mkt_dir == "BUY" else _tick.bid)
                        except Exception:
                            pass
                        if _entry <= 0:
                            _entry = float(h1.get("_last_price", h1.get("close", 0.0)))

                        # SL / TP via strategy
                        _sl, _tp = 0.0, 0.0
                        try:
                            _so = get_strategy_by_name(_wname)
                            _sl, _tp = _so.calculate_sl_tp(_entry, _atr_val, _mkt_dir)
                            _sl, _tp = round(float(_sl), 5), round(float(_tp), 5)
                        except Exception:
                            _sl = round(_entry - _atr_val * 1.8, 5) if _mkt_dir == "BUY" else round(_entry + _atr_val * 1.8, 5)
                            _tp = round(_entry + _atr_val * 3.0, 5) if _mkt_dir == "BUY" else round(_entry - _atr_val * 3.0, 5)

                        _res = _conn.place_order(
                            symbol=_sym, direction=_mkt_dir, lot=_lot,
                            sl=_sl, tp=_tp,
                            comment=f"NXB {_wname[:9]} {_mkt_dir[:1]}"
                        )
                        _tkt  = _res.get("ticket", -1)
                        _stat = _res.get("status", "UNKNOWN")

                        if _tkt > 0:
                            st.session_state["atde_positions"].append({
                                "ticket":      _tkt,
                                "strategy":    _wname,
                                "direction":   _mkt_dir,
                                "entry_price": _entry,
                                "sl":          _sl,
                                "tp":          _tp,
                                "lot":         _lot,
                                "confidence":  _wscore,
                                "mt5_status":  _stat,
                                "live_pnl":    0.0,
                            })
                            st.session_state["atde_last_strat"] = _wname
                            if _stat == "SIMULATED":
                                st.warning(f"⚠️ SIM ticket #{_tkt} — MT5 not connected\n"
                                           f"Dir: {_mkt_dir} | Lot: {_lot:.2f} | SL: {_sl:.5f} | TP: {_tp:.5f}")
                            else:
                                st.success(f"✅ LIVE order placed | Ticket #{_tkt}\n"
                                           f"{_mkt_dir} {_lot:.2f} lots | Entry: {_entry:.5f} | SL: {_sl:.5f} | TP: {_tp:.5f}")
                        else:
                            st.error(f"❌ Order FAILED: {_res.get('error') or _res.get('comment','Unknown')}")

                    if st.session_state["atde_mode"] == "ADVISORY":
                        if _canDep:
                            st.info(f"💡 Advisory: {_mkt_dir} via {_wname} ({_wscore:.1f}%)")

                    elif st.session_state["atde_mode"] == "SEMI_AUTO":
                        if _canDep:
                            if st.button(f"✅ Place {_mkt_dir} Order", key="atde_semi_btn", use_container_width=True):
                                _do_place()
                        elif not _above:
                            st.warning(f"Confidence {_wscore:.1f}% below {_min_conf:.1f}%")

                    elif st.session_state["atde_mode"] == "LIVE":
                        if _canDep:
                            _do_place()
                        elif _dup:
                            st.info(f"⏸ '{_wname}' already deployed. Close position to redeploy.")
                        elif not _above:
                            st.warning(f"Confidence {_wscore:.1f}% below {_min_conf:.1f}%")

            # ── ROW 2 : positions panel ───────────────────────────────────────
            st.markdown("---")
            _pcnt = len(st.session_state["atde_positions"])
            _plbl = "📂 Live Positions (MT5)" if st.session_state["atde_mode"] == "LIVE" else "📂 Positions"
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                f'<b style="color:#e2e8f0;">{_plbl}</b>'
                f'<span style="background:#1e293b;color:#94a3b8;font-size:0.73rem;'
                f'padding:2px 10px;border-radius:10px;">{_pcnt} / {_pcfg.max_positions}</span>'
                f'</div>', unsafe_allow_html=True)

            if not st.session_state["atde_positions"]:
                st.markdown(
                    '<div style="background:#0f172a;border:1px dashed #1e293b;border-radius:8px;'
                    'padding:18px;text-align:center;color:#475569;font-size:0.83rem;">No open positions</div>',
                    unsafe_allow_html=True)
            else:
                for _pos in list(st.session_state["atde_positions"]):
                    _pt  = _pos.get("ticket")
                    _pst = _pos.get("strategy", "?")
                    _pd  = _pos.get("direction", "?")
                    _pe  = float(_pos.get("entry_price", 0.0))
                    _psl = float(_pos.get("sl", 0.0))
                    _ptp = float(_pos.get("tp", 0.0))
                    _plot = float(_pos.get("lot", 0.0))
                    _pco = float(_pos.get("confidence", 0.0))
                    _pmt = _pos.get("mt5_status", "?")
                    _ppnl= float(_pos.get("live_pnl", 0.0))

                    _pc  = "#22c55e" if _ppnl >= 0 else "#ef4444"
                    _dc  = "#22c55e" if _pd == "BUY" else "#ef4444"
                    _mc  = "#22c55e" if _pmt == "PLACED" else "#f59e0b" if _pmt == "SIMULATED" else "#94a3b8"
                    _ml  = "🟢 LIVE" if _pmt == "PLACED" else "🟡 SIM" if _pmt == "SIMULATED" else _pmt
                    _sls = f"{_psl:.5f}" if _psl else "—"
                    _tps = f"{_ptp:.5f}" if _ptp else "—"

                    _pa, _pb = st.columns([6, 1])
                    with _pa:
                        st.markdown(
                            f'<div style="background:#111827;border-left:3px solid {_pc};'
                            f'border-radius:8px;padding:11px 14px;margin-bottom:6px;">'
                            f'<div style="display:flex;justify-content:space-between;">'
                            f'<div><b style="color:#f1f5f9;">#{_pt} {_pst}</b>'
                            f'<span style="background:{_mc};color:#fff;font-size:0.68rem;font-weight:700;'
                            f'padding:1px 6px;border-radius:7px;margin-left:6px;">{_ml}</span><br>'
                            f'<span style="color:{_dc};font-weight:700;font-size:0.80rem;">{_pd}</span>'
                            f'<span style="color:#64748b;font-size:0.73rem;"> @ {_pe:.5f} | {_plot:.2f} lots</span></div>'
                            f'<div style="text-align:right;">'
                            f'<b style="color:{_pc};font-size:1.1rem;">${_ppnl:+.2f}</b><br>'
                            f'<span style="color:#64748b;font-size:0.70rem;">{_pco:.1f}% conf</span></div></div>'
                            f'<div style="display:flex;gap:18px;margin-top:7px;border-top:1px solid #1e293b;padding-top:5px;">'
                            f'<span style="font-size:0.73rem;color:#94a3b8;">SL <b style="color:#ef4444;">{_sls}</b></span>'
                            f'<span style="font-size:0.73rem;color:#94a3b8;">TP <b style="color:#22c55e;">{_tps}</b></span>'
                            f'</div></div>', unsafe_allow_html=True)
                    with _pb:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("✖", key=f"atde_close_{_pt}", use_container_width=True):
                            st.session_state["atde_positions"] = [
                                p for p in st.session_state["atde_positions"] if p.get("ticket") != _pt]
                            if st.session_state["atde_last_strat"] == _pst:
                                st.session_state["atde_last_strat"] = None
                            st.rerun()

        st.divider()

        # ═══════════════════════════════════════════════════════════════════════
        # TIER 3.6 — DECISION OBSERVABILITY & REPLAY
        # ═══════════════════════════════════════════════════════════════════════
        st.markdown("### 🔎 Tier 3.6 — Decision Observability & Replay")

        _ob1, _ob2 = st.columns(2)
        with _ob1:
            with st.expander("📊 Regime & Eligible Strategies", expanded=True):
                _ms = h1.get("macro_regime", "RANGING")
                st.markdown(
                    f'<div style="background:#0f172a;border:1px solid #3b82f6;border-radius:10px;padding:12px;">'
                    f'<div style="font-size:0.72rem;color:#94a3b8;letter-spacing:1px;">CURRENT REGIME</div>'
                    f'<div style="font-size:1.5rem;font-weight:800;color:#3b82f6;">{_ms.replace("_"," ")}</div>'
                    f'</div>', unsafe_allow_html=True)
                st.markdown("")

                _active_strats = getattr(ctx, "active_strategies", []) or []
                if _active_strats:
                    for _sn in _active_strats:
                        _sf = next((t.get("market_fit_score", 0) for t in tournament if t.get("strategy") == _sn), 0)
                        st.markdown(
                            f'<div style="background:#111827;border-radius:6px;padding:7px 11px;margin-bottom:4px;'
                            f'display:flex;justify-content:space-between;">'
                            f'<span style="color:#22c55e;font-weight:600;">{_sn}</span>'
                            f'<b style="color:#e2e8f0;">{float(_sf):.1f} FIT</b></div>',
                            unsafe_allow_html=True)
                else:
                    st.caption("No eligible strategies.")

            with st.expander("❌ Rejected Strategies", expanded=False):
                _rejs = explainer.get("strategy_rejections", {}) or {}
                if _rejs:
                    for _rn, _rr in _rejs.items():
                        st.markdown(
                            f'<div style="background:#111827;border-left:3px solid #ef4444;'
                            f'border-radius:6px;padding:8px 11px;margin-bottom:5px;">'
                            f'<b style="color:#ef4444;">{_rn}</b><br>'
                            f'<span style="font-size:0.78rem;color:#94a3b8;">{_rr}</span></div>',
                            unsafe_allow_html=True)
                else:
                    st.success("No strategies rejected.")

        with _ob2:
            with st.expander("🏅 Full Tournament Rankings", expanded=True):
                for _ri, _rt in enumerate(tournament, 1):
                    _rn  = _rt.get("strategy", "N/A")
                    _rs  = float(_rt.get("market_fit_score", 0.0))
                    _rbd = _rt.get("score_breakdown", {})
                    _rcb = _rt.get("confidence_breakdown", {})
                    _rc  = "#3b82f6" if _ri == 1 else "#64748b"
                    _rbs = ""
                    if _rbd:
                        _rbs = (f"Base: {_rbd.get('base',0):.1f} | "
                                f"H4: {_rbd.get('h4_bonus',0):+.1f} | "
                                f"H1: {_rbd.get('h1_bonus',0):+.1f} | "
                                f"M15: {_rbd.get('m15_bonus',0):+.1f}")
                        _pen = abs(float(_rbd.get("fatigue_pen", 0))) + abs(float(_rbd.get("noise_pen", 0)))
                        if _pen:
                            _rbs += f" | Pen: -{_pen:.1f}"
                    _rcs = ""
                    if _rcb:
                        _rcs = (f"Trend {_rcb.get('trend_strength',0):.0f}% | "
                                f"Vol {_rcb.get('volatility_alignment',0):.0f}% | "
                                f"Str {_rcb.get('structure_quality',0):.0f}% | "
                                f"Ready {_rcb.get('execution_readiness',0):.0f}%")
                    st.markdown(
                        f'<div style="background:#0f172a;border:1px solid #1e293b;border-radius:8px;'
                        f'padding:9px 13px;margin-bottom:5px;">'
                        f'<div style="display:flex;justify-content:space-between;">'
                        f'<span style="font-weight:700;color:#f1f5f9;">#{_ri} {_rn}</span>'
                        f'<b style="color:{_rc};">{_rs:.1f}</b></div>'
                        f'{f"<div style=font-size:0.73rem;color:#64748b;margin-top:3px;>{_rbs}</div>" if _rbs else ""}'
                        f'{f"<div style=font-size:0.71rem;color:#3b82f6;margin-top:2px;border-top:1px solid #1e293b;padding-top:3px;>{_rcs}</div>" if _rcs else ""}'
                        f'</div>', unsafe_allow_html=True)

            with st.expander("🎯 Execution Candidates", expanded=False):
                _cands = getattr(ctx, "execution_candidates", []) or []
                if _cands:
                    for _c in _cands:
                        _cd  = _c.get("direction", "NEUTRAL")
                        _cc2 = "#22c55e" if _cd in ("BUY", "BULLISH") else "#ef4444" if _cd in ("SELL", "BEARISH") else "#94a3b8"
                        _ccf = float(_c.get("confidence", 0.0))
                        _crs = _c.get("reasons", [])
                        st.markdown(
                            f'<div style="background:#111827;border-left:3px solid {_cc2};'
                            f'border-radius:6px;padding:10px 13px;margin-bottom:6px;">'
                            f'<div style="display:flex;justify-content:space-between;">'
                            f'<b style="color:#e2e8f0;">{_c.get("strategy","?")}</b>'
                            f'<span style="background:{_cc2};color:#fff;font-size:0.70rem;font-weight:700;'
                            f'padding:1px 7px;border-radius:7px;">{_cd}</span></div>'
                            f'<div style="color:#f59e0b;font-size:0.82rem;font-weight:700;margin-top:3px;">'
                            f'Conf: {_ccf:.1f}%</div>'
                            f'<div style="font-size:0.76rem;color:#94a3b8;margin-top:3px;">'
                            f'{"<br>".join(f"• {r}" for r in _crs)}</div>'
                            f'</div>', unsafe_allow_html=True)
                else:
                    st.info("No execution candidates under current state.")


    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 4 — MARKET DIAGNOSTICS
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("### 🔬 Tier 4 — Market Diagnostics")

    diag_tab1, diag_tab2, diag_tab3, diag_tab4 = st.tabs([
        "📊 Regime Transition", "🕐 Session & Memory", "🕯️ Candlestick", "🚦 Risk Breakdown"
    ])

    with diag_tab1:
        trans_state = trans.get("transition_state", "STABLE")
        trans_prob  = float(trans.get("transition_probability", 0.0))
        exp_phase   = bool(trans.get("expansion_phase", False))
        comp_phase  = bool(trans.get("compression_phase", False))
        exh_val     = float(trans.get("trend_exhaustion", 0.0))
        bkout_val   = float(trans.get("breakout_loading", 0.0))

        t_state_colors = {
            "EXPANSION_BEGINNING": "#22c55e",
            "BREAKOUT_LOADING":    "#f59e0b",
            "TREND_EXHAUSTION":    "#ef4444",
            "DISTRIBUTION_CHOP":  "#f97316",
            "COMPRESSION_REGIME": "#3b82f6",
            "STABLE":              "#94a3b8",
        }
        t_col1, t_col2 = st.columns(2)
        with t_col1:
            state_c = t_state_colors.get(trans_state, "#94a3b8")
            st.markdown(
                f'<div style="background:#111827;border-left:4px solid {state_c};'
                f'padding:14px;border-radius:8px;">'
                f'<div style="color:#94a3b8;font-size:0.78rem;letter-spacing:1px;">TRANSITION STATE</div>'
                f'<div style="color:{state_c};font-size:1.3rem;font-weight:800;">{trans_state.replace("_"," ")}</div>'
                f'<div style="color:#64748b;font-size:0.80rem;">Probability: {trans_prob:.0f}%</div>'
                f'<div style="margin-top:8px;">'
                f'{_badge("EXPANSION", "#22c55e") if exp_phase else ""}'
                f'{_badge("COMPRESSION", "#3b82f6") if comp_phase else ""}'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        with t_col2:
            st.markdown(
                _score_bar("Trend Exhaustion", exh_val, "#ef4444") +
                _score_bar("Breakout Loading", bkout_val, "#f59e0b") +
                _score_bar("Transition Probability", trans_prob, "#8b5cf6"),
                unsafe_allow_html=True,
            )

    with diag_tab2:
        s_col1, s_col2 = st.columns(2)
        with s_col1:
            st.markdown("**Session Context**")
            session_full = sess.get("current_session", "ASIAN")
            liq_acc = float(sess.get("liquidity_acceleration", 1.0))
            sess_vol = float(sess.get("session_volatility", 0.0))
            is_ovlp  = bool(sess.get("is_overlap", False))
            st.write(f"🕐 **Session**: {session_full.replace('_', ' ')}")
            st.write(f"💧 **Liquidity**: {sess.get('session_liquidity','?')}")
            st.write(f"⚡ **Acceleration**: {liq_acc:.2f}x")
            st.write(f"📈 **Session Volatility**: {sess_vol:.3f}")
            if is_ovlp:
                st.success("✅ Session Overlap Active")

        with s_col2:
            st.markdown("**Market Memory**")
            reg_dur  = int(mem.get("regime_duration", 0))
            trend_age_m = int(mem.get("h1_trend_age", 0))
            vol_pers = int(mem.get("volatility_persistence", 0))
            stability = float(mem.get("market_stability", 50.0))

            st.markdown(
                _score_bar("Market Stability", stability, "#22c55e"),
                unsafe_allow_html=True,
            )
            st.write(f"📅 **Regime Duration**: {reg_dur} candles")
            st.write(f"📈 **H1 Trend Age**: {trend_age_m} candles")
            st.write(f"🔁 **Volatility Persistence**: {vol_pers} candles")

    with diag_tab3:
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            pattern_type = candle.get("pattern_type", "NEUTRAL")
            pattern_name = candle.get("pattern_name", "No Pattern")
            cdir         = candle.get("direction_bias", "NEUTRAL")
            cq           = float(candle.get("candle_quality", 0.0))
            sweep        = bool(candle.get("liquidity_sweep", False))
            c_color = _DIR_COLORS.get(cdir, "#94a3b8")

            st.markdown(
                f'<div style="background:#111827;border-left:4px solid {c_color};'
                f'padding:16px;border-radius:8px;">'
                f'<div style="color:#94a3b8;font-size:0.78rem;">CANDLESTICK PATTERN</div>'
                f'<div style="color:{c_color};font-size:1.3rem;font-weight:800;">{pattern_name}</div>'
                f'<div style="color:#64748b;font-size:0.80rem;">Type: {pattern_type} | Bias: {cdir}</div>'
                f'{"<div style=margin-top:8px;>" + _badge("⚡ LIQUIDITY SWEEP", "#f59e0b") + "</div>" if sweep else ""}'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(
                _score_bar("Candle Quality", cq, c_color) +
                _score_bar("Body Ratio", float(candle.get("body_ratio", 0.0)) * 100, "#3b82f6") +
                _score_bar("Upper Wick", float(candle.get("upper_wick_ratio", 0.0)) * 100, "#ef4444") +
                _score_bar("Lower Wick", float(candle.get("lower_wick_ratio", 0.0)) * 100, "#22c55e"),
                unsafe_allow_html=True,
            )

        with c_col2:
            st.markdown("**M5 Precision Timing**")
            m5_dir    = m5.get("micro_direction", "NEUTRAL")
            m5_timing = float(m5.get("m5_timing_score", 0.0))
            entry_q   = float(m5.get("entry_window_quality", 0.0))
            spread_q  = m5.get("spread_quality", "NORMAL")
            mom_aln   = bool(m5.get("momentum_aligned", False))
            vol_cfm   = bool(m5.get("volume_confirmation", False))

            m5_color = _DIR_COLORS.get(m5_dir, "#94a3b8")
            st.markdown(
                f'<div style="background:#111827;border-left:4px solid {m5_color};'
                f'padding:12px;border-radius:8px;margin-bottom:10px;">'
                f'<div style="color:#94a3b8;font-size:0.78rem;">M5 MICRO DIRECTION</div>'
                f'<div style="color:{m5_color};font-size:1.2rem;font-weight:800;">{m5_dir}</div>'
                f'<div style="margin-top:6px;">'
                f'{_badge("✅ ALIGNED" if mom_aln else "⚠ MISALIGNED", "#22c55e" if mom_aln else "#f59e0b")}'
                f'{_badge("📊 VOL OK" if vol_cfm else "📉 WEAK VOL", "#22c55e" if vol_cfm else "#94a3b8")}'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                _score_bar("M5 Timing Score", m5_timing, m5_color) +
                _score_bar("Entry Window Quality", entry_q, "#3b82f6"),
                unsafe_allow_html=True,
            )
            st.caption(f"Spread: **{spread_q}** | UTC Hour: {clock.get('current_utc_hour', 0):02d}:00")

    with diag_tab4:
        risk_factors = risk.get("risk_factors", [])
        r_col1, r_col2 = st.columns(2)
        with r_col1:
            st.markdown(
                _score_bar("Exhaustion Probability", float(risk.get("exhaustion_probability", 0.0)), "#ef4444") +
                _score_bar("Fake Breakout Risk", float(risk.get("fake_breakout_prob", 0.0)), "#f59e0b") +
                _score_bar("Liquidity Vacuum Risk", float(risk.get("liquidity_vacuum_risk", 0.0)), "#8b5cf6") +
                _score_bar("Composite Risk Score", float(risk.get("risk_score", 0.0)), _RISK_COLORS.get(risk.get("risk_level","MODERATE"), "#94a3b8")),
                unsafe_allow_html=True,
            )
        with r_col2:
            if risk_factors:
                for rf in risk_factors:
                    st.markdown(
                        f'<div style="background:#1e293b;padding:10px 14px;border-radius:8px;'
                        f'font-size:0.82rem;color:#fde68a;margin-bottom:6px;">{rf}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.success("✅ No major risk factors detected.")

    st.divider()

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 5 — RAW QUANT LAB (hidden by default)
    # ═══════════════════════════════════════════════════════════════════════════
    with st.expander("🔭 Tier 5 — Raw Quant Laboratory", expanded=False):
        st.markdown("##### H4 Structure")
        st.json(h4)
        st.markdown("##### Confidence Layer Scores")
        layer_scores = conf.get("layer_scores", {})
        if layer_scores:
            st.json(layer_scores)
        st.markdown("##### Execution Readiness Gates")
        gates = ready.get("readiness_gates", [])
        hard_blocks = ready.get("hard_blocks", [])
        for g in gates:
            st.markdown(f"- ⚡ {g}")
        for b in hard_blocks:
            st.error(b)
        st.markdown("##### Signal Quality Raw")
        st.json(sq)
        st.markdown("##### Full Context Dump")
        if st.checkbox("Show full context JSON (may be large)", value=False):
            st.json(ctx.to_dict())
