"""
ui/live_trade_center.py
NexusBot V3 — Institutional Live Execution Terminal

Layout:
  LEFT  (70%): Live price chart, position SL/TP overlays, depth-style ladder
  RIGHT (30%): Account metrics, active positions, thesis, safety, tournament digest
  BOTTOM (full-width): Continuously updating event stream + broker confirmation log

All user-initiated mutations are written to session_state and dispatched to
event_runtime — no blocking calls during the Streamlit render path.
"""
import streamlit as st
import pandas as pd
import datetime
from datetime import timezone

from ui.live_chart_panel import render_chart_controls, render_live_chart
from ui.tournament_panel import render_tournament_panel, render_explainability_panel
from ui.execution_panel import render_execution_signal_card, render_position_command_center
from ui.safety_panel import render_safety_panel, render_event_stream
from ui.thesis_panel import render_trade_thesis
from ui.ranked_strategy_context import render_ranked_strategy_context


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pill(label: str, value: str, color: str | None = None, bg: str | None = None) -> str:
    """Renders a compact metric pill."""
    theme = _theme_tokens()
    value_color = color or theme["text"]
    pill_bg = bg or theme["metric_bg"]
    return (
        f'<div style="background:{pill_bg};border:1px solid {theme["metric_border"]};border-radius:7px;'
        f'padding:7px 12px;min-width:92px;text-align:center;box-shadow:0 1px 2px rgba(15,23,42,0.04);">'
        f'<span style="font-size:0.6rem;color:{theme["faint"]};letter-spacing:1px;'
        f'text-transform:uppercase;display:block;">{label}</span>'
        f'<span style="font-size:0.82rem;color:{value_color};font-weight:800;'
        f'display:block;margin-top:1px;">{value}</span>'
        f'</div>'
    )


def _dispatch_action(action: str, payload: dict | None = None) -> None:
    """Write a pending action to session state for event_runtime to pick up."""
    st.session_state["_pending_action"] = {"action": action, "payload": payload or {}}


def _resolve_runtime_symbol() -> str:
    symbol = st.session_state.get("runtime_symbol", None)
    if not symbol:
        symbol = "UNKNOWN"
    symbol = str(symbol).strip().upper() or "UNKNOWN"
    return symbol


def _is_light_theme() -> bool:
    return st.session_state.get("ui_theme", "Dark") == "Light"


def _theme_tokens() -> dict:
    if _is_light_theme():
        return {
            "page": "#f4f7fb",
            "surface": "#ffffff",
            "surface_soft": "#f8fafc",
            "surface_strong": "#eef4fb",
            "border": "#d6e0ec",
            "border_strong": "#b9c7d8",
            "text": "#0f172a",
            "muted": "#475569",
            "faint": "#64748b",
            "shadow": "0 10px 28px rgba(15,23,42,0.08)",
            "metric_bg": "#ffffff",
            "metric_border": "#d6e0ec",
        }
    return {
        "page": "#050816",
        "surface": "#0f172a",
        "surface_soft": "#111827",
        "surface_strong": "#1e293b",
        "border": "#1e293b",
        "border_strong": "#334155",
        "text": "#e5e7eb",
        "muted": "#94a3b8",
        "faint": "#64748b",
        "shadow": "0 8px 24px rgba(0,0,0,0.35)",
        "metric_bg": "#111827",
        "metric_border": "#1e293b",
    }


def _fmt_price(value: float | int | None, symbol: str = "") -> str:
    try:
        price = float(value or 0.0)
    except (TypeError, ValueError):
        return "-"
    if price <= 0:
        return "-"
    symbol = str(symbol or "").upper()
    decimals = 2 if any(token in symbol for token in ("XAU", "XAG", "US", "NAS", "GER", "UK", "OIL")) else 5
    return f"{price:.{decimals}f}"


def _latest_chart_price(df: pd.DataFrame) -> float:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return 0.0
    cols = {str(col).lower(): col for col in df.columns}
    close_col = cols.get("close")
    if close_col is None:
        return 0.0
    try:
        return float(df[close_col].dropna().iloc[-1])
    except Exception:
        return 0.0


def _get_live_snapshot() -> dict:
    try:
        from deployment.engine_runtime import get_global_runtime
        snapshot = get_global_runtime().snapshot_store.get_snapshot()
        return snapshot.to_dict() if hasattr(snapshot, "to_dict") else {}
    except Exception:
        return {}


def _read_live_metrics(state, engine, latest_price: float = 0.0) -> dict:
    snapshot = _get_live_snapshot()
    live_metrics = snapshot.get("live_metrics", {}) if isinstance(snapshot, dict) else {}
    market_state = snapshot.get("market_state", {}) if isinstance(snapshot, dict) else {}

    balance = live_metrics.get("balance")
    equity = live_metrics.get("equity")
    currency = live_metrics.get("currency", "USD")
    if balance in (None, 0, 0.0):
        balance = st.session_state.get("mt5_balance") or getattr(engine, "balance", 0.0)
    if equity in (None, 0, 0.0):
        equity = st.session_state.get("mt5_equity") or balance

    price = latest_price or market_state.get("price") or getattr(state, "last_price", 0.0)
    spread = market_state.get("spread", getattr(state, "last_spread", 0.0))

    return {
        "balance": float(balance or 0.0),
        "equity": float(equity or 0.0),
        "currency": currency or "USD",
        "price": float(price or 0.0),
        "spread": float(spread or 0.0),
        "daily_pnl": float(live_metrics.get("daily_pnl", float(equity or 0.0) - float(balance or 0.0))),
    }


