"""
ui/analysis_lab.py
NexusBot V3 — Analysis Lab Workspace

Presentation-only: reads from snapshot_store and session_state.
All heavy computation (pipeline, data download) is triggered via
'pending_*' session-state flags that fire ONCE at the top of the
render function, keeping Streamlit reruns deterministic.

Focus Mode: when engine_state is ARMED or EXECUTING, the chart and
Execution Intelligence Pipeline take full focus. Auxiliary expanders
(AI Briefing, Ingestion, Replay) are auto-collapsed.
"""
import streamlit as st
import pandas as pd
import numpy as np
import datetime
import io
import plotly.graph_objects as go
from types import SimpleNamespace
from engine.intelligence_pipeline import run_intelligence_pipeline, clear_pipeline_cache
from engine.tournament_models import TournamentInput
from deployment.replay_controller import ReplayController
from ui.thesis_panel import render_trade_thesis
from ui.pipeline_panel import render_execution_pipeline
from utils.data_loader import resolve_symbol


ANALYSIS_SYMBOLS_BY_ASSET_CLASS = {
    "Forex": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD"],
    "Indices": ["US500", "NAS100", "US30", "GER40", "UK100"],
    "Commodities": ["XAUUSD", "XAGUSD", "USOIL", "UKOIL"],
    "Crypto": ["BTCUSD", "ETHUSD"],
    "Stocks": ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL"],
    "Custom": [],
}
ANALYSIS_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]


@st.cache_data
def run_data_pipeline_cached(file_name: str, file_bytes: bytes) -> dict:
    """Caches CSV dataset parsing, validation, and resampling."""
    from engine.data_pipeline import DataPipeline
    pipeline = DataPipeline()
    return pipeline.load_from_upload(io.BytesIO(file_bytes))


def _sync_pipeline_results(orch_ctx, h1_df: pd.DataFrame, m15_df: pd.DataFrame) -> None:
    """Synchronizes pipeline outputs back to Streamlit session state."""
    from engine.mtf_context import MTFContextEngine
    if orch_ctx is None:
        orch_ctx = SimpleNamespace(
            h1_structure={},
            m15_execution={},
            execution_readiness={},
            contradiction_engine={},
            contradiction_state={},
            confidence_hierarchy={},
            signal_saturation={},
            institutional_risk={},
            execution_candidates=[],
            tournament_results=[],
            recommended_strategy=None,
            market_explainer={},
        )
    st.session_state["orchestration_context"] = orch_ctx
    st.session_state["market_regime"] = orch_ctx.h1_structure

    # Calculate MTF context
    if h1_df is not None and not h1_df.empty and m15_df is not None and not m15_df.empty:
        alignment_score = MTFContextEngine().analyze(h1_df, m15_df).get("alignment_score", 50.0)
    else:
        alignment_score = orch_ctx.h1_structure.get("_alignment_score", 50.0)
    st.session_state["mtf_context"] = {
        "h1_structure":   orch_ctx.h1_structure,
        "m15_execution":  orch_ctx.m15_execution,
        "alignment_score": orch_ctx.h1_structure.get("_alignment_score", 50.0)
        if "_alignment_score" in orch_ctx.h1_structure
        else alignment_score,
        "context_label": orch_ctx.h1_structure.get("context_label", "Developing"),
    }
    st.session_state["v3_pipeline_complete"] = True
    st.session_state["step_2_complete"] = True


def _get_runtime_symbol() -> str:
    symbol = st.session_state.get("runtime_symbol", None)
    if not symbol:
        symbol = "UNKNOWN"
    return str(symbol).strip().upper() or "UNKNOWN"


def _normalize_symbol(value: str | None) -> str:
    return str(value or "").strip().upper()


def _parse_manual_symbols(value: str) -> list[str]:
    symbols = []
    for raw in str(value or "").replace("\n", ",").split(","):
        sym = _normalize_symbol(raw)
        if sym and sym not in symbols:
            symbols.append(sym)
    return symbols


def _render_analysis_market_selector(state) -> tuple[list[str], str, str]:
    st.markdown("#### Market Basket")
    st.caption("Saved in Settings. Click a symbol to inspect that symbol's analysis context.")

    selected_symbols = [
        _normalize_symbol(sym)
        for sym in st.session_state.get("runtime_symbols", [_get_runtime_symbol()])
        if _normalize_symbol(sym)
    ][:5] or [_get_runtime_symbol()]

    active_symbol = st.session_state.get("runtime_symbol", selected_symbols[0])
    if active_symbol not in selected_symbols:
        active_symbol = selected_symbols[0]

    button_cols = st.columns(max(1, len(selected_symbols)))
    for idx, sym in enumerate(selected_symbols):
        with button_cols[idx]:
            btn_type = "primary" if sym == active_symbol else "secondary"
            if st.button(sym, key=f"analysis_use_symbol_{sym}", type=btn_type, use_container_width=True):
                st.session_state["runtime_symbol"] = sym
                st.session_state["chart_symbol"] = sym
                _activate_stored_symbol_context(sym)
                st.rerun()

    current_tf = str(st.session_state.get("runtime_timeframe", "M5")).upper()
    if current_tf not in ANALYSIS_TIMEFRAMES:
        current_tf = "M5"
    timeframe = st.selectbox(
        "Analysis Timeframe",
        ANALYSIS_TIMEFRAMES,
        index=ANALYSIS_TIMEFRAMES.index(current_tf),
        key="analysis_runtime_timeframe",
    )

    st.session_state["analysis_selected_symbols"] = selected_symbols
    st.session_state["dashboard_symbols"] = selected_symbols
    st.session_state["runtime_symbol"] = active_symbol
    st.session_state["runtime_timeframe"] = timeframe
    st.session_state["dashboard_timeframe"] = timeframe
    st.session_state["chart_symbol"] = active_symbol
    st.session_state["chart_timeframe"] = timeframe
    if hasattr(state, "watchlist_timeframe"):
        state.watchlist_timeframe = timeframe

    try:
        from deployment.engine_runtime import get_global_runtime
        runtime = get_global_runtime()
        runtime.set_symbol(active_symbol)
        if hasattr(runtime, "set_timeframe"):
            runtime.set_timeframe(timeframe)
    except Exception:
        pass

    return selected_symbols, active_symbol, timeframe


def _activate_stored_symbol_context(symbol: str) -> bool:
    contexts = st.session_state.get("analysis_symbol_contexts") or {}
    payload = contexts.get(symbol)
    if not payload:
        return False
    st.session_state["uploaded_df"] = payload.get("uploaded_df")
    st.session_state["m5_df"] = payload.get("m5_df")
    st.session_state["m15_df"] = payload.get("m15_df")
    st.session_state["h1_df"] = payload.get("h1_df")
    st.session_state["h4_df"] = payload.get("h4_df")
    orch_ctx = payload.get("orchestration_context")
    _sync_pipeline_results(orch_ctx, payload.get("h1_df"), payload.get("m15_df"))
    st.session_state["recommended_strategy"] = getattr(orch_ctx, "recommended_strategy", None)
    st.session_state["market_explainer"] = getattr(orch_ctx, "market_explainer", {})
    st.session_state["tournament_results"] = getattr(orch_ctx, "tournament_results", [])
    return True


def calculate_fvgs(df: pd.DataFrame, window_size: int = 150) -> list:
    """
    Identifies Fair Value Gaps (FVG) in the latest window of candles.
    Returns list of dicts: {"type": "BULLISH"/"BEARISH", "top": float, "bottom": float, "start_idx": int}
    """
    fvgs = []
    if df is None or len(df) < 3:
        return fvgs

    # Standardize column casing to lower
    pdf = df.copy()
    pdf.columns = [c.lower() for c in pdf.columns]
    
    # We only scan the last N candles
    start_idx = max(0, len(pdf) - window_size)
    
    for i in range(start_idx + 2, len(pdf)):
        prev2 = pdf.iloc[i - 2]
        curr = pdf.iloc[i]
        
        # Bullish FVG: Low of candle [i] > High of candle [i-2]
        if curr["low"] > prev2["high"]:
            fvgs.append({
                "type": "BULLISH",
                "top": curr["low"],
                "bottom": prev2["high"],
                "start_idx": i - 2,
                "end_idx": i
            })
        # Bearish FVG: High of candle [i] < Low of candle [i-2]
        elif curr["high"] < prev2["low"]:
            fvgs.append({
                "type": "BEARISH",
                "top": prev2["low"],
                "bottom": curr["high"],
                "start_idx": i - 2,
                "end_idx": i
            })
            
    return fvgs


