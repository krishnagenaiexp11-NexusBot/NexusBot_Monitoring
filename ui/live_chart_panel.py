"""
ui/live_chart_panel.py
Lightweight presentational panel for Plotly candlestick rendering.
"""
import time
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from ui.components.tradingview_chart import render_tradingview_chart


CHART_ASSET_SYMBOLS = {
    "Forex": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"],
    "Indices": ["US30", "US100", "US500", "GER40", "UK100", "JP225"],
    "Commodities": ["XAUUSD", "XAGUSD", "USOIL", "UKOIL", "NATGAS"],
    "Crypto": ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD"],
    "Stocks": ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL"],
    "Custom": [],
}
CHART_TIMEFRAMES = ["M1", "M5", "M15", "H1", "H4", "D1"]
CHART_TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 5 * 60,
    "M15": 15 * 60,
    "H1": 60 * 60,
    "H4": 4 * 60 * 60,
    "D1": 24 * 60 * 60,
}


def _asset_class_for_chart_symbol(symbol: str) -> str:
    symbol = str(symbol or "").strip().upper()
    for asset_class, symbols in CHART_ASSET_SYMBOLS.items():
        if symbol in symbols:
            return asset_class
    return "Custom"


def init_chart_state(default_symbol: str = "UNKNOWN") -> None:
    symbol = str(default_symbol or "UNKNOWN").strip().upper() or "UNKNOWN"
    asset_class = _asset_class_for_chart_symbol(symbol)
    runtime_tf = str(st.session_state.get("runtime_timeframe") or "M5").upper()
    if runtime_tf not in CHART_TIMEFRAMES:
        runtime_tf = "M5"
    defaults = {
        "chart_asset_class": asset_class,
        "chart_symbol": symbol,
        "chart_timeframe": runtime_tf,
        "chart_auto_refresh": True,
        "chart_refresh_interval": 5,
        "_chart_last_refresh_at": 0.0,
        "_chart_last_symbol": symbol,
        "_chart_last_timeframe": runtime_tf,
        "_chart_last_candle_bucket": None,
        "_chart_refresh_nonce": 0,
        "_chart_cached_figure": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_chart_controls(default_symbol: str = "UNKNOWN") -> dict:
    init_chart_state(default_symbol)
    runtime_symbol = str(default_symbol or st.session_state.get("runtime_symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"
    if runtime_symbol != "UNKNOWN" and st.session_state.get("chart_symbol") != runtime_symbol:
        st.session_state["chart_symbol"] = runtime_symbol
        st.session_state["chart_asset_class"] = _asset_class_for_chart_symbol(runtime_symbol)

    current_symbol = str(st.session_state.get("chart_symbol") or default_symbol or "UNKNOWN").upper()
    symbols = [
        str(sym).strip().upper()
        for sym in st.session_state.get("runtime_symbols", [current_symbol])
        if str(sym).strip()
    ] or [current_symbol]
    if current_symbol not in symbols:
        current_symbol = symbols[0]
    asset_class = _asset_class_for_chart_symbol(current_symbol)
    if st.session_state.get("chart_symbol_from_basket") not in symbols:
        st.session_state["chart_symbol_from_basket"] = current_symbol

    ctl_cols = st.columns([1.5, 0.9, 0.9, 0.9])

    with ctl_cols[0]:
        selected_symbol = st.selectbox(
            "Symbol",
            symbols,
            index=symbols.index(current_symbol) if current_symbol in symbols else 0,
            key="chart_symbol_from_basket",
        )

    selected_symbol = str(selected_symbol or "UNKNOWN").strip().upper() or "UNKNOWN"
    previous_symbol = str(st.session_state.get("chart_symbol") or "").upper()
    symbol_changed = selected_symbol != previous_symbol
    st.session_state["chart_symbol"] = selected_symbol
    if selected_symbol != st.session_state.get("runtime_symbol"):
        st.session_state["runtime_symbol"] = selected_symbol

    with ctl_cols[1]:
        current_tf = st.session_state.get("runtime_timeframe") or st.session_state.get("chart_timeframe", "H1")
        if current_tf not in CHART_TIMEFRAMES:
            current_tf = "M5"
        if st.session_state.get("chart_timeframe") != current_tf:
            st.session_state["chart_timeframe"] = current_tf
        timeframe = st.selectbox(
            "Timeframe",
            CHART_TIMEFRAMES,
            index=CHART_TIMEFRAMES.index(current_tf),
            key="chart_timeframe",
        )
        st.session_state["runtime_timeframe"] = timeframe

    with ctl_cols[2]:
        auto_refresh = st.toggle(
            "Auto-refresh",
            value=bool(st.session_state.get("chart_auto_refresh", False)),
            key="chart_auto_refresh",
        )
        interval = st.number_input(
            "Interval (sec)",
            min_value=5,
            max_value=3600,
            value=int(st.session_state.get("chart_refresh_interval", 30)),
            step=5,
            key="chart_refresh_interval",
            disabled=not auto_refresh,
        )

    with ctl_cols[3]:
        st.write("")
        manual_refresh = st.button(
            "Manual Refresh",
            key="chart_manual_refresh",
            use_container_width=True,
        )

    now = time.time()
    previous_timeframe = st.session_state.get("_chart_last_timeframe")
    timeframe_changed = timeframe != previous_timeframe
    tf_seconds = CHART_TIMEFRAME_SECONDS.get(timeframe, 60)
    current_candle_bucket = int(now // tf_seconds)
    last_candle_bucket = st.session_state.get("_chart_last_candle_bucket")
    new_candle = bool(last_candle_bucket is not None and current_candle_bucket != last_candle_bucket)
    should_refresh = symbol_changed or timeframe_changed or manual_refresh or new_candle

    if should_refresh:
        st.session_state["_chart_last_refresh_at"] = now
        st.session_state["_chart_last_symbol"] = selected_symbol
        st.session_state["_chart_last_timeframe"] = timeframe
        st.session_state["_chart_refresh_nonce"] = int(st.session_state.get("_chart_refresh_nonce", 0)) + 1
    st.session_state["_chart_last_candle_bucket"] = current_candle_bucket

    return {
        "asset_class": asset_class,
        "symbol": selected_symbol,
        "timeframe": timeframe,
        "auto_refresh": auto_refresh,
        "refresh_interval": int(interval),
        "should_refresh": should_refresh,
        "manual_refresh": manual_refresh,
        "symbol_changed": symbol_changed,
        "timeframe_changed": timeframe_changed,
        "new_candle": new_candle,
    }


def _build_live_chart_figure(
    df: pd.DataFrame,
    active_positions: list,
    active_candidates: list,
    strategy_markers: list,
    current_regime: str,
    window_size: int,
):
    light_theme = st.session_state.get("ui_theme", "Dark") == "Light"
    chart_bg = "#ffffff" if light_theme else "rgba(0,0,0,0)"
    plot_bg = "#ffffff" if light_theme else "rgba(0,0,0,0)"
    grid_color = "#d8e1ee" if light_theme else "rgba(30, 41, 59, 0.4)"
    axis_color = "#94a3b8" if light_theme else "#334155"
    tick_color = "#475569" if light_theme else "#64748b"
    legend_bg = "rgba(255,255,255,0.92)" if light_theme else "rgba(15,23,42,0.88)"
    legend_border = "#d8e1ee" if light_theme else "#334155"
    legend_text = "#0f172a" if light_theme else "#cbd5e1"
    annotation_bg = "#ffffff" if light_theme else "#0f172a"

    # Standardize column casing
    plot_df = df.copy()
    plot_df.columns = [col.lower() for col in plot_df.columns]

    # Cap window size
    plot_df = plot_df.iloc[-window_size:]

    time_col = 'timestamp' if 'timestamp' in plot_df.columns else plot_df.index

    # Create Candlestick chart
    fig = go.Figure(data=[go.Candlestick(
        x=plot_df[time_col],
        open=plot_df['open'],
        high=plot_df['high'],
        low=plot_df['low'],
        close=plot_df['close'],
        name="Candles",
        line=dict(width=1.0),
        increasing_line_color='#22c55e',
        increasing_fillcolor='rgba(34, 197, 94, 0.2)',
        decreasing_line_color='#ef4444',
        decreasing_fillcolor='rgba(239, 68, 68, 0.2)'
    )])

    # Add Regime Background Shading
    regime_colors = {
        "TRENDING": "rgba(34, 197, 94, 0.04)",
        "RANGING": "rgba(59, 130, 246, 0.04)",
        "VOLATILE": "rgba(245, 158, 11, 0.04)",
        "LOW_VOLATILITY": "rgba(148, 163, 184, 0.04)",
        "NEUTRAL": "rgba(148, 163, 184, 0.02)"
    }
    bg_color = regime_colors.get(str(current_regime).upper(), "rgba(148, 163, 184, 0.02)")

    fig.add_vrect(
        x0=plot_df[time_col].iloc[0],
        x1=plot_df[time_col].iloc[-1],
        fillcolor=bg_color,
        opacity=1.0,
        layer="below",
        line_width=0,
    )

    # Add Active Position Markers
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

    # Add Candidate Signal Markers
    last_time = plot_df[time_col].iloc[-1]
    last_price = plot_df['close'].iloc[-1]

    marker_df = pd.DataFrame(strategy_markers or [])
    if not marker_df.empty:
        marker_df["timestamp"] = pd.to_datetime(marker_df["timestamp"], errors="coerce")
        marker_df = marker_df.dropna(subset=["timestamp"])
        if not marker_df.empty:
            visible_start = pd.to_datetime(plot_df[time_col].iloc[0])
            visible_end = pd.to_datetime(plot_df[time_col].iloc[-1])
            marker_df = marker_df[
                (marker_df["timestamp"] >= visible_start)
                & (marker_df["timestamp"] <= visible_end)
            ]
        if not marker_df.empty:
            buy_df = marker_df[marker_df["signal"].isin(["BUY", "BULLISH", "UP"])]
            sell_df = marker_df[marker_df["signal"].isin(["SELL", "BEARISH", "DOWN"])]
            if not buy_df.empty:
                fig.add_trace(go.Scatter(
                    x=buy_df["timestamp"],
                    y=buy_df["price"],
                    mode="markers",
                marker=dict(symbol="triangle-up", size=12, color="#16a34a", line=dict(width=1, color="#052e16")),
                    name="Historical BUY",
                    text=buy_df["label"],
                    hovertemplate="%{text}<br>%{x}<br>Price %{y}<extra></extra>",
                ))
            if not sell_df.empty:
                fig.add_trace(go.Scatter(
                    x=sell_df["timestamp"],
                    y=sell_df["price"],
                    mode="markers",
                marker=dict(symbol="triangle-down", size=12, color="#dc2626", line=dict(width=1, color="#450a0a")),
                    name="Historical SELL",
                    text=sell_df["label"],
                    hovertemplate="%{text}<br>%{x}<br>Price %{y}<extra></extra>",
                ))

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
                bgcolor=annotation_bg,
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
                bgcolor=annotation_bg,
                bordercolor="#ef4444",
                borderwidth=1,
                borderpad=4
            )

    # Set custom Bloomberg-style layout
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        paper_bgcolor=chart_bg,
        plot_bgcolor=plot_bg,
        margin=dict(l=8, r=8, t=8, b=8),
        hovermode="x unified",
        xaxis=dict(
            gridcolor=grid_color,
            tickfont=dict(color=tick_color, family="Inter"),
            linecolor=axis_color,
            zerolinecolor=grid_color,
        ),
        yaxis=dict(
            gridcolor=grid_color,
            tickfont=dict(color=tick_color, family="Inter"),
            linecolor=axis_color,
            zerolinecolor=grid_color,
            side="right"
        ),
        height=520,
        showlegend=bool(strategy_markers),
        legend=dict(
            bgcolor=legend_bg,
            bordercolor=legend_border,
            borderwidth=1,
            font=dict(color=legend_text, family="Inter", size=11),
            orientation="v",
            x=1.01,
            y=1.0,
        ),
    )
    return fig


def render_live_chart(
    df: pd.DataFrame,
    active_positions: list,
    active_candidates: list,
    current_regime: str,
    strategy_markers: list | None = None,
    window_size: int = 200,
    refresh_allowed: bool = False,
) -> None:
    """
    Renders the primary institutional live chart using TradingView
    Lightweight Charts. The browser-side component preserves zoom/pan and
    updates candle/marker/zone payloads without relying on Plotly rerenders.
    """
    if df is None or df.empty:
        st.info("No market data loaded yet. Connect to MT5 or Ingest a CSV in Step 1 to populate the chart.")
        return

    active_plan = st.session_state.get("active_trade_plan") or {}
    if not active_plan and active_candidates:
        candidate = active_candidates[0] or {}
        has_real_plan = bool(candidate.get("stop_loss") or candidate.get("sl")) and bool(candidate.get("take_profit") or candidate.get("tp"))
        active_plan = candidate if has_real_plan else {}
    render_tradingview_chart(
        df=df,
        runtime_symbol=str(st.session_state.get("runtime_symbol") or st.session_state.get("chart_symbol") or "UNKNOWN"),
        runtime_timeframe=str(st.session_state.get("runtime_timeframe") or st.session_state.get("chart_timeframe") or "M5"),
        active_trade_plan=active_plan,
        open_positions=active_positions or [],
        strategy_markers=strategy_markers or [],
        active_candidates=active_candidates or [],
        height=700,
        window_size=window_size,
        component_key="nexusbot_primary_live_chart",
    )