def _runtime_close_candle(price: float | int | None) -> dict:
    close_price = float(price or 0.0)
    ts = datetime.datetime.now(timezone.utc).isoformat()
    return {
        "timestamp": ts,
        "open": close_price,
        "high": close_price,
        "low": close_price,
        "close": close_price,
    }


def _get_chart_dataframe(default_df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    tf_key = str(timeframe or "H1").lower()
    session_key = f"{tf_key}_df"

    session_df = st.session_state.get(session_key)
    if isinstance(session_df, pd.DataFrame) and not session_df.empty:
        return session_df

    try:
        from deployment.engine_runtime import get_global_runtime
        bundle_df = get_global_runtime().orchestration.bundle.get(tf_key, pd.DataFrame())
        if isinstance(bundle_df, pd.DataFrame) and not bundle_df.empty:
            return bundle_df
    except Exception:
        pass

    if tf_key == "d1":
        source_df = st.session_state.get("h1_df")
        if not isinstance(source_df, pd.DataFrame) or source_df.empty:
            source_df = default_df
        return _resample_chart_dataframe(source_df, "1D")

    if isinstance(default_df, pd.DataFrame) and not default_df.empty:
        return default_df
    return pd.DataFrame()


def _merge_chart_data(base_df: pd.DataFrame, live_df: pd.DataFrame) -> pd.DataFrame:
    frames = [df for df in (base_df, live_df) if isinstance(df, pd.DataFrame) and not df.empty]
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    merged.columns = [str(col).lower() for col in merged.columns]
    if "timestamp" not in merged.columns:
        return merged
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True, errors="coerce")
    merged = merged.dropna(subset=["timestamp"])
    merged = merged.drop_duplicates(subset=["timestamp"], keep="last")
    merged = merged.sort_values("timestamp").reset_index(drop=True)
    return merged


def _fetch_recent_mt5_candles(symbol: str, timeframe: str, count: int = 500) -> pd.DataFrame:
    try:
        from deployment.engine_runtime import get_global_runtime
        from runtime.timeframe_mapper import TIMEFRAME_MAP
        import MetaTrader5 as mt5

        runtime = get_global_runtime()
        connector = runtime.mt5.connector
        if getattr(connector, "is_simulated", False) or mt5 is None:
            return pd.DataFrame()

        broker_symbol = connector.ensure_symbol(symbol)
        tf_const = TIMEFRAME_MAP.get(str(timeframe).upper())
        if tf_const is None:
            return pd.DataFrame()
        rates = mt5.copy_rates_from_pos(broker_symbol, tf_const, 0, int(count))
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
        raw = pd.DataFrame(rates)
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(raw["time"], unit="s", utc=True),
            "open": raw["open"].astype(float),
            "high": raw["high"].astype(float),
            "low": raw["low"].astype(float),
            "close": raw["close"].astype(float),
            "volume": raw["tick_volume"].astype(float),
            "spread": raw.get("spread", 0).astype(float) if "spread" in raw else 0.0,
            "symbol": symbol,
            "timeframe": timeframe,
        })
        return df
    except Exception:
        return pd.DataFrame()


def _strategy_name_for_markers(state) -> str:
    runtime_strategy = st.session_state.get("runtime_strategy")
    if runtime_strategy:
        return str(runtime_strategy)
    tournament = getattr(state, "latest_tournament", []) or st.session_state.get("tournament_results") or []
    if tournament:
        top = tournament[0] or {}
        if top.get("strategy"):
            return str(top["strategy"])
    return str(st.session_state.get("runtime_strategy") or "Mean Reversion")


def _sync_selected_trade_plan(state, selected_ranked_strategy: dict, symbol: str, timeframe: str) -> None:
    """Keep the visible ranked strategy and active trade plan in one runtime context."""
    selected_name = str(
        (selected_ranked_strategy or {}).get("strategy")
        or (selected_ranked_strategy or {}).get("name")
        or st.session_state.get("runtime_strategy")
        or ""
    ).strip()
    symbol = str(symbol or "UNKNOWN").strip().upper()
    timeframe = str(timeframe or "M5").strip().upper()
    selection_key = f"{symbol}|{timeframe}|{selected_name}"

    previous_key = getattr(state, "selected_trade_plan_key", None)
    previous_name = getattr(state, "selected_strategy_name", None)
    state.selected_strategy_name = selected_name or None
    state.selected_strategy_context = selected_ranked_strategy or {}
    state.selected_trade_plan_key = selection_key

    plan = getattr(state, "active_trade_plan", None) or {}
    plan_strategy = str(plan.get("strategy") or "").strip().lower()
    plan_symbol = str(plan.get("symbol") or "").strip().upper()
    plan_tf = str(plan.get("timeframe") or "").strip().upper()
    plan_mismatch = bool(plan) and (
        plan_symbol != symbol
        or plan_tf != timeframe
        or (selected_name and plan_strategy != selected_name.lower())
    )
    selection_changed = previous_key is not None and previous_key != selection_key
    first_selection = previous_key is None and bool(selected_name)

    if plan_mismatch or selection_changed:
        state.active_candidates = []
        state.last_plan_candle = None
        if hasattr(state, "set_active_trade_plan"):
            state.set_active_trade_plan(None)
        else:
            state.active_trade_plan = None
        st.session_state.pop("active_trade_plan", None)

    should_request_plan = first_selection or selection_changed or plan_mismatch or previous_name != selected_name
    if selected_name and should_request_plan:
        request_key = f"{selection_key}|{st.session_state.get('_live_chart_latest_ts', '')}"
        if st.session_state.get("_last_strategy_plan_request_key") != request_key:
            st.session_state["_last_strategy_plan_request_key"] = request_key
            try:
                from deployment.engine_runtime import get_global_runtime
                get_global_runtime().orchestration.trigger_evaluation("strategy")
            except Exception:
                pass