def render_liquidity_plotly(df: pd.DataFrame, active_positions: list, active_candidates: list, fvgs: list, window_size: int = 150) -> None:
    """
    Renders the Plotly candlestick chart with liquidity map overlays, FVG blocks,
    session lines, and buy/sell markers.
    """
    if df is None or df.empty:
        st.info("No market data loaded yet.")
        return

    # Standardize column casing
    plot_df = df.copy()
    plot_df.columns = [col.lower() for col in plot_df.columns]
    
    # Slice to last N candles
    plot_df = plot_df.iloc[-window_size:]
    time_col = 'timestamp' if 'timestamp' in plot_df.columns else None
    x_values = plot_df[time_col] if time_col else plot_df.index
    
    fig = go.Figure()
    
    # 1. Add Candlestick Trace
    fig.add_trace(go.Candlestick(
        x=x_values,
        open=plot_df['open'],
        high=plot_df['high'],
        low=plot_df['low'],
        close=plot_df['close'],
        name="Candles",
        increasing_line=dict(color='#22c55e', width=1.0),
        increasing_fillcolor='rgba(34, 197, 94, 0.15)',
        decreasing_line=dict(color='#ef4444', width=1.0),
        decreasing_fillcolor='rgba(239, 68, 68, 0.15)'
    ))
    
    # 2. Add FVG Shapes
    # Draw them as transparent shaded rectangles
    for fvg in fvgs:
        fvg_start_idx = fvg["start_idx"]
        if fvg_start_idx < len(df) - window_size:
            continue
            
        if time_col and time_col in df.columns:
            x0_val = df[time_col].iloc[fvg["start_idx"]]
            x1_val = df[time_col].iloc[-1]  # Extend to current candle
        else:
            x0_val = df.index[fvg["start_idx"]]
            x1_val = df.index[-1]
        color = "rgba(34, 197, 94, 0.15)" if fvg["type"] == "BULLISH" else "rgba(239, 68, 68, 0.15)"
        
        fig.add_shape(
            type="rect",
            x0=x0_val,
            x1=x1_val,
            y0=fvg["bottom"],
            y1=fvg["top"],
            fillcolor=color,
            opacity=0.6,
            layer="below",
            line_width=0,
        )

    # 3. Add Session/Window Highs and Lows (Liquidity pools)
    win_high = float(plot_df['high'].max())
    win_low = float(plot_df['low'].min())
    
    fig.add_hline(
        y=win_high,
        line_dash="dash",
        line_color="#ec4899",
        line_width=1.5,
        annotation_text="Liquidity Ceiling (High)",
        annotation_position="top left",
        annotation_font=dict(color="#ec4899", size=10)
    )
    fig.add_hline(
        y=win_low,
        line_dash="dash",
        line_color="#3b82f6",
        line_width=1.5,
        annotation_text="Liquidity Floor (Low)",
        annotation_position="bottom left",
        annotation_font=dict(color="#3b82f6", size=10)
    )

    # 4. Add Active Position Lines
    for pos in active_positions:
        fig.add_hline(
            y=pos["entry_price"],
            line_dash="dot",
            line_color="#3b82f6",
            line_width=1.5,
            annotation_text=f"#{pos['ticket']} Entry ({pos['direction']})",
            annotation_position="top left",
            annotation_font=dict(color="#3b82f6", size=10)
        )
        if pos.get("sl"):
            fig.add_hline(
                y=pos["sl"],
                line_dash="dash",
                line_color="#ef4444",
                line_width=1.5,
                annotation_text="SL",
                annotation_position="bottom left",
                annotation_font=dict(color="#ef4444", size=10)
            )
        if pos.get("tp"):
            fig.add_hline(
                y=pos["tp"],
                line_dash="dash",
                line_color="#22c55e",
                line_width=1.5,
                annotation_text="TP",
                annotation_position="top left",
                annotation_font=dict(color="#22c55e", size=10)
            )

    # 5. Add Candidate Annotations
    last_time = x_values.iloc[-1] if hasattr(x_values, "iloc") else x_values[-1]
    last_price = plot_df['close'].iloc[-1]
    for cand in active_candidates:
        direction = cand.get("direction", "NEUTRAL")
        confidence = cand.get("confidence", 0)
        
        if direction in ("BUY", "BULLISH", "UP"):
            fig.add_annotation(
                x=last_time,
                y=last_price,
                text=f"BUY Candidate ({confidence:.0f}%)",
                showarrow=True,
                arrowhead=2,
                arrowcolor="#22c55e",
                arrowsize=1.5,
                arrowwidth=2,
                ay=-45,
                font=dict(color="#22c55e", size=11, family="Inter"),
                bgcolor="#0f172a",
                bordercolor="#22c55e",
                borderwidth=1,
                borderpad=4
            )
        elif direction in ("SELL", "BEARISH", "DOWN"):
            fig.add_annotation(
                x=last_time,
                y=last_price,
                text=f"SELL Candidate ({confidence:.0f}%)",
                showarrow=True,
                arrowhead=2,
                arrowcolor="#ef4444",
                arrowsize=1.5,
                arrowwidth=2,
                ay=45,
                font=dict(color="#ef4444", size=11, family="Inter"),
                bgcolor="#0f172a",
                bordercolor="#ef4444",
                borderwidth=1,
                borderpad=4
            )

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=5, r=5, t=5, b=5),
        hovermode="x unified",
        xaxis=dict(
            gridcolor='rgba(30, 41, 59, 0.4)',
            tickfont=dict(color='#64748b', family="Inter"),
            linecolor='#334155'
        ),
        yaxis=dict(
            gridcolor='rgba(30, 41, 59, 0.4)',
            tickfont=dict(color='#64748b', family="Inter"),
            linecolor='#334155',
            side="right"
        ),
        height=520,
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)


def _execute_pending_pipeline(state, engine, h1_df, m15_df) -> bool:
    """
    Runs the 19-engine intelligence pipeline if 'pending_pipeline_run' is set.
    Returns True if pipeline ran and session was updated (triggers st.rerun outside).
    """
    if not st.session_state.pop("pending_pipeline_run", False):
        return False
    if h1_df is None or h1_df.empty or m15_df is None or m15_df.empty:
        st.session_state["pipeline_error"] = "Load or download market data before triggering the engine."
        return True

    bundle = {
        "m5":    st.session_state.get("m5_df", m15_df),
        "m15":   m15_df,
        "h1":    h1_df,
        "h4":    st.session_state.get("h4_df", h1_df),
        "symbol": _get_runtime_symbol()
    }
    try:
        from deployment.engine_runtime import get_global_runtime
        rt = get_global_runtime()
        rt.run_pipeline_eval(bundle)
        orch_ctx = run_intelligence_pipeline(bundle, use_cache=False)
        rt.latest_orch_ctx = orch_ctx
        diagnostics = rt.orchestration._compile_engine_diagnostics(orch_ctx)
        flow = rt.orchestration._compile_pipeline_flow(orch_ctx)
        rt.snapshot_store.update_snapshot(
            engine_diagnostics=diagnostics,
            pipeline_flow=flow,
            strategy_rankings=getattr(orch_ctx, "tournament_results", []) or [],
            execution_candidates=getattr(orch_ctx, "execution_candidates", []) or [],
        )
        st.session_state["pipeline_diagnostics"] = diagnostics
        st.session_state["pipeline_flow"] = flow
        st.session_state["pipeline_status"] = f"Pipeline completed: {len(diagnostics)} engines, {len(flow)} stages."
        if orch_ctx is None:
            raise RuntimeError("Engine evaluation did not produce an orchestration context.")
        _sync_pipeline_results(orch_ctx, h1_df, m15_df)
        st.session_state["recommended_strategy"] = getattr(orch_ctx, "recommended_strategy", None)
        st.session_state["market_explainer"]      = getattr(orch_ctx, "market_explainer", {})
        st.session_state["tournament_results"]    = getattr(orch_ctx, "tournament_results", [])
        st.toast("✅ 19-Engine Pipeline completed.")
    except Exception as exc:
        st.session_state["pipeline_error"] = str(exc)
        st.session_state["pipeline_status"] = f"Pipeline failed: {exc}"
    return True


def _execute_pending_replay_step(state, replay_ctrl, h1_df, m15_df) -> bool:
    """
    Advances one replay candle and re-evaluates the pipeline if
    'pending_replay_step' is set. Returns True on completion.
    """
    if not st.session_state.pop("pending_replay_step", False):
        return False

    advanced = replay_ctrl.step_candle()
    if advanced:
        sliced_h1 = replay_ctrl.get_current_slice()
        bundle = {
            "m5":    st.session_state.get("m5_df", m15_df),
            "m15":   m15_df,
            "h1":    sliced_h1,
            "h4":    st.session_state.get("h4_df", h1_df),
            "symbol": _get_runtime_symbol()
        }
        try:
            from deployment.engine_runtime import get_global_runtime
            rt = get_global_runtime()
            rt.run_pipeline_eval(bundle)
            orch_ctx = rt.latest_orch_ctx
            _sync_pipeline_results(orch_ctx, sliced_h1, m15_df)
        except Exception as e:
            state.event_bus.emit(f"Replay step failed: {e}", "CRITICAL")
    return True


def _summarize_orchestration(symbol: str, timeframe: str, rows: int, integrity_score: float, orch_ctx) -> dict:
    tournament = getattr(orch_ctx, "tournament_results", []) or []
    top = tournament[0] if tournament else {}
    h1_structure = getattr(orch_ctx, "h1_structure", {}) or {}
    readiness = getattr(orch_ctx, "execution_readiness", {}) or {}
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "rows": rows,
        "integrity_score": integrity_score,
        "regime": h1_structure.get("regime") or h1_structure.get("market_regime") or h1_structure.get("context_label", "N/A"),
        "direction": h1_structure.get("direction", "N/A"),
        "top_strategy": top.get("strategy", "N/A"),
        "rank": top.get("rank", "N/A"),
        "fit": top.get("market_fit_score", top.get("fit_score", "N/A")),
        "signal": top.get("signal", top.get("direction", "N/A")),
        "readiness": readiness.get("status", readiness.get("readiness", "N/A")),
        "tournament_results": tournament,
        "status": "ANALYZED",
    }