def _clear_plan_if_chart_context_changed(state, symbol: str, timeframe: str) -> None:
    plan = getattr(state, "active_trade_plan", None) or {}
    if not plan:
        st.session_state.pop("active_trade_plan", None)
        return
    plan_symbol = str(plan.get("symbol") or "").strip().upper()
    plan_tf = str(plan.get("timeframe") or "").strip().upper()
    symbol = str(symbol or "").strip().upper()
    timeframe = str(timeframe or "").strip().upper()
    if plan_symbol == symbol and plan_tf == timeframe:
        return
    state.active_candidates = []
    state.last_plan_candle = None
    if hasattr(state, "set_active_trade_plan"):
        state.set_active_trade_plan(None)
    else:
        state.active_trade_plan = None
    st.session_state.pop("active_trade_plan", None)


def _build_strategy_markers(df: pd.DataFrame, strategy_name: str, max_window: int = 200) -> list[dict]:
    """Build filtered strategy signal markers for the chart.

    Applies three layers of filtering to prevent chart overfill:
    1. Minimum signal strength threshold (>= 60)
    2. Cooldown: at least 5 candles between plotted signals
    3. Hard cap of 50 markers maximum
    """
    _MIN_STRENGTH = 60
    _COOLDOWN_CANDLES = 5
    _MAX_MARKERS = 50

    if df is None or df.empty or not strategy_name:
        return []
    try:
        from engine.strategy_registry import get_strategy_by_name
        strategy = get_strategy_by_name(strategy_name)
    except Exception:
        try:
            from engine.strategy_registry import get_strategy_by_name
            strategy = get_strategy_by_name("Mean Reversion")
            strategy_name = "Mean Reversion"
        except Exception:
            return []

    try:
        work = df.copy()
        work.columns = [str(col).lower() for col in work.columns]
        if "timestamp" not in work.columns:
            return []
        work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True, errors="coerce")
        work = work.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        work = strategy.prepare_indicators(work)
        if len(work) < 30:
            return []
        start = max(30, len(work) - int(max_window))
        markers = []
        last_marker_idx = -(_COOLDOWN_CANDLES + 1)  # allow first signal immediately
        for idx in range(start, len(work)):
            # Cooldown: skip if too close to last plotted signal
            if idx - last_marker_idx < _COOLDOWN_CANDLES:
                continue
            window = work.iloc[: idx + 1]
            signal = strategy.generate_signal(window) or {}
            side = str(signal.get("signal", "HOLD")).upper()
            if side not in ("BUY", "SELL", "BULLISH", "BEARISH", "UP", "DOWN"):
                continue
            strength = signal.get("strength", 0)
            # Strength gate: skip weak signals
            if int(strength or 0) < _MIN_STRENGTH:
                continue
            row = work.iloc[idx]
            price = float(row.get("close", 0.0) or 0.0)
            label = f"{strategy_name} {side} ({strength})"
            markers.append({
                "timestamp": row["timestamp"],
                "price": price,
                "signal": side,
                "strength": strength,
                "strategy": strategy_name,
                "label": label,
            })
            last_marker_idx = idx
            # Hard cap
            if len(markers) >= _MAX_MARKERS:
                break
        return markers
    except Exception:
        return []


def _maybe_update_chart_cache_state(df: pd.DataFrame, symbol: str, timeframe: str) -> bool:
    if df is None or df.empty or "timestamp" not in df.columns:
        return False
    latest_ts = pd.to_datetime(df["timestamp"].iloc[-1], utc=True, errors="coerce")
    key = f"{symbol}:{timeframe}"
    prev_key = st.session_state.get("_live_chart_data_key")
    prev_ts = st.session_state.get("_live_chart_latest_ts")
    changed = key != prev_key or str(latest_ts) != str(prev_ts)
    if changed:
        st.session_state["_live_chart_data_key"] = key
        st.session_state["_live_chart_latest_ts"] = str(latest_ts)
        st.session_state["_chart_refresh_nonce"] = int(st.session_state.get("_chart_refresh_nonce", 0)) + 1
    return changed


def _resample_chart_dataframe(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df is None or df.empty or "timestamp" not in df.columns:
        return pd.DataFrame()
    try:
        work = df.copy()
        work["timestamp"] = pd.to_datetime(work["timestamp"])
        resampled = (
            work.set_index("timestamp")
            .resample(rule)
            .agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            })
            .dropna()
            .reset_index()
        )
        return resampled
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Sub-panels
# ─────────────────────────────────────────────────────────────────────────────