def _download_and_analyze_symbol(symbol: str, timeframe: str, mt5_start_dt, mt5_end_dt, make_active: bool) -> dict:
    from runtime.mt5_data_downloader import MT5DataDownloader
    from runtime.dataset_bundle import DatasetBundle
    from runtime.dataset_registry import DatasetRegistry
    from engine.feature_engineering import compute_features
    from deployment.engine_runtime import get_global_runtime

    runtime = get_global_runtime()
    connector = runtime.mt5.connector
    runtime.set_symbol(symbol)
    if st.session_state.get("mt5_terminal", "") == "MetaTrader 5 (Simulated)":
        connector.is_simulated = True
    connector.ensure_symbol(symbol)

    downloader = MT5DataDownloader(connector)
    dt_start = datetime.datetime.combine(mt5_start_dt, datetime.time.min)
    dt_end = datetime.datetime.combine(mt5_end_dt, datetime.time.max)

    df, report = downloader.download_historical_data(
        symbol=symbol,
        timeframe_str=timeframe,
        start_date=dt_start,
        end_date=dt_end,
    )
    if df is None or df.empty:
        raise RuntimeError(f"Downloaded dataset is empty for {symbol}. {report.get('error', '')}")

    resolved_sym = resolve_symbol(df, symbol)
    bundle_exporter = DatasetBundle()
    meta = bundle_exporter.save_bundle(
        symbol=resolved_sym,
        broker=st.session_state.get("mt5_broker", "ICMarkets"),
        base_df=df,
        integrity_score=report.get("integrity_score", 0.0),
    )

    DatasetRegistry().register_dataset(
        symbol=resolved_sym,
        timeframe=timeframe,
        rows=len(df),
        integrity_score=report.get("integrity_score", 0.0),
        dataset_hash=meta["dataset_hash"],
    )

    loaded_bundle = bundle_exporter.load_bundle(resolved_sym)
    if not loaded_bundle:
        raise RuntimeError(f"Saved bundle could not be reloaded for {resolved_sym}.")

    bundle = {
        "m5": compute_features(loaded_bundle["m5"]),
        "m15": compute_features(loaded_bundle["m15"]),
        "h1": compute_features(loaded_bundle["h1"]),
        "h4": compute_features(loaded_bundle["h4"]),
        "symbol": resolved_sym,
    }

    runtime.run_pipeline_eval(bundle)
    orch_ctx = run_intelligence_pipeline(bundle, use_cache=False)
    runtime.latest_orch_ctx = orch_ctx
    summary = _summarize_orchestration(
        resolved_sym,
        timeframe,
        len(df),
        report.get("integrity_score", 0.0),
        orch_ctx,
    )

    results = st.session_state.get("analysis_symbol_results") or {}
    results[resolved_sym] = summary
    st.session_state["analysis_symbol_results"] = results

    contexts = st.session_state.get("analysis_symbol_contexts") or {}
    contexts[resolved_sym] = {
        "uploaded_df": df,
        "m5_df": bundle["m5"],
        "m15_df": bundle["m15"],
        "h1_df": bundle["h1"],
        "h4_df": bundle["h4"],
        "orchestration_context": orch_ctx,
    }
    st.session_state["analysis_symbol_contexts"] = contexts

    if make_active:
        st.session_state["runtime_symbol"] = resolved_sym
        st.session_state["step_1_complete"] = True
        _activate_stored_symbol_context(resolved_sym)

    return summary