def _render_account_strip(state, engine, live_metrics: dict | None = None) -> None:
    """Compact account metric strip rendered above the main columns."""
    theme = _theme_tokens()
    live_metrics = live_metrics or _read_live_metrics(state, engine)
    mt5_conn = st.session_state.get("mt5_connected", False)
    conn_col = "#22c55e" if mt5_conn else "#ef4444"
    conn_txt = "LIVE" if mt5_conn else "OFFLINE"

    bal = live_metrics["balance"]
    equity = live_metrics["equity"]
    currency = live_metrics.get("currency", "USD")
    pnl = equity - bal
    pnl_c = "#22c55e" if pnl >= 0 else "#ef4444"

    reg = state.current_regime.upper()
    reg_c = {"TRENDING": "#16a34a", "RANGING": "#2563eb", "VOLATILE": "#d97706",
             "LOW_VOLATILITY": "#64748b", "NEUTRAL": theme["muted"]}.get(reg, theme["muted"])

    eng_st = state.engine_state
    eng_c = {"SAFE": "#2563eb", "ARMED": "#d97706", "ACTIVE": "#16a34a",
             "EXECUTING": "#16a34a", "PAUSED": "#64748b",
             "LOCKED": "#dc2626", "EMERGENCY": "#dc2626"}.get(eng_st, theme["muted"])

    dd_pct = getattr(state, "daily_drawdown", 0.0)
    dd_c = "#16a34a" if dd_pct < 2.0 else ("#d97706" if dd_pct < 4.0 else "#dc2626")

    positions_count = len(getattr(state, "active_positions", []))
    symbol = st.session_state.get("runtime_symbol", "UNKNOWN")
    spread = live_metrics["spread"]
    price = live_metrics["price"]
    utc = datetime.datetime.now(timezone.utc).strftime("%H:%M:%S")

    pills = [
        _pill("MT5", conn_txt, conn_col),
        _pill("Symbol", symbol),
        _pill("Live Price", _fmt_price(price, symbol)),
        _pill("Regime", reg, reg_c),
        _pill("Engine", eng_st, eng_c),
        _pill("Spread", f"{spread:.1f}pt"),
        _pill("Balance", f"{currency} {bal:,.2f}", "#b7791f" if _is_light_theme() else "#eab308"),
        _pill("Equity", f"{currency} {equity:,.2f}", theme["text"]),
        _pill("Open P&L", f"{currency} {pnl:+.2f}", pnl_c),
        _pill("Drawdown", f"{dd_pct:.2f}%", dd_c),
        _pill("Positions", str(positions_count)),
        _pill("Trading Mode", getattr(state, "active_trading_mode", "Aggressive Scalper")),
        _pill("Strategy", st.session_state.get("runtime_strategy") or engine.profile.name),
        _pill("UTC", utc, theme["muted"], theme["surface_soft"]),
    ]

    st.markdown(
        f"""
        <div style="display:flex;flex-wrap:wrap;gap:6px;
                    background:{theme["surface"]};
                    border:1px solid {theme["border"]};border-radius:9px;
                    padding:10px 14px;margin-bottom:14px;
                    box-shadow:{theme["shadow"]};">
          {"".join(pills)}
        </div>
        """,
        unsafe_allow_html=True,
    )