def render_analysis_lab(state, engine) -> None:
    """
    Renders the Analysis Lab workspace.
    Presentation-only: reads snapshot state, dispatches work via pending flags.
    Focus Mode: ARMED/EXECUTING collapses auxiliary panels.
    """
    # ── Guard: initialize replay controller ───────────────────────────────
    if "replay_controller" not in st.session_state:
        st.session_state["replay_controller"] = ReplayController()

    replay_ctrl = st.session_state["replay_controller"]
    orch_ctx    = st.session_state.get("orchestration_context")
    h1_df       = st.session_state.get("h1_df")
    m15_df      = st.session_state.get("m15_df")
    replay_active = st.session_state.get("replay_active", False)
    if orch_ctx is None:
        try:
            from deployment.engine_runtime import get_global_runtime
            orch_ctx = get_global_runtime().latest_orch_ctx
        except Exception:
            orch_ctx = None

    # Focus Mode: collapse auxiliary panels when executing
    focus_mode = state.engine_state in ("ARMED", "EXECUTING", "ACTIVE")

    # ── Execute any pending deferred work (fires ONCE, then reruns) ────────
    did_work = False
    did_work |= _execute_pending_pipeline(state, engine, h1_df if h1_df is not None else pd.DataFrame(), m15_df if m15_df is not None else pd.DataFrame())
    did_work |= _execute_pending_replay_step(state, replay_ctrl, h1_df if h1_df is not None else pd.DataFrame(), m15_df if m15_df is not None else pd.DataFrame())
    if did_work:
        st.rerun()

    # Pipeline error display
    if "pipeline_error" in st.session_state:
        err = st.session_state.pop("pipeline_error")
        st.error(f"❌ Pipeline error: {err}")

    # Focus Mode banner
    if focus_mode:
        st.markdown(
            '<div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.3);'
            'border-radius:6px;padding:6px 14px;margin-bottom:10px;font-size:0.75rem;color:#f59e0b;">'
            '⚡ <b>FOCUS MODE</b> — Engine ARMED/EXECUTING. Chart and Pipeline Panel in full view. '
            'Auxiliary panels collapsed.</div>',
            unsafe_allow_html=True
        )


    selected_symbols, active_symbol, selected_timeframe = _render_analysis_market_selector(state)

    left_col, right_col = st.columns([1.7, 1.0], gap="large")
    with left_col:
        st.markdown(
            '<div style="font-size:0.8rem;font-weight:700;color:#64748b;'
            'letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;">'
            '📈 Interactive Liquidity Chart</div>',
            unsafe_allow_html=True
        )

        with st.expander("📥 Data Ingestion & Live Feed", expanded=(h1_df is None)):
            if st.session_state.get("symbol_warning"):
                st.warning(st.session_state["symbol_warning"])

            ingest_mode = st.radio(
                "Choose Data Ingestion Source",
                options=["Upload CSV", "Download From MT5"],
                index=0 if st.session_state.get("ingestion_source", "Upload CSV") == "Upload CSV" else 1,
                horizontal=True,
                key="ingestion_source_radio_lab"
            )
            st.session_state["ingestion_source"] = ingest_mode

            if ingest_mode == "Upload CSV":
                uploaded_file = st.file_uploader(
                    "Upload Broker CSV File",
                    type=["csv"],
                    help="Supports standard MT5 broker exports.",
                    key="uploader_lab"
                )

                if uploaded_file:
                    if (st.session_state["last_uploaded_filename"] != uploaded_file.name or 
                        st.session_state["last_uploaded_filesize"] != uploaded_file.size or 
                        not st.session_state["step_1_complete"]):
                        
                        with st.spinner("Processing Ingestion Pipeline..."):
                            try:
                                file_bytes = uploaded_file.read()
                                pipe_data = run_data_pipeline_cached(uploaded_file.name, file_bytes)

                                df = pipe_data["df"]
                                sidebar_sym = _get_runtime_symbol()
                                resolved_sym = resolve_symbol(df, sidebar_sym)

                                if sidebar_sym and resolved_sym != sidebar_sym.upper():
                                    st.session_state["symbol_warning"] = f"Loaded MT5 symbol detected: {resolved_sym}. Global runtime symbol remains {sidebar_sym}."
                                else:
                                    st.session_state["symbol_warning"] = None

                                st.session_state["uploaded_df"] = df
                                st.session_state["h1_df"]       = pipe_data["h1_df"]
                                st.session_state["m15_df"]      = pipe_data["m15_df"]
                                st.session_state["pipeline_data"] = pipe_data
                                st.session_state["last_uploaded_filename"] = uploaded_file.name
                                st.session_state["last_uploaded_filesize"] = uploaded_file.size
                                st.session_state["step_1_complete"] = True

                                # Reset downstream progress
                                for key in ("market_regime", "mtf_context", "market_explainer", "tournament_results", 
                                            "recommended_strategy", "optimization_result", "deployment_candidate", "workflow_complete"):
                                    st.session_state[key] = None
                                for step_f in ("step_2_complete", "step_3_complete", "step_4_complete", "step_5_complete"):
                                    st.session_state[step_f] = False
                                    
                                st.success("✅ Ingested successfully.")
                                st.rerun()

                            except Exception as exc:
                                st.error(f"❌ Ingestion Error: {exc}")
                                st.session_state["step_1_complete"] = False
            else:
                # MT5 Downloader controls
                runtime_symbol = _get_runtime_symbol()
                st.markdown(f"**Ingestion Asset Symbol:** `{runtime_symbol}`")
                tf_options = ["M1", "M5", "M15", "M30", "H1", "H4"]
                current_tf = str(st.session_state.get("runtime_timeframe", "M5")).upper()
                if current_tf not in tf_options:
                    current_tf = "M5"
                if st.session_state.get("mt5_tf_input_lab") != current_tf:
                    st.session_state["mt5_tf_input_lab"] = current_tf
                mt5_tf = st.selectbox(
                    "Base Timeframe",
                    options=tf_options,
                    index=tf_options.index(current_tf),
                    key="mt5_tf_input_lab",
                )
                st.session_state["runtime_timeframe"] = mt5_tf
                
                c_d1, c_d2 = st.columns(2)
                with c_d1:
                    mt5_start_dt = st.date_input("Start Date", value=datetime.date.today() - datetime.timedelta(days=90), key="mt5_start_input_lab")
                with c_d2:
                    mt5_end_dt = st.date_input("End Date", value=datetime.date.today(), key="mt5_end_input_lab")

                btn1, btn2 = st.columns(2)
                with btn1:
                    connect_clicked = st.button("🔌 Connect MT5", type="secondary", use_container_width=True, key="btn_connect_mt5_lab")
                with btn2:
                    download_clicked = st.button("📥 Download Data", type="primary", use_container_width=True, disabled=not st.session_state.get("mt5_connected", False), key="btn_download_mt5_lab")

                if connect_clicked:
                    with st.spinner("Connecting to MT5 terminal..."):
                        from deployment.engine_runtime import get_global_runtime
                        runtime = get_global_runtime()
                        connector = runtime.mt5.connector
                        conn_status = connector.initialize()
                        runtime.mt5.connection_status = conn_status
                        runtime.set_symbol(_get_runtime_symbol())
                        
                        st.session_state["mt5_connected"] = conn_status["connected"]
                        st.session_state["mt5_broker"] = conn_status["broker"]
                        st.session_state["mt5_server"] = conn_status["server"]
                        st.session_state["mt5_terminal"] = conn_status["terminal"]
                        
                        if conn_status["connected"]:
                            acc_info = connector.get_account_info()
                            st.session_state["mt5_balance"] = acc_info["balance"]
                            st.session_state["mt5_equity"] = acc_info["equity"]
                            st.session_state["mt5_currency"] = acc_info["currency"]
                            st.session_state["mt5_leverage"] = acc_info["leverage"]
                            st.success("✅ Connected to MT5 API.")
                            st.rerun()
                        else:
                            st.error(f"❌ Failed to initialize MT5 connection. last_error={conn_status.get('last_error')}")

                if download_clicked:
                    with st.spinner(f"Downloading and analyzing {len(selected_symbols)} symbol(s) from MT5..."):
                        try:
                            from deployment.engine_runtime import get_global_runtime
                            runtime = get_global_runtime()
                            connector = runtime.mt5.connector
                            conn_status = connector.initialize()
                            runtime.mt5.connection_status = conn_status
                            if not conn_status.get("connected"):
                                raise RuntimeError(f"MT5 connection failed: {conn_status.get('last_error')}")

                            summaries = []
                            failures = []
                            active_sym = _get_runtime_symbol()
                            for sym in selected_symbols:
                                try:
                                    summaries.append(
                                        _download_and_analyze_symbol(
                                            symbol=sym,
                                            timeframe=mt5_tf,
                                            mt5_start_dt=mt5_start_dt,
                                            mt5_end_dt=mt5_end_dt,
                                            make_active=(sym == active_sym),
                                        )
                                    )
                                except Exception as sym_exc:
                                    failures.append({"symbol": sym, "error": str(sym_exc)})

                            if summaries:
                                active_summary = next((item for item in summaries if item.get("symbol") == active_sym), summaries[0])
                                st.session_state["last_mt5_download_report"] = {
                                    "symbol": active_summary.get("symbol", active_sym),
                                    "timeframe": mt5_tf,
                                    "rows": active_summary.get("rows", 0),
                                    "integrity_score": active_summary.get("integrity_score", 0.0),
                                    "basket_count": len(summaries),
                                }
                                st.session_state["analysis_last_batch_failures"] = failures
                                st.success(f"Downloaded and analyzed {len(summaries)} symbol(s).")
                                st.rerun()
                            elif failures:
                                st.session_state["analysis_last_batch_failures"] = failures
                                st.warning(f"{len(failures)} symbol(s) failed. See batch status below.")
                        except Exception as exc:
                            st.error(f"MT5 Download failed: {exc}")
        download_report = st.session_state.get("last_mt5_download_report")
        uploaded_df = st.session_state.get("uploaded_df")
        if download_report and uploaded_df is not None and not uploaded_df.empty:
            st.success(
                f"MT5 data loaded: {download_report['rows']:,} {download_report['symbol']} "
                f"{download_report['timeframe']} candles | integrity {download_report['integrity_score']:.1f}%"
            )
            st.dataframe(uploaded_df.tail(20), use_container_width=True, height=240)

        analysis_results = st.session_state.get("analysis_symbol_results") or {}
        selected_result_rows = [
            {
                "symbol": sym,
                "timeframe": analysis_results.get(sym, {}).get("timeframe", selected_timeframe),
                "status": analysis_results.get(sym, {}).get("status", "PENDING"),
                "regime": analysis_results.get(sym, {}).get("regime", "N/A"),
                "top_strategy": analysis_results.get(sym, {}).get("top_strategy", "N/A"),
                "fit": analysis_results.get(sym, {}).get("fit", "N/A"),
                "readiness": analysis_results.get(sym, {}).get("readiness", "N/A"),
            }
            for sym in selected_symbols
        ]
        if selected_result_rows:
            st.markdown("#### Basket Analysis Status")
            st.dataframe(pd.DataFrame(selected_result_rows), use_container_width=True, hide_index=True)

        batch_failures = st.session_state.get("analysis_last_batch_failures") or []
        if batch_failures:
            with st.expander("Batch Download Failures", expanded=False):
                st.dataframe(pd.DataFrame(batch_failures), use_container_width=True, hide_index=True)

        # 5. Historical Replay Engine
        with st.expander("🔄 Historical Replay Engine", expanded=replay_active and not focus_mode):
            toggle_replay = st.checkbox("Enable Replay Mode", value=replay_active, key="replay_active_chk_lab")
            if toggle_replay != replay_active:
                st.session_state["replay_active"] = toggle_replay
                if toggle_replay:
                    if h1_df is not None and not h1_df.empty:
                        replay_ctrl.load_dataset(h1_df)
                        state.event_bus.emit(f"Historical Replay enabled with {len(h1_df)} candles.", "INFO")
                    else:
                        st.session_state["replay_active"] = False
                        st.warning("Load market data before enabling replay.")
                else:
                    state.event_bus.emit("Historical Replay disabled.", "INFO")
                st.rerun()
            if replay_active:
                total_candles = len(replay_ctrl.replay_dataset)
                curr_ptr = replay_ctrl.candle_pointer
                
                # Pointer slider - ensure min_val < max_val
                max_val = max(200, total_candles - 1)
                min_val = min(200, max(0, total_candles - 1))
                
                if min_val < max_val:
                    new_ptr = st.slider(
                        "Replay Candle Pointer",
                        min_value=min_val,
                        max_value=max_val,
                        value=min(max(min_val, curr_ptr), max_val),
                        key="replay_slider_lab"
                    )
                    if new_ptr != curr_ptr:
                        replay_ctrl.candle_pointer = new_ptr
                        st.rerun()
                else:
                    st.caption(f"Replay pointer locked: {curr_ptr}/{total_candles - 1} (requires >200 candles to enable scrubbing slider)")
                
                col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
                with col_btn1:
                    play_lbl = "⏸️ Pause" if replay_ctrl.play_status == "PLAYING" else "▶️ Play"
                    if st.button(play_lbl, key="btn_play_lab", use_container_width=True):
                        new_status = "PAUSED" if replay_ctrl.play_status == "PLAYING" else "PLAYING"
                        replay_ctrl.set_play_status(new_status)
                        st.rerun()
                with col_btn2:
                    if st.button("➡️ Step", key="btn_step_lab", use_container_width=True):
                        # Dispatch deferred — no heavy work inside render path
                        st.session_state["pending_replay_step"] = True
                        st.rerun()
                with col_btn3:
                    if st.button("🔄 Reset", key="btn_reset_lab", use_container_width=True):
                        replay_ctrl.candle_pointer = 200
                        replay_ctrl.set_play_status("PAUSED")
                        st.rerun()

                if replay_ctrl.play_status == "PLAYING":
                    st.components.v1.html(
                        """
                        <script>
                        var parent_win = window.parent;
                        setTimeout(function() {
                            var btn = Array.from(parent_win.document.querySelectorAll("button")).find(el => el.innerText.trim() === "➡️ Step");
                            if (btn) {
                                btn.click();
                            }
                        }, 2000);
                        </script>
                        """,
                        height=0,
                        width=0
                    )

        # 6. Pipeline Trigger Card (collapsed in focus mode, since pipeline runs in background)
        if h1_df is not None and not h1_df.empty and not focus_mode:
            st.write("")
            if st.button(
                "🔍 Trigger V3 19-Engine Intelligence Pipeline",
                key="btn_run_pipeline_lab",
                type="primary",
                use_container_width=True
            ):
                # Deferred — dispatch via flag, not inline execution
                st.session_state["pending_pipeline_run"] = True
                st.rerun()
            if st.session_state.get("pipeline_status"):
                st.info(st.session_state["pipeline_status"])

    # ── Page Bottom (Full Width) ──
    st.markdown("---")
    
    # 1. Execution Intelligence Pipeline panel (Primary Visibility!)
    render_execution_pipeline(state, engine, orch_ctx)

    # 2. Strategy Deployment Console
    render_strategy_deployment_console(state, engine, orch_ctx)
    
    # 3. Strategy Arsenal / Persona Layer
    render_strategy_arsenal(state, engine, orch_ctx)
    
    # 4. Strategy Exclusion Logs (collapsible diagnostics)
    explainer = st.session_state.get("market_explainer")
    if explainer and explainer.get("strategy_rejections"):
        st.write("") # padding
        with st.expander("🚫 Strategy Exclusion Logs", expanded=False):
            for name, reason in explainer["strategy_rejections"].items():
                st.markdown(
                    f"""
                    <div style="background:#111827;border:1px solid #1e293b;border-radius:6px;padding:8px 12px;margin-bottom:6px;">
                        <strong style="color:#ef4444;font-size:0.85rem;">❌ {name}</strong><br>
                        <span style="color:#94a3b8;font-size:0.75rem;">Reason: {reason}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )


STRATEGY_CATEGORIES = {
    "Elder Swing": "Swing",
    "Breakout Hunter": "Breakout",
    "Aggressive Scalper": "Scalper",
    "Conservative Scalper": "Scalper",
    "Mean Reversion": "Mean Reversion",
    "Spike Catcher": "Volatility",
    "Momentum Continuation": "Momentum",
    "Compression Breakout": "Breakout",
    "Liquidity Sweep Reversal": "Institutional / Liquidity",
    "Session Breakout": "Breakout",
    "Structure Shift": "Reversal",
    "Exhaustion Reversal": "Reversal",
    "Trap Reversal": "Reversal",
    "FVG Reaction": "Institutional / Liquidity",
    "Dead Cat Bounce": "Volatility",
    "Swing Trader": "Swing",
    "Absorption": "Institutional / Liquidity"
}


def get_strategy_name_safe(strategy) -> str:
    if hasattr(strategy, "get_strategy_name"):
        try:
            return strategy.get_strategy_name()
        except Exception:
            pass
    metadata = getattr(strategy, "metadata", {})
    if isinstance(metadata, dict) and "name" in metadata:
        return metadata["name"]
    if hasattr(strategy, "STRATEGY_NAME"):
        return strategy.STRATEGY_NAME
    return strategy.__class__.__name__


def get_all_strategy_instances(engine=None):
    registry = getattr(engine, "strategy_registry", None)
    if registry and hasattr(registry, "list_registered_strategies"):
        try:
            return list(registry.list_registered_strategies())
        except Exception:
            pass

    try:
        from engine.strategy_registry import list_registered_strategies
        instances = list_registered_strategies()
    except Exception:
        instances = []

    return instances


def _strategy_key(name: str) -> str:
    return str(name or "").strip().lower()


def map_tournament_results_by_name(tournament_results):
    result_map = {}
    for res in tournament_results or []:
        res_name = res.get("strategy") or res.get("strategy_name") or res.get("name")
        if res_name:
            result_map[_strategy_key(res_name)] = res
    return result_map


def sort_strategies_by_rank(instances, tournament_by_name):
    if not tournament_by_name:
        return instances
            
    def get_rank(strat):
        name = get_strategy_name_safe(strat)
        item = tournament_by_name.get(_strategy_key(name))
        return item.get("rank", 1000) if item else 1000
        
    return sorted(instances, key=get_rank)


def get_strategy_signal(strategy, h1_df, m15_df, name, category):
    try:
        is_swing = name in ["Elder Swing", "Swing Trader"] or "Swing" in category
        df = h1_df if is_swing else m15_df
        
        if df is not None and not df.empty:
            prepared_df = strategy.prepare_indicators(df)
            sig_result = strategy.generate_signal(prepared_df)
            if isinstance(sig_result, dict):
                sig = sig_result.get("signal", "HOLD")
                strength = sig_result.get("strength", 0)
                reasons = sig_result.get("reasons", [])
                return sig, strength, reasons
            else:
                return str(sig_result), 50, []
        else:
            return "HOLD", 0, ["No market data loaded"]
    except Exception as e:
        return "HOLD", 0, [f"Signal error: {str(e)}"]


def get_rejection_reasons(strategy, h1_df, m15_df, name, category, reasons):
    if reasons:
        return reasons
        
    is_swing = name in ["Elder Swing", "Swing Trader"] or "Swing" in category
    df = h1_df if is_swing else m15_df
    
    if df is None or df.empty:
        return ["No market data loaded"]
        
    try:
        row = df.iloc[-1]
        params = strategy.params if hasattr(strategy, "params") else getattr(strategy, "default_params", {})
        rejections = []
        
        # 1. ADX Filter
        if "adx" in row:
            adx_val = row["adx"]
            adx_thresh = params.get("adx_threshold")
            if adx_thresh and adx_val < adx_thresh:
                rejections.append(f"ADX trend strength ({adx_val:.1f}) below threshold ({adx_thresh:.1f})")
                
        # 2. RSI Filter
        if "rsi" in row:
            rsi_val = row["rsi"]
            rsi_buy_min = params.get("rsi_buy_min")
            rsi_sell_max = params.get("rsi_sell_max")
            if rsi_buy_min and rsi_val <= rsi_buy_min:
                rejections.append(f"RSI ({rsi_val:.1f}) <= buy threshold ({rsi_buy_min:.1f})")
            if rsi_sell_max and rsi_val >= rsi_sell_max:
                rejections.append(f"RSI ({rsi_val:.1f}) >= sell threshold ({rsi_sell_max:.1f})")
                
        # 3. Trend Alignment (EMA Fast vs Slow)
        if "ema_fast" in row and "ema_slow" in row:
            ef = row["ema_fast"]
            es = row["ema_slow"]
            if abs(ef - es) < 0.0001:
                rejections.append("EMA Fast and Slow converged (no trend)")
                
        if not rejections:
            rejections.append("No active entry trigger met (Hold)")
            
        return rejections
    except Exception as e:
        return [f"Rejection query failed: {str(e)}"]


def _ctx_section(orch_ctx, attr: str) -> dict:
    value = getattr(orch_ctx, attr, {}) if orch_ctx else {}
    return value if isinstance(value, dict) else {}


def _fmt_console_value(value, suffix: str = "") -> str:
    if value is None or value == "":
        return "N/A"
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def _fmt_console_list(values) -> str:
    if not values:
        return "N/A"
    if isinstance(values, str):
        return values
    return ", ".join(str(item) for item in values)


def _ordered_tournament_results(tournament_results: list) -> list:
    results = list(tournament_results or [])
    return sorted(results, key=lambda item: item.get("rank", 999))


def _build_ai_decision_context(orch_ctx) -> dict:
    tournament_results = (
        st.session_state.get("tournament_results")
        or (getattr(orch_ctx, "tournament_results", []) if orch_ctx else [])
        or []
    )
    ranked_results = _ordered_tournament_results(tournament_results)
    return {
        "runtime_symbol": st.session_state.get("runtime_symbol", "UNKNOWN"),
        "market_regime": st.session_state.get("market_regime") or _ctx_section(orch_ctx, "market_regime"),
        "h4_structure": _ctx_section(orch_ctx, "h4_structure"),
        "mtf_context": st.session_state.get("mtf_context") or {
            "h1_structure": _ctx_section(orch_ctx, "h1_structure"),
            "m15_execution": _ctx_section(orch_ctx, "m15_execution"),
        },
        "execution_readiness": _ctx_section(orch_ctx, "execution_readiness"),
        "contradiction_state": _ctx_section(orch_ctx, "contradiction_engine") or _ctx_section(orch_ctx, "contradiction_state"),
        "signal_saturation": _ctx_section(orch_ctx, "signal_saturation"),
        "institutional_risk": _ctx_section(orch_ctx, "institutional_risk"),
        "tournament_results": ranked_results[:5],
        "ai_guardrails": {
            "may_generate_trades": False,
            "may_change_scores": False,
            "may_override_selection": False,
            "purpose": "Explain deterministic NexusBot outputs only.",
        },
    }


def _configure_ai_provider_from_session():
    provider = (
        st.session_state.get("sidebar_ai_provider_micro")
        or st.session_state.get("ai_provider")
        or "Deterministic Template"
    )
    st.session_state["ai_provider"] = provider
    if provider == "Deterministic Template":
        return None, "Deterministic Template selected."

    def _provider_state_key(prefix: str, provider_name: str) -> str:
        safe_provider = "".join(ch.lower() if ch.isalnum() else "_" for ch in provider_name).strip("_")
        return f"{prefix}_{safe_provider}"

    provider_key_state = _provider_state_key("ai_api_key", provider)
    sidebar_key_state = _provider_state_key("sidebar_api_key", provider)
    api_key = (
        st.session_state.get(sidebar_key_state)
        or st.session_state.get(provider_key_state)
        or st.session_state.get("ai_api_key")
        or ""
    )
    if provider == "Google Gemini":
        api_key = api_key or st.session_state.get("gemini_api_key", "")
    elif provider == "OpenRouter":
        api_key = api_key or st.session_state.get("openrouter_api_key", "")

    if api_key:
        st.session_state[provider_key_state] = api_key
        st.session_state["ai_api_key"] = api_key
        if provider == "Google Gemini":
            st.session_state["gemini_api_key"] = api_key
        elif provider == "OpenRouter":
            st.session_state["openrouter_api_key"] = api_key
    if provider in ("Google Gemini", "OpenAI", "Claude", "OpenRouter") and not api_key:
        return None, f"{provider} is selected but no API key is configured."

    model = (
        st.session_state.get(_provider_state_key("ai_model", provider))
        or st.session_state.get(_provider_state_key("sidebar_ai_model", provider))
        or st.session_state.get("ai_model")
        or ""
    )
    if provider == "OpenRouter":
        model = (
            st.session_state.get("sidebar_ai_model_openrouter")
            or st.session_state.get("openrouter_model")
            or st.session_state.get("sidebar_ai_model_openrouter_custom")
            or model
        )
        model = model or "anthropic/claude-3.5-sonnet:beta"
        st.session_state["openrouter_model"] = model
    elif provider == "Google Gemini":
        model = model or "gemini-1.5-flash"

    if model:
        st.session_state[_provider_state_key("ai_model", provider)] = model
        st.session_state["ai_model"] = model

    try:
        from providers.provider_manager import get_provider_manager
        pm = get_provider_manager()
        pm.configure({
            "provider": provider,
            "api_key": api_key,
            "model": model,
            "base_url": "",
            "temperature": 0.2,
            "max_tokens": 900,
        })
        return pm, None
    except Exception as exc:
        return None, f"AI provider unavailable: {exc}"


def _generate_deterministic_market_decision_explanation(context: dict) -> dict:
    results = context.get("tournament_results", []) or []
    top = results[0] if results else {}
    others = results[1:5]
    readiness = context.get("execution_readiness", {}) or {}
    risk = context.get("institutional_risk", {}) or {}
    contradiction = context.get("contradiction_state", {}) or {}
    saturation = context.get("signal_saturation", {}) or {}
    h4 = context.get("h4_structure", {}) or {}
    mtf = context.get("mtf_context", {}) or {}

    top_name = top.get("strategy") or top.get("strategy_name") or "N/A"
    top_fit = top.get("market_fit_score", top.get("fit_score", "N/A"))
    regime = context.get("market_regime") or {}
    regime_label = regime.get("macro_regime") or regime.get("regime") or h4.get("macro_direction") or "N/A"

    others_lines = []
    for item in others[:3]:
        name = item.get("strategy") or item.get("strategy_name") or "N/A"
        fit = item.get("market_fit_score", item.get("fit_score", "N/A"))
        penalties = []
        if item.get("contradiction_penalty") not in (None, 0, 0.0):
            penalties.append(f"contradiction penalty {item.get('contradiction_penalty')}")
        if item.get("saturation_penalty") not in (None, 0, 0.0):
            penalties.append(f"saturation penalty {item.get('saturation_penalty')}")
        if item.get("deployment_bias"):
            penalties.append(f"deployment bias {item.get('deployment_bias')}")
        if item.get("supported") is False or item.get("regime_match") is False:
            penalties.append("unsupported current regime/state")
        detail = "; ".join(penalties) if penalties else "lower tournament rank and/or lower market fit"
        others_lines.append(f"{name}: fit {fit}; {detail}.")

    risk_factors = risk.get("risk_factors") or []
    conflict_list = contradiction.get("conflicts") or []
    watch_items = list(readiness.get("readiness_gates", []) or []) + list(readiness.get("hard_blocks", []) or [])
    if saturation.get("saturation_level"):
        watch_items.append(f"Signal saturation level: {saturation.get('saturation_level')}")

    return {
        "source": "Deterministic fallback",
        "market_thesis": (
            f"{context.get('runtime_symbol', 'UNKNOWN')} is in {regime_label} context. "
            f"H4 direction={h4.get('macro_direction', 'N/A')}, strength={h4.get('macro_strength', 'N/A')}, "
            f"MTF alignment={mtf.get('alignment_score', 'N/A')}."
        ),
        "why_top_strategy_won": (
            f"{top_name} ranked #{top.get('rank', 'N/A')} with market fit {top_fit}. "
            f"Deployment bias={top.get('deployment_bias', 'N/A')}; supported regimes={_fmt_console_list(top.get('supported_regimes'))}; "
            f"dna={_fmt_console_list(top.get('dna_tags'))}."
        ),
        "why_others_were_penalized": others_lines or ["N/A"],
        "main_risks": risk_factors or conflict_list or [
            f"Risk level={risk.get('risk_level', 'N/A')}; contradiction score={contradiction.get('contradiction_score', 'N/A')}; "
            f"saturation penalty={saturation.get('saturation_penalty', 'N/A')}."
        ],
        "what_to_watch_next": watch_items or ["N/A"],
    }


def _normalize_ai_decision_explanation(ai_briefing: dict, context: dict) -> dict:
    fallback = _generate_deterministic_market_decision_explanation(context)
    if not isinstance(ai_briefing, dict):
        return fallback

    ai_meta = ai_briefing.get("_ai_meta", {}) if isinstance(ai_briefing.get("_ai_meta", {}), dict) else {}
    results = context.get("tournament_results", []) or []
    top = results[0] if results else {}
    others = results[1:4]

    return {
        "source": "AI provider",
        "ai_meta": ai_meta,
        "raw_ai_output": ai_meta.get("raw_response", ai_briefing),
        "prompt": ai_meta.get("prompt", ""),
        "usage": ai_meta.get("usage", {}),
        "market_thesis": ai_briefing.get("market_thesis") or ai_briefing.get("executive_summary") or fallback["market_thesis"],
        "why_top_strategy_won": (
            ai_briefing.get("why_top_strategy_won")
            or ai_briefing.get("deployment_context")
            or fallback["why_top_strategy_won"]
        ),
        "why_others_were_penalized": (
            ai_briefing.get("why_others_were_penalized")
            or [
                f"{item.get('strategy') or item.get('strategy_name')}: rank #{item.get('rank', 'N/A')}, "
                f"fit {item.get('market_fit_score', item.get('fit_score', 'N/A'))}, "
                f"bias {item.get('deployment_bias', 'N/A')}."
                for item in others
            ]
            or fallback["why_others_were_penalized"]
        ),
        "main_risks": ai_briefing.get("main_risks") or ai_briefing.get("key_risks") or fallback["main_risks"],
        "what_to_watch_next": (
            ai_briefing.get("what_to_watch_next")
            or ai_briefing.get("timing_summary")
            or fallback["what_to_watch_next"]
        ),
    }


def _render_ai_decision_explanation(explanation: dict) -> None:
    meta = explanation.get("ai_meta", {}) if isinstance(explanation.get("ai_meta", {}), dict) else {}
    provider = meta.get("provider") or st.session_state.get("sidebar_ai_provider_micro") or st.session_state.get("ai_provider", "N/A")
    model = meta.get("model") or (st.session_state.get("openrouter_model") if provider == "OpenRouter" else st.session_state.get("ai_model", "N/A"))
    st.caption(
        f"Provider selected: {provider}. Model: {model or 'N/A'}. Source: {explanation.get('source', 'N/A')}. "
        "AI is explanatory only and does not alter trades, scores, or selection."
    )
    st.markdown("**Market thesis**")
    st.write(explanation.get("market_thesis", "N/A"))
    st.markdown("**Why top strategy won**")
    st.write(explanation.get("why_top_strategy_won", "N/A"))
    st.markdown("**Why others were penalized**")
    others = explanation.get("why_others_were_penalized", "N/A")
    if isinstance(others, list):
        for item in others:
            st.markdown(f"- {item}")
    else:
        st.write(others)
    st.markdown("**Main risks**")
    risks = explanation.get("main_risks", "N/A")
    if isinstance(risks, list):
        for item in risks:
            st.markdown(f"- {item}")
    else:
        st.write(risks)
    st.markdown("**What to watch next**")
    watch = explanation.get("what_to_watch_next", "N/A")
    if isinstance(watch, list):
        for item in watch:
            st.markdown(f"- {item}")
    else:
        st.write(watch)


def _render_ai_trace(ai_result: dict, deterministic_result: dict) -> None:
    if ai_result:
        meta = ai_result.get("ai_meta", {}) or {}
        usage = ai_result.get("usage") or meta.get("usage") or {}
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("AI Provider", meta.get("provider", st.session_state.get("ai_provider", "N/A")))
        c2.metric("AI Model", meta.get("model", st.session_state.get("ai_model", "N/A")))
        c3.metric("Prompt Tokens", usage.get("prompt_tokens", usage.get("input_tokens", "N/A")))
        c4.metric("Completion Tokens", usage.get("completion_tokens", usage.get("output_tokens", "N/A")))
        if usage:
            st.caption(f"Usage raw: {usage}")
        if meta.get("finish_reason"):
            st.caption(f"Finish reason: {meta.get('finish_reason')}")
        if meta.get("id"):
            st.caption(f"Request ID: {meta.get('id')}")

        with st.expander("Prompt Sent To AI", expanded=False):
            st.code(ai_result.get("prompt") or meta.get("prompt") or "Prompt unavailable for this provider.", language="text")
        with st.expander("Raw AI Output Captured", expanded=False):
            raw_output = ai_result.get("raw_ai_output") or meta.get("raw_response") or ai_result
            if isinstance(raw_output, (dict, list)):
                st.json(raw_output)
            else:
                st.code(str(raw_output), language="text")

    with st.expander("Deterministic Safety Layer Output", expanded=False):
        st.caption("This is generated on every click and remains the deterministic reference. AI can explain it, not override it.")
        st.json(deterministic_result)


def render_strategy_deployment_console(state, engine, orch_ctx) -> None:
    tournament_results = (
        st.session_state.get("tournament_results")
        or (getattr(orch_ctx, "tournament_results", []) if orch_ctx else [])
        or []
    )
    ranked_results = _ordered_tournament_results(tournament_results)

    st.markdown("<h3 style='margin-top:28px; margin-bottom:2px;'>Strategy Deployment Console</h3>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#64748b; font-size:0.85rem; margin-top:0; margin-bottom:16px;'>"
        "Deterministic explanation of the selected strategy from tournament and orchestration data.</p>",
        unsafe_allow_html=True,
    )

    if not ranked_results:
        st.info("No tournament results available yet. Run the intelligence pipeline to populate deployment selection data.")
        return

    selected = ranked_results[0]
    readiness = _ctx_section(orch_ctx, "execution_readiness")
    contradiction = _ctx_section(orch_ctx, "contradiction_engine") or _ctx_section(orch_ctx, "contradiction_state")
    saturation = _ctx_section(orch_ctx, "signal_saturation")
    confidence = _ctx_section(orch_ctx, "confidence_hierarchy")
    institutional_risk = _ctx_section(orch_ctx, "institutional_risk")

    selected_name = selected.get("strategy") or selected.get("strategy_name") or "N/A"
    market_fit = selected.get("market_fit_score", selected.get("fit_score"))
    readiness_label = readiness.get("execution_state")
    readiness_score = readiness.get("readiness_score")
    readiness_text = (
        f"{readiness_label} ({readiness_score:.1f}%)"
        if readiness_label and isinstance(readiness_score, (int, float))
        else _fmt_console_value(readiness_label or readiness_score)
    )
    risk_level = selected.get("risk_level") or institutional_risk.get("risk_level")
    contradiction_penalty = selected.get("contradiction_penalty", contradiction.get("deployment_penalty"))
    saturation_penalty = selected.get("saturation_penalty", saturation.get("saturation_penalty"))
    confidence_level = confidence.get("confidence_level")

    metric_cols = st.columns(4)
    metric_cols[0].metric("Selected Strategy", selected_name)
    metric_cols[1].metric("Rank", _fmt_console_value(selected.get("rank")))
    metric_cols[2].metric("Market Fit", _fmt_console_value(market_fit, "%") if isinstance(market_fit, (int, float)) else "N/A")
    metric_cols[3].metric("Readiness", readiness_text)

    metric_cols = st.columns(4)
    metric_cols[0].metric("Deployment Bias", _fmt_console_value(selected.get("deployment_bias")))
    metric_cols[1].metric("Risk Level", _fmt_console_value(risk_level))
    metric_cols[2].metric("Contradiction Penalty", _fmt_console_value(contradiction_penalty))
    metric_cols[3].metric("Confidence Level", _fmt_console_value(confidence_level))
    st.caption(f"Saturation Penalty: {_fmt_console_value(saturation_penalty)}")

    score_breakdown = selected.get("score_breakdown") or {}
    confidence_breakdown = selected.get("confidence_breakdown") or {}
    dna_tags = selected.get("dna_tags") or []
    supported_regimes = selected.get("supported_regimes") or []
    readiness_gates = list(readiness.get("readiness_gates", []) or []) + list(readiness.get("hard_blocks", []) or [])
    conflicts = contradiction.get("conflicts", []) or []

    with st.expander("Why selected", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Score Breakdown**")
            if score_breakdown:
                st.dataframe(pd.DataFrame([score_breakdown]).T.rename(columns={0: "value"}), use_container_width=True)
            else:
                st.caption("N/A")

            st.markdown("**DNA Tags**")
            st.caption(_fmt_console_list(dna_tags))

            st.markdown("**Supported Regimes**")
            st.caption(_fmt_console_list(supported_regimes))

        with c2:
            st.markdown("**Confidence Breakdown**")
            if confidence_breakdown:
                st.dataframe(pd.DataFrame([confidence_breakdown]).T.rename(columns={0: "value"}), use_container_width=True)
            else:
                st.caption("N/A")

            st.markdown("**Readiness Gates**")
            if readiness_gates:
                for gate in readiness_gates:
                    st.markdown(f"- {gate}")
            else:
                st.caption("N/A")

            st.markdown("**Conflicts**")
            if conflicts:
                for conflict in conflicts:
                    st.markdown(f"- {conflict}")
            else:
                st.caption("N/A")

    with st.expander("Why others were not selected", expanded=True):
        next_results = ranked_results[1:4]
        if not next_results:
            st.caption("No additional ranked strategies available.")
        for item in next_results:
            name = item.get("strategy") or item.get("strategy_name") or "N/A"
            fit = item.get("market_fit_score", item.get("fit_score"))
            fit_gap = None
            if isinstance(market_fit, (int, float)) and isinstance(fit, (int, float)):
                fit_gap = round(float(market_fit) - float(fit), 1)

            reasons = []
            if fit_gap is not None:
                reasons.append(f"Market fit was {fit_gap:.1f} points below the selected strategy.")
            if item.get("deployment_bias"):
                reasons.append(f"Deployment bias: {item.get('deployment_bias')}.")
            if item.get("supported") is False or item.get("regime_match") is False:
                reasons.append("Current regime/state support flag was false.")
            if item.get("contradiction_penalty") not in (None, 0, 0.0):
                reasons.append(f"Contradiction penalty: {item.get('contradiction_penalty')}.")
            if item.get("saturation_penalty") not in (None, 0, 0.0):
                reasons.append(f"Saturation penalty: {item.get('saturation_penalty')}.")
            score_parts = item.get("score_breakdown") or {}
            penalty_parts = {
                key: value for key, value in score_parts.items()
                if "pen" in key.lower() and value not in (None, 0, 0.0)
            }
            if penalty_parts:
                reasons.append(
                    "Score penalties: "
                    + ", ".join(f"{key}={value}" for key, value in penalty_parts.items())
                    + "."
                )
            if not reasons:
                reasons.append("Tournament rank is lower than the selected strategy; no additional penalty fields were present.")

            st.markdown(f"**#{item.get('rank', 'N/A')} {name}** — fit: {_fmt_console_value(fit, '%') if isinstance(fit, (int, float)) else 'N/A'}")
            for reason in reasons:
                st.markdown(f"- {reason}")

    if st.button("Explain Current Market Decision", key="btn_explain_market_decision", use_container_width=True):
        context = _build_ai_decision_context(orch_ctx)
        deterministic_explanation = _generate_deterministic_market_decision_explanation(context)
        deterministic_explanation["source"] = "Deterministic layer"
        st.session_state["deterministic_market_decision_explanation"] = deterministic_explanation
        pm, unavailable_reason = _configure_ai_provider_from_session()
        ai_explanation = None
        if pm:
            try:
                with st.spinner("Generating explanatory briefing from configured AI provider..."):
                    provider_obj = getattr(pm, "active_provider", None)
                    if provider_obj is None:
                        raise RuntimeError("No active AI provider configured.")
                    ai_briefing = provider_obj.generate_briefing(context)
                ai_explanation = _normalize_ai_decision_explanation(ai_briefing, context)
                explanation = ai_explanation
            except Exception as exc:
                explanation = dict(deterministic_explanation)
                explanation["source"] = f"Deterministic fallback (AI failed: {exc})"
        else:
            explanation = dict(deterministic_explanation)
            explanation["source"] = f"Deterministic fallback ({unavailable_reason})"
        if ai_explanation:
            st.session_state["ai_market_decision_ai_result"] = ai_explanation
        else:
            st.session_state["ai_market_decision_ai_result"] = None
        st.session_state["ai_market_decision_explanation"] = explanation

    if st.session_state.get("ai_market_decision_explanation"):
        with st.expander("AI Explanation Layer", expanded=True):
            _render_ai_decision_explanation(st.session_state["ai_market_decision_explanation"])
            _render_ai_trace(
                st.session_state.get("ai_market_decision_ai_result"),
                st.session_state.get("deterministic_market_decision_explanation")
                or _generate_deterministic_market_decision_explanation(_build_ai_decision_context(orch_ctx)),
            )


def render_strategy_arsenal(state, engine, orch_ctx) -> None:
    st.markdown("<h3 style='margin-top:35px; margin-bottom:2px;'>🎯 Strategy Arsenal / Persona Layer</h3>", unsafe_allow_html=True)
    st.markdown("<p style='color:#64748b; font-size:0.85rem; margin-top:0; margin-bottom:25px;'>Live visibility of all strategy profiles participating in tournament selection and market-state routing.</p>", unsafe_allow_html=True)
    
    light_theme = st.session_state.get("ui_theme", "Dark") == "Light"
    card_bg = "#ffffff" if light_theme else "rgba(17,24,39,0.75)"
    card_text = "#0f172a" if light_theme else "#f8fafc"
    card_value = "#1e293b" if light_theme else "#cbd5e1"
    card_label = "#64748b"
    card_muted = "#475569" if light_theme else "#94a3b8"
    card_border_default = "#d8e1ee" if light_theme else "#1e293b"
    card_progress_bg = "#e2e8f0" if light_theme else "#1e293b"
    card_footer_border = "#e2e8f0" if light_theme else "#1e293b"
    card_shadow = "box-shadow:0 10px 24px rgba(15,23,42,0.08);" if light_theme else ""
    winner_bg = "background:#ecfdf5;" if light_theme else "background: rgba(34, 197, 94, 0.1);"
    winner_glow = "box-shadow:0 10px 28px rgba(22,163,74,0.12);" if light_theme else "box-shadow: 0 0 10px rgba(34, 197, 94, 0.2);"

    h1_df = st.session_state.get("h1_df")
    m15_df = st.session_state.get("m15_df")
    
    # Retrieve tournament standings and exclusion logs
    tournament_results = st.session_state.get("tournament_results") or (getattr(orch_ctx, "tournament_results", []) if orch_ctx else [])
    market_explainer = st.session_state.get("market_explainer") or (getattr(orch_ctx, "market_explainer", {}) if orch_ctx else {})
    rejections = market_explainer.get("strategy_rejections", {})
    tournament_by_name = map_tournament_results_by_name(tournament_results)
    
    candidates = getattr(orch_ctx, "execution_candidates", []) or []
    candidates_by_name = {
        _strategy_key(cand.get("strategy") or cand.get("strategy_name")): cand
        for cand in candidates
        if cand.get("strategy") or cand.get("strategy_name")
    }
    
    instances = get_all_strategy_instances(engine)
    show_mode = st.radio(
        "Strategy Arsenal View",
        options=["Show all strategies", "Show ranked only"],
        index=0,
        horizontal=True,
        key="strategy_arsenal_view_mode",
    )
    sorted_instances = sort_strategies_by_rank(instances, tournament_by_name)
    if show_mode == "Show ranked only":
        sorted_instances = [
            strategy for strategy in sorted_instances
            if _strategy_key(get_strategy_name_safe(strategy)) in tournament_by_name
        ]
    if not sorted_instances:
        st.info("No ranked tournament results yet. Switch to Show all strategies to view the full registered arsenal.")
        return
    
    cols = st.columns(3)
    
    for idx, strategy in enumerate(sorted_instances):
        col = cols[idx % 3]
        name = get_strategy_name_safe(strategy)
        name_key = _strategy_key(name)
        category = STRATEGY_CATEGORIES.get(name, "Quantitative")
        
        # 1. Match tournament results
        tourney_item = tournament_by_name.get(name_key)
                    
        # 2. Match candidate
        cand_item = candidates_by_name.get(name_key)
                
        # 3. Determine status and badge color
        is_winner = tourney_item and tourney_item.get("rank") == 1
        is_rejected = name in rejections or name.lower() in [k.lower() for k in rejections.keys()]
        
        # Determine rejection reason if blocked
        reject_reason = None
        if is_rejected:
            for r_key, r_val in rejections.items():
                if r_key.lower() == name.lower():
                    reject_reason = r_val
                    break
        
        if is_winner:
            status_label = "ACTIVE"
            badge_color = "#22c55e" # neon green
            bg_glow = winner_glow
            border_style = "border: 1px solid #16a34a;" if light_theme else "border: 1px solid #22c55e;"
        elif is_rejected:
            status_label = "BLOCKED"
            badge_color = "#ef4444" # red
            bg_glow = ""
            border_style = "border: 1px solid rgba(220, 38, 38, 0.35);" if light_theme else "border: 1px solid rgba(239, 68, 68, 0.3);"
        elif tourney_item:
            bias = tourney_item.get("deployment_bias", "")
            fit_score = tourney_item.get("market_fit_score", 0.0)
            if fit_score < 50.0 or bias == "AVOID":
                status_label = "LOW FIT"
                badge_color = "#f97316" # orange
                border_style = "border: 1px solid rgba(234, 88, 12, 0.40);" if light_theme else "border: 1px solid rgba(249, 115, 22, 0.3);"
            elif bias == "READY":
                status_label = "ELIGIBLE"
                badge_color = "#3b82f6" # blue
                border_style = "border: 1px solid rgba(37, 99, 235, 0.40);" if light_theme else "border: 1px solid rgba(59, 130, 246, 0.3);"
            else:
                status_label = "STANDBY"
                badge_color = "#64748b" # gray
                border_style = f"border: 1px solid {card_border_default};"
            bg_glow = ""
        else:
            status_label = "STANDBY"
            badge_color = "#64748b" # gray
            bg_glow = ""
            border_style = f"border: 1px solid {card_border_default};"
            
        # 4. Get fit score
        fit_score = "N/A"
        if tourney_item:
            fit_score = tourney_item.get("market_fit_score") or tourney_item.get("fit_score", "N/A")
            
        # 5. Get deployment confidence
        confidence_val = "N/A"
        if cand_item:
            confidence_val = cand_item.get("confidence", "N/A")
        elif tourney_item and "confidence_score" in tourney_item:
            confidence_val = tourney_item["confidence_score"]
            
        # 6. Generate signal
        if tourney_item:
            sig, sig_strength, sig_reasons = get_strategy_signal(strategy, h1_df, m15_df, name, category)
        else:
            sig, sig_strength, sig_reasons = "N/A", "N/A", []
        
        # Color coding for signal
        sig_colors = {"BUY": "#22c55e", "SELL": "#ef4444", "HOLD": "#64748b"}
        sig_color = sig_colors.get(sig, "#64748b")
        
        # Risk levels
        risk_level = "N/A"
        metadata = getattr(strategy, "metadata", {})
        if isinstance(metadata, dict):
            risk_level = metadata.get("risk_level", "MEDIUM")
        risk_colors = {"LOW": "#22c55e", "MEDIUM": "#f59e0b", "HIGH": "#ef4444"}
        risk_color = risk_colors.get(str(risk_level).upper(), "#64748b")
        
        # Supported regimes & states
        supported_regimes = strategy.get_supported_regimes() if hasattr(strategy, "get_supported_regimes") else []
        supported_states = strategy.get_supported_market_states() if hasattr(strategy, "get_supported_market_states") else []
        
        regimes_str = ", ".join(supported_regimes) if supported_regimes else "N/A"
        states_str = ", ".join(supported_states) if supported_states else "N/A"
        
        # Format recommended timeframes & markets
        tf_list = metadata.get("supported_timeframes", []) if isinstance(metadata, dict) else []
        tfs_str = ", ".join(tf_list) if tf_list else "N/A"
        
        mkt_list = metadata.get("recommended_markets", []) if isinstance(metadata, dict) else []
        mkts_str = ", ".join(mkt_list) if mkt_list else "N/A"

        params = strategy.get_default_parameters() if hasattr(strategy, "get_default_parameters") else getattr(strategy, "default_params", {})
        if not params:
            params = getattr(strategy, "params", {})
        if params:
            params_preview = ", ".join([f"{k}: {v}" for k, v in list(params.items())[:3]])
            if len(params) > 3:
                params_preview += f", +{len(params) - 3} more"
        else:
            params_preview = "N/A"
        
        # Build HTML card
        with col:
            # Highlight header background if winning
            header_bg = winner_bg if is_winner else ""
            
            fit_pct_str = f"{fit_score:.1f}%" if isinstance(fit_score, (int, float)) else "N/A"
            conf_pct_str = f"{confidence_val:.1f}%" if isinstance(confidence_val, (int, float)) else "N/A"
            rank_str = f"#{tourney_item['rank']}" if tourney_item and "rank" in tourney_item else "N/A"
            strength_str = f"{sig_strength}/100" if isinstance(sig_strength, (int, float)) else "N/A"
            
            card_html = f"""
            <div style="background:{card_bg}; {border_style} border-radius:8px; padding:14px; margin-bottom:12px; {card_shadow} {bg_glow}">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; {header_bg} padding: 4px; border-radius:4px;">
                    <span style="font-size:0.9rem; font-weight:800; color:{card_text};">
                        {rank_str if rank_str != "N/A" else ""} {name}
                    </span>
                    <span style="background:{badge_color}1a; border:1px solid {badge_color}44; color:{badge_color}; font-size:0.6rem; font-weight:800; padding:2px 8px; border-radius:12px; text-transform:uppercase;">
                        {status_label}
                    </span>
                </div>
                
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; font-size:0.75rem; margin-bottom:12px;">
                    <div>
                        <span style="color:{card_label}; display:block; text-transform:uppercase; font-size:0.6rem;">Rank</span>
                        <strong style="color:{card_value};">{rank_str}</strong>
                    </div>
                    <div>
                        <span style="color:{card_label}; display:block; text-transform:uppercase; font-size:0.6rem;">Risk Profile</span>
                        <strong style="color:{risk_color};">{risk_level}</strong>
                    </div>
                    <div>
                        <span style="color:{card_label}; display:block; text-transform:uppercase; font-size:0.6rem;">Persona</span>
                        <strong style="color:{card_value};">{category}</strong>
                    </div>
                    <div>
                        <span style="color:{card_label}; display:block; text-transform:uppercase; font-size:0.6rem;">Market Fit</span>
                        <strong style="color:{card_value};">{fit_pct_str}</strong>
                    </div>
                    <div>
                        <span style="color:{card_label}; display:block; text-transform:uppercase; font-size:0.6rem;">Current Signal</span>
                        <strong style="color:{sig_color};">{sig}</strong>
                    </div>
                    <div>
                        <span style="color:{card_label}; display:block; text-transform:uppercase; font-size:0.6rem;">Strength</span>
                        <strong style="color:{card_value};">{strength_str}</strong>
                    </div>
                    <div style="grid-column:1 / span 2;">
                        <span style="color:{card_label}; display:block; text-transform:uppercase; font-size:0.6rem;">Params</span>
                        <strong style="color:{card_value};">{params_preview}</strong>
                    </div>
                </div>
                
                <!-- Fit & Confidence Progress Bars -->
                {f'''
                <div style="margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between; font-size:0.65rem; color:{card_muted}; margin-bottom:2px;">
                        <span>Market Fit Score</span>
                        <strong>{fit_score:.1f}%</strong>
                    </div>
                    <div style="background:{card_progress_bg}; border-radius:3px; height:4px; overflow:hidden;">
                        <div style="width: {min(100.0, max(0.0, fit_score)):.1f}%; background: linear-gradient(90deg, #3b82f6, #22c55e); height:100%;"></div>
                    </div>
                </div>
                ''' if isinstance(fit_score, (int, float)) else ''}
                
                {f'''
                <div style="margin-bottom:12px;">
                    <div style="display:flex; justify-content:space-between; font-size:0.65rem; color:{card_muted}; margin-bottom:2px;">
                        <span>Deployment Confidence</span>
                        <strong>{confidence_val:.1f}%</strong>
                    </div>
                    <div style="background:{card_progress_bg}; border-radius:3px; height:4px; overflow:hidden;">
                        <div style="width: {min(100.0, max(0.0, confidence_val)):.1f}%; background: linear-gradient(90deg, #3b82f6, #06b6d4); height:100%;"></div>
                    </div>
                </div>
                ''' if isinstance(confidence_val, (int, float)) else ''}
                
                <div style="border-top:1px solid {card_footer_border}; padding-top:6px; font-size:0.65rem; color:{card_muted};">
                    <div style="margin-bottom:2px;"><b>Regimes:</b> <span style="color:{card_value};">{regimes_str}</span></div>
                    <div><b>States:</b> <span style="color:{card_value};">{states_str}</span></div>
                </div>
            </div>
            """
            card_html_clean = "\n".join([line.strip() for line in card_html.split("\n")])
            st.markdown(card_html_clean, unsafe_allow_html=True)
            
            # Diagnostic & Parameters Expander
            with st.expander("🔍 Diagnostics & Parameters", expanded=False):
                # Parameters
                st.markdown("**Default Parameters:**")
                if params:
                    param_text = ", ".join([f"`{k}`: {v}" for k, v in list(params.items())[:6]])
                    if len(params) > 6:
                        param_text += f", ... (+{len(params)-6} more)"
                    st.caption(param_text)
                else:
                    st.caption("N/A")
                    
                # Signal details
                if sig == "HOLD":
                    rej_reasons = get_rejection_reasons(strategy, h1_df, m15_df, name, category, sig_reasons)
                    st.markdown("**Rejection reasons:**")
                    for r in rej_reasons:
                        st.markdown(f"- {r}")
                else:
                    if sig_reasons:
                        st.markdown("**Signal reasons:**")
                        for r in sig_reasons:
                            st.markdown(f"- {r}")
                            
                # Supported regimes and market states
                st.markdown(f"**Supported Regimes:** `{regimes_str}`")
                st.markdown(f"**Supported Market States:** `{states_str}`")
                st.markdown(f"**Recommended Timeframes:** `{tfs_str}` | **Recommended Markets:** `{mkts_str}`")

                # Confidence Breakdown
                st.markdown("**Confidence Breakdown:**")
                if tourney_item and tourney_item.get("confidence_breakdown"):
                    cb = tourney_item["confidence_breakdown"]
                    cb_text = "  \n".join([f"- {k.replace('_', ' ').title()}: `{v}`" for k, v in cb.items()])
                    st.markdown(cb_text)
                else:
                    st.caption("N/A")
                    
                # Penalties and contradictions
                if tourney_item:
                    st.markdown("**Penalties & Contradictions:**")
                    score_breakdown = tourney_item.get("score_breakdown", {})
                    penalties_list = []
                    for k, v in score_breakdown.items():
                        if "pen" in k or "penalty" in k:
                            if v != 0:
                                penalties_list.append(f"- {k.replace('_', ' ').title()}: `{v}`")
                    
                    contra_penalty = tourney_item.get("contradiction_penalty", 0.0)
                    if contra_penalty != 0:
                        penalties_list.append(f"- Contradiction Penalty: `{contra_penalty}`")
                        
                    if penalties_list:
                        st.markdown("  \n".join(penalties_list))
                    else:
                        st.caption("No penalties or contradictions applied.")
                else:
                    st.caption("N/A (Not ranked in tournament)")
                    
                # Selection / Rejection / Readiness notes
                st.markdown(f"**Readiness & Tournament Notes:**")
                if is_winner:
                    st.info("Winning strategy: Highest overall multi-timeframe market fit and alignment score.")
                elif reject_reason:
                    st.warning(reject_reason)
                elif tourney_item:
                    bias = tourney_item.get("deployment_bias", "")
                    st.caption(f"Ranked #{tourney_item['rank']} | Fit score: {fit_score:.1f}% | Deployment Bias: {bias}")
                else:
                    st.caption("Not eligible for current market regime / state.")