def _render_position_manager(state, engine) -> None:
    """Rich position manager with live PnL badges and close buttons."""
    theme = _theme_tokens()
    positions = getattr(state, "active_positions", [])
    last_price = getattr(state, "last_price", 0.0)

    st.markdown(
        f"""
        <div style="font-size:0.75rem;font-weight:800;color:{theme["faint"]};
                    letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;">
          Active Positions
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not positions:
        st.markdown(
            f'<div style="background:{theme["surface"]};border:1px solid {theme["border"]};border-radius:7px;'
            f'padding:12px 14px;color:{theme["muted"]};font-size:0.78rem;text-align:center;">'
            'No open positions</div>',
            unsafe_allow_html=True,
        )
        return

    for pos in positions:
        ticket = pos.get("ticket", "?")
        direction = pos.get("direction", "?")
        entry = float(pos.get("entry_price", 0.0) or 0.0)
        sl = pos.get("sl", None)
        tp = pos.get("tp", None)
        size = pos.get("size", pos.get("lot", 0.01))
        strategy = pos.get("strategy", "Manual")
        sl_display = f"{float(sl):.5f}" if sl not in (None, 0, 0.0, "") else "-"
        tp_display = f"{float(tp):.5f}" if tp not in (None, 0, 0.0, "") else "-"
        raw_pnl = float(pos.get("live_pnl", pos.get("profit", 0.0)) or 0.0)
        if raw_pnl == 0.0 and last_price and entry:
            raw_pnl = (last_price - entry) * (1 if direction in ("BUY", "LONG") else -1) * float(size or 0.01) * 100_000
        pnl_c = "#16a34a" if raw_pnl >= 0 else "#dc2626"
        dir_c = "#16a34a" if direction in ("BUY", "LONG") else "#dc2626"
        dir_icon = "BUY" if direction in ("BUY", "LONG") else "SELL"

        col_info, col_btn = st.columns([3.5, 1])
        with col_info:
            st.markdown(
                f"""
                <div style="background:{theme["surface"]};border:1px solid {theme["border"]};
                            border-left:3px solid {dir_c};border-radius:7px;
                            padding:9px 12px;margin-bottom:6px;font-size:0.75rem;
                            box-shadow:0 1px 2px rgba(15,23,42,0.04);">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;gap:10px;">
                    <span style="color:{dir_c};font-weight:800;">{dir_icon} #{ticket} - {direction}</span>
                    <span style="color:{pnl_c};font-weight:900;font-size:0.85rem;">${raw_pnl:+.2f}</span>
                  </div>
                  <div style="display:flex;gap:14px;color:{theme["muted"]};flex-wrap:wrap;">
                    <span>Entry: <b style="color:{theme["text"]};">{entry:.5f}</b></span>
                    <span>SL: <b style="color:#dc2626;">{sl_display}</b></span>
                    <span>TP: <b style="color:#16a34a;">{tp_display}</b></span>
                    <span>Size: <b style="color:#7c3aed;">{size}</b></span>
                  </div>
                  <div style="color:{theme["faint"]};margin-top:2px;font-size:0.68rem;">Strategy: {strategy}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_btn:
            st.write("")
            if st.button("Close", key=f"close_pos_{ticket}", use_container_width=True):
                st.session_state["manual_close_intent"] = ticket
                st.rerun()

def _render_quick_execution_controls(state, engine) -> None:
    """Quick-fire execution control bar: Pause/Resume, mode switch, emergency flatten."""
    st.markdown(
        '<div style="font-size:0.75rem;font-weight:700;color:#64748b;'
        'letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;">'
        '⚙️ Execution Controls</div>',
        unsafe_allow_html=True
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        is_paused = state.engine_state == "PAUSED"
        lbl = "▶ Resume" if is_paused else "⏸ Pause"
        if st.button(lbl, key="ltc_pause_resume", use_container_width=True):
            st.session_state["manual_safety_action"] = "RESUME" if is_paused else "PAUSE"
            st.rerun()

    with c2:
        modes = ["ADVISORY", "SEMI_AUTO", "LIVE"]
        curr  = state.deployment_mode
        new_m = st.selectbox(
            "Mode", modes,
            index=modes.index(curr) if curr in modes else 0,
            key="ltc_mode_select",
            label_visibility="collapsed"
        )
        if new_m != curr:
            st.session_state["manual_mode_change"] = new_m
            st.rerun()

    with c3:
        is_locked = state.emergency_shutdown or state.engine_state in ("LOCKED", "EMERGENCY")
        if is_locked:
            if st.button("🔓 Reset", key="ltc_reset_lock", use_container_width=True):
                st.session_state["manual_safety_action"] = "RESET_SAFETY"
                st.rerun()
        else:
            if st.button("🚨 FLATTEN", key="ltc_flatten", type="primary", use_container_width=True):
                st.session_state["manual_safety_action"] = "EMERGENCY_FLATTEN"
                st.rerun()

    st.markdown("<hr style='margin:8px 0;'>", unsafe_allow_html=True)

    # Trading Mode selectbox
    from deployment.trading_modes import list_mode_names, get_mode
    mode_names = list_mode_names()
    active_mode_name = getattr(state, "active_trading_mode", "Aggressive Scalper")
    active_mode = get_mode(active_mode_name)

    selected_trading_mode = st.selectbox(
        "Trading Mode preset",
        mode_names,
        index=mode_names.index(active_mode_name) if active_mode_name in mode_names else 0,
        key="ltc_trading_mode_select"
    )

    if selected_trading_mode != active_mode_name:
        st.session_state["manual_trading_mode_change"] = selected_trading_mode
        st.rerun()

    # Ensure slider state is initialized
    if "ltc_min_confidence_slider" not in st.session_state:
        st.session_state["ltc_min_confidence_slider"] = float(active_mode.default_confidence)

    min_conf = st.slider(
        "Min Confidence Threshold",
        min_value=0.0,
        max_value=100.0,
        key="ltc_min_confidence_slider",
        step=1.0,
    )

    if hasattr(engine, "profile") and engine.profile is not None:
        engine.profile.minimum_confidence = float(min_conf)


# ─────────────────────────────────────────────────────────────────────────────
# Pending action processor (non-blocking dispatch to runtime)
# ─────────────────────────────────────────────────────────────────────────────

def _candidate_order_defaults(state, direction_override: str | None = None) -> dict:
    plan = getattr(state, "active_trade_plan", None) or st.session_state.get("active_trade_plan") or {}
    candidate = plan if plan else ((getattr(state, "active_candidates", []) or [{}])[0] or {})
    symbol = _resolve_runtime_symbol()
    price = float(getattr(state, "last_price", 0.0) or candidate.get("entry_price") or 0.0)
    direction = str(direction_override or candidate.get("direction") or "BUY").upper()
    if direction == "BULLISH":
        direction = "BUY"
    elif direction == "BEARISH":
        direction = "SELL"

    lot = float(candidate.get("lot") or candidate.get("qty") or candidate.get("size") or 0.01)
    sl = float(candidate.get("sl") or candidate.get("stop_loss") or 0.0)
    tp = float(candidate.get("tp") or candidate.get("take_profit") or 0.0)
    if candidate.get("entry_zone_low") and candidate.get("entry_zone_high") and not price:
        price = (float(candidate.get("entry_zone_low")) + float(candidate.get("entry_zone_high"))) / 2.0

    optimization_results = st.session_state.get("optimization_result") or st.session_state.get("optimization_results") or []
    if isinstance(optimization_results, list):
        best_opt = optimization_results[0] if optimization_results else {}
    elif isinstance(optimization_results, dict):
        best_opt = optimization_results
    else:
        best_opt = {}
    opt_params = best_opt.get("parameters", {}) if isinstance(best_opt, dict) else {}
    if isinstance(best_opt, dict):
        opt_params = {**best_opt, **opt_params}

    atr = float(candidate.get("atr") or 0.0)
    if not atr:
        tf = str(st.session_state.get("runtime_timeframe") or "M5").lower()
        df = st.session_state.get(f"{tf}_df")
        if not isinstance(df, pd.DataFrame) or df.empty:
            df = st.session_state.get("uploaded_df")
        if isinstance(df, pd.DataFrame) and not df.empty:
            cols = {str(col).lower(): col for col in df.columns}
            atr_col = cols.get("atr")
            if atr_col:
                try:
                    atr = float(df[atr_col].dropna().iloc[-1])
                except Exception:
                    atr = 0.0
            if not atr and {"high", "low"}.issubset(cols):
                try:
                    atr = float((df[cols["high"]] - df[cols["low"]]).tail(20).mean())
                except Exception:
                    atr = 0.0

    sl_mult = float(opt_params.get("sl_atr_multiplier") or opt_params.get("sl_atr") or 1.5)
    tp_mult = float(opt_params.get("tp_atr_multiplier") or opt_params.get("tp_atr") or 2.5)

    if price and (not sl or not tp):
        if atr:
            sl_dist = atr * sl_mult
            tp_dist = atr * tp_mult
        else:
            sl_dist = price * 0.005
            tp_dist = price * 0.01
        if direction == "SELL":
            sl = sl or price + sl_dist
            tp = tp or max(0.0, price - tp_dist)
        else:
            sl = sl or max(0.0, price - sl_dist)
            tp = tp or price + tp_dist

    return {
        "symbol": symbol,
        "entry_price": price,
        "direction": direction if direction in ("BUY", "SELL") else "BUY",
        "lot": max(0.01, lot),
        "sl": sl,
        "tp": tp,
        "strategy": candidate.get("strategy") or st.session_state.get("runtime_strategy") or "Manual",
        "source": "active plan" if plan else ("candidate" if candidate else ("optimizer" if best_opt else "manual")),
        "atr": atr,
        "sl_mult": sl_mult,
        "tp_mult": tp_mult,
    }


def _render_manual_order_ticket(state) -> None:
    theme = _theme_tokens()
    initial_defaults = _candidate_order_defaults(state)
    direction = st.selectbox(
        "Order Direction",
        ["BUY", "SELL"],
        index=0 if initial_defaults["direction"] == "BUY" else 1,
        key="ltc_order_direction_pre",
    )
    defaults = _candidate_order_defaults(state, direction_override=direction)
    defaults_key = (
        defaults["symbol"],
        direction,
        round(float(defaults.get("entry_price") or 0.0), 5),
        round(float(defaults.get("atr") or 0.0), 5),
        defaults.get("source"),
    )
    if st.session_state.get("_ltc_order_defaults_key") != defaults_key:
        st.session_state["_ltc_order_defaults_key"] = defaults_key
        st.session_state["ltc_order_lot"] = float(defaults["lot"])
        st.session_state["ltc_order_sl"] = float(defaults["sl"])
        st.session_state["ltc_order_tp"] = float(defaults["tp"])
    st.markdown(
        f"""
        <div style="background:{theme["surface"]};border:1px solid {theme["border"]};
                    border-radius:9px;padding:12px 14px;margin-bottom:10px;
                    box-shadow:{theme["shadow"]};">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:6px;">
            <div>
              <div style="font-size:0.72rem;font-weight:900;color:{theme["faint"]};
                          letter-spacing:1px;text-transform:uppercase;">Manual Broker Order</div>
              <div style="font-size:1.0rem;font-weight:900;color:{theme["text"]};">
                {defaults["symbol"]} {defaults["direction"]}
              </div>
            </div>
            <div style="text-align:right;font-size:0.72rem;color:{theme["muted"]};">
              <div>Reference <b style="color:{theme["text"]};">{_fmt_price(defaults["entry_price"], defaults["symbol"])}</b></div>
              <div>SL/TP: <b style="color:{theme["text"]};">{defaults["source"]}</b></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not defaults["entry_price"]:
        st.warning("No live/reference price available yet. Load data or wait for MT5 price sync before sending an order.")
    if defaults.get("source") != "active plan":
        st.info("No executable strategy trade plan is active. SL/TP below are manual protective defaults, not a tournament-approved auto-trade plan.")
    st.caption(
        f"ATR basis: {_fmt_price(defaults['atr'], defaults['symbol'])} | "
        f"SL ATR x{defaults['sl_mult']:.2f} | TP ATR x{defaults['tp_mult']:.2f}"
    )
    if st.button("Rebuild SL/TP From Current Price", key="ltc_rebuild_dynamic_sltp", use_container_width=True):
        for key in ("ltc_order_sl", "ltc_order_tp", "ltc_order_lot"):
            st.session_state.pop(key, None)
        st.rerun()
    with st.form("ltc_broker_order_ticket", clear_on_submit=False):
        lot = st.number_input(
            "Lot",
            min_value=0.01,
            max_value=100.0,
            value=float(defaults["lot"]),
            step=0.01,
            key="ltc_order_lot",
        )
        c3, c4 = st.columns(2)
        with c3:
            sl = st.number_input("SL", value=float(defaults["sl"]), step=0.01, format="%.5f", key="ltc_order_sl")
        with c4:
            tp = st.number_input("TP", value=float(defaults["tp"]), step=0.01, format="%.5f", key="ltc_order_tp")

        submitted = st.form_submit_button("Send Broker Order", type="primary", use_container_width=True)
        if submitted:
            if not defaults["entry_price"]:
                st.error("Order not queued: no live/reference price is available for this symbol.")
                return
            st.session_state["manual_order_ticket"] = {
                "symbol": defaults["symbol"],
                "direction": direction,
                "lot": float(lot),
                "sl": float(sl),
                "tp": float(tp),
                "comment": f"Manual {defaults['strategy']}",
            }
            st.rerun()


def _process_pending_actions(state, engine) -> None:
    """
    Process any pending actions written to session_state by UI widgets.
    This keeps the render path clean — all mutations happen here at the top.
    """
    from deployment.engine_runtime import get_global_runtime
    runtime = get_global_runtime()

    # Manual broker order
    if "manual_order_ticket" in st.session_state:
        order = st.session_state.pop("manual_order_ticket")
        runtime.event.dispatch("PLACE_ORDER", order)
        runtime.state_manager.event_bus.emit(
            f"Manual broker order queued: {order.get('direction')} {order.get('lot')} lots "
            f"SL={order.get('sl')} TP={order.get('tp')}",
            "INFO",
        )
        st.toast("Broker order queued with SL/TP.")

    # Manual position close
    if "manual_close_intent" in st.session_state:
        ticket = st.session_state.pop("manual_close_intent")
        runtime.event.dispatch("CLOSE_POSITION", {"ticket": ticket})
        runtime.state_manager.event_bus.emit(
            f"Manual close queued for position #{ticket}.", "INFO"
        )
        st.toast(f"Close queued for position #{ticket}.")
    # Mode switch
    if "manual_mode_change" in st.session_state:
        new_mode = st.session_state.pop("manual_mode_change")
        runtime.state_manager.deployment_mode = new_mode
        runtime.state_manager.event_bus.emit(
            f"Execution mode changed to: {new_mode}", "INFO"
        )

    # Trading mode switch
    if "manual_trading_mode_change" in st.session_state:
        new_trading_mode = st.session_state.pop("manual_trading_mode_change")
        runtime.event.dispatch("SET_TRADING_MODE", {"mode": new_trading_mode})
        
        # Reset the confidence slider key to the mode's default
        from deployment.trading_modes import get_mode
        mode = get_mode(new_trading_mode)
        st.session_state["ltc_min_confidence_slider"] = float(mode.default_confidence)

    # Safety actions
    if "manual_safety_action" in st.session_state:
        action = st.session_state.pop("manual_safety_action")
        if action == "PAUSE":
            runtime.pause()
        elif action == "RESUME":
            runtime.resume()
        elif action == "EMERGENCY_FLATTEN":
            runtime.event.dispatch("EMERGENCY_FLATTEN", {})
            runtime.state_manager.event_bus.emit(
                "Emergency flatten queued by operator.", "CRITICAL"
            )
        elif action == "RESET_SAFETY":
            runtime.state_manager.reset_daily_stats()


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def _render_execution_verification_panel(state) -> None:
    verification = getattr(state, "execution_verification", {}) or {}
    st.markdown(
        '<div style="font-size:0.75rem;font-weight:700;color:#64748b;'
        'letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;">'
        'Execution Verification</div>',
        unsafe_allow_html=True,
    )

    checklist = [
        ("Intent Created", "intent_created"),
        ("Strategy Candidate Built", "strategy_candidate_built"),
        ("Risk Gates Passed", "risk_gates_passed"),
        ("Broker Order Sent", "broker_order_sent"),
        ("Broker Order Confirmed", "broker_order_confirmed"),
        ("Broker Ticket Returned", "broker_ticket_returned"),
        ("Broker Position Confirmed", "broker_position_confirmed"),
        ("Runtime Position Synced", "runtime_position_synced"),
    ]
    for label, key in checklist:
        passed = bool(verification.get(key))
        color = "#22c55e" if passed else "#ef4444"
        icon = "PASS" if passed else "MISS"
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;border-bottom:1px solid #1e293b;"
            f"padding:4px 0;font-size:0.76rem;'><span>{label}</span>"
            f"<b style='color:{color};'>{icon}</b></div>",
            unsafe_allow_html=True,
        )

    if verification.get("auto_live_local_only") or (
        getattr(state, "deployment_mode", "") == "LIVE"
        and verification.get("intent_created")
        and not verification.get("broker_order_sent")
    ):
        st.error("AUTO LIVE currently created local runtime position only. Broker order not verified.")
    if verification.get("broker_order_failed"):
        st.error(verification.get("last_warning") or "LIVE broker order failed. Runtime position was not added.")

    field_map = {
        "last_intent_id": verification.get("last_intent_id"),
        "last_order_request": verification.get("last_order_request"),
        "last_order_result": verification.get("last_order_result"),
        "last_broker_ticket": verification.get("last_broker_ticket"),
        "last_confirmed_position": verification.get("last_confirmed_position"),
        "broker_order_confirmed": verification.get("broker_order_confirmed"),
        "broker_order_failed": verification.get("broker_order_failed"),
    }
    with st.expander("Execution Verification Details", expanded=False):
        st.json(field_map)
        events = verification.get("events") or []
        if events:
            st.markdown("**Verification Events**")
            st.dataframe(pd.DataFrame(events), use_container_width=True)


def render_live_trade_center(state, engine) -> None:
    """
    Institutional Live Execution Terminal.

    Architecture:
      1. Process pending actions (no UI mutations inside render path)
      2. Account metric strip (full-width)
      3. Main 70/30 columns:
         LEFT : Live chart with entries/SL/TP overlays
         RIGHT: Execution signal, position manager, quick controls,
                thesis panel, safety panel, tournament digest
      4. Bottom: Full-width event stream
    """
    # ── 1. Action Dispatch (non-blocking) ──────────────────────────────────
    _process_pending_actions(state, engine)

    symbol = _resolve_runtime_symbol()
    chart_state = render_chart_controls(default_symbol=symbol)
    symbol = chart_state["symbol"]
    st.session_state["runtime_symbol"] = symbol
    st.session_state["runtime_timeframe"] = chart_state["timeframe"]
    _clear_plan_if_chart_context_changed(state, symbol, chart_state["timeframe"])
    if getattr(state, "active_trade_plan", None):
        st.session_state["active_trade_plan"] = state.active_trade_plan
    else:
        st.session_state.pop("active_trade_plan", None)
    if hasattr(state, "watchlist_timeframe"):
        state.watchlist_timeframe = chart_state["timeframe"]
    try:
        from deployment.engine_runtime import get_global_runtime
        runtime = get_global_runtime()
        runtime.set_symbol(symbol)
        if hasattr(runtime, "set_timeframe"):
            runtime.set_timeframe(chart_state["timeframe"])
    except Exception:
        pass

    # ── 2. Account Strip ───────────────────────────────────────────────────
    h1_df = st.session_state.get("h1_df")
    orch_ctx = st.session_state.get("orchestration_context")
    if h1_df is None or h1_df.empty:
        try:
            from deployment.engine_runtime import get_global_runtime
            h1_df = get_global_runtime().orchestration.bundle.get("h1", pd.DataFrame())
        except Exception:
            h1_df = pd.DataFrame()
    chart_df = _get_chart_dataframe(h1_df, chart_state["timeframe"])
    live_df = _fetch_recent_mt5_candles(symbol, chart_state["timeframe"], count=750)
    chart_df = _merge_chart_data(chart_df, live_df)
    latest_price = _latest_chart_price(chart_df)
    if latest_price:
        state.last_price = latest_price
        st.session_state["last_live_price"] = latest_price
    live_metrics = _read_live_metrics(state, engine, latest_price=latest_price)
    st.session_state["mt5_balance"] = live_metrics["balance"]
    st.session_state["mt5_equity"] = live_metrics["equity"]
    data_changed = _maybe_update_chart_cache_state(chart_df, symbol, chart_state["timeframe"])
    marker_strategy = _strategy_name_for_markers(state)
    strategy_markers = _build_strategy_markers(chart_df, marker_strategy, max_window=200)
    _render_account_strip(state, engine, live_metrics=live_metrics)
    selected_ranked_strategy = render_ranked_strategy_context(state, key_prefix="live", compact=True)
    if selected_ranked_strategy:
        _sync_selected_trade_plan(state, selected_ranked_strategy, symbol, chart_state["timeframe"])
        marker_strategy = str(selected_ranked_strategy.get("strategy") or marker_strategy)
        strategy_markers = _build_strategy_markers(chart_df, marker_strategy, max_window=200)

    # Focus Mode: collapse auxiliary panels when ARMED or EXECUTING
    focus_mode = state.engine_state in ("ARMED", "EXECUTING", "ACTIVE")
    if focus_mode:
        st.markdown(
            '<div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.3);'
            'border-radius:6px;padding:6px 14px;margin-bottom:10px;font-size:0.75rem;color:#f59e0b;">'
            '⚡ <b>FOCUS MODE ACTIVE</b> — Engine is ARMED/EXECUTING. Auxiliary panels collapsed.'
            '</div>',
            unsafe_allow_html=True
        )

    # ── 3. Main 70/30 Columns ─────────────────────────────────────────────
    chart_col, control_col = st.columns([2.25, 1.0])

    with chart_col:
        st.markdown(
            '<div style="font-size:0.75rem;font-weight:700;color:#64748b;'
            'letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;">'
            f'📈 {symbol} — Live Price Chart</div>',
            unsafe_allow_html=True
        )
        render_live_chart(
            df=chart_df,
            active_positions=state.active_positions,
            active_candidates=state.active_candidates,
            strategy_markers=strategy_markers,
            current_regime=state.current_regime,
            window_size=320,
            refresh_allowed=chart_state["should_refresh"] or data_changed,
        )
        if strategy_markers:
            st.caption(f"Showing {len(strategy_markers)} historical {marker_strategy} signal marker(s) in recent data.")

        # Execution signal overlay below chart
        if state.active_candidates:
            render_execution_signal_card(active_candidates=state.active_candidates)

    with control_col:
        # 3a. Manual broker order ticket
        _render_manual_order_ticket(state)
        st.write("")

        # 3b. Active Positions
        _render_position_manager(state, engine)
        st.write("")

        # 3c. Quick Execution Controls
        _render_quick_execution_controls(state, engine)
        st.write("")

        with st.expander("Execution Verification", expanded=True):
            _render_execution_verification_panel(state)
        st.write("")

        # 3c. Trade Thesis Panel
        with st.expander("🎯 Trade Thesis & AI Briefing", expanded=not focus_mode):
            render_trade_thesis(state, engine, orch_ctx)

        # 3d. Safety Circuit Breaker
        with st.expander("🛡️ Safety Circuit Breaker", expanded=focus_mode):
            vol_state = state.last_volatility
            render_safety_panel(
                engine_state=state.engine_state,
                spread=state.last_spread,
                max_spread=engine.profile.max_spread,
                volatility=vol_state,
                drawdown=state.daily_drawdown,
                max_drawdown=state.max_daily_drawdown_pct,
                consecutive_losses=state.consecutive_losses,
                max_losses=state.max_consecutive_losses,
                deployment_mode=state.deployment_mode
            )

        # 3e. Tournament Digest (collapsed in focus mode)
        if not focus_mode:
            with st.expander("🏆 Strategy Tournament Digest", expanded=False):
                render_tournament_panel(
                    latest_tournament=state.latest_tournament,
                    rejected_strategies=getattr(
                        orch_ctx, "market_explainer", {}
                    ).get("strategy_rejections", {}) if orch_ctx else {},
                    state=state
                )
                # Explainability breakdown
                winner_data = state.latest_tournament[0] if state.latest_tournament else {}
                render_explainability_panel(winner_strategy=winner_data)

    # ── 4. Bottom: Full-Width Event Stream ────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div style="font-size:0.75rem;font-weight:700;color:#64748b;'
        'letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;">'
        '📡 Live Event Feed & Broker Confirmation Log</div>',
        unsafe_allow_html=True
    )
    render_event_stream(events=state.event_bus.latest())
