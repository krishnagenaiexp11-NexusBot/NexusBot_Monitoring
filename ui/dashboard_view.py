"""
ui/dashboard_view.py
Multi-symbol strategy dashboard and trading-engine watchlist controls.
"""
import streamlit as st
import pandas as pd

from engine.strategy_registry import list_registered_strategies
from ui.ranked_strategy_context import render_ranked_strategy_context


DASHBOARD_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
    "US500", "NAS100", "US30", "GER40", "UK100",
    "XAUUSD", "XAGUSD", "USOIL", "UKOIL",
    "BTCUSD", "ETHUSD",
]
DASHBOARD_TIMEFRAMES = ["M1", "M5", "M15", "H1", "H4", "D1"]


def _fmt_list(values) -> str:
    if not values:
        return "N/A"
    return ", ".join(str(item) for item in values)


def _registered_strategy_rows() -> list[dict]:
    rows = []
    for strategy in list_registered_strategies():
        try:
            name = strategy.get_strategy_name()
        except Exception:
            name = strategy.__class__.__name__
        try:
            regimes = strategy.get_supported_regimes()
        except Exception:
            regimes = []
        try:
            states = strategy.get_supported_market_states()
        except Exception:
            states = []
        params = getattr(strategy, "params", None) or getattr(strategy, "default_params", {}) or {}
        rows.append({
            "strategy": name,
            "supported_regimes": _fmt_list(regimes),
            "supported_states": _fmt_list(states),
            "params": ", ".join(f"{k}={v}" for k, v in list(params.items())[:6]),
        })
    return rows


def _symbol_rows(symbols: list[str], timeframe: str, state) -> list[dict]:
    watchlist = getattr(state, "trading_watchlist", []) or []
    watched = {item.get("symbol"): item for item in watchlist}
    analysis_results = st.session_state.get("analysis_symbol_results") or {}
    tournament = getattr(state, "latest_tournament", []) or []
    top = tournament[0] if tournament else {}
    candidate = (getattr(state, "active_candidates", []) or [{}])[0] or {}

    rows = []
    for symbol in symbols:
        watch_item = watched.get(symbol)
        symbol_result = analysis_results.get(symbol, {})
        row_top_strategy = symbol_result.get("top_strategy") or top.get("strategy", "N/A")
        row_fit = symbol_result.get("fit", top.get("market_fit_score", top.get("fit_score", "N/A")))
        rows.append({
            "symbol": symbol,
            "timeframe": symbol_result.get("timeframe", timeframe),
            "active": "YES" if symbol == st.session_state.get("runtime_symbol") else "NO",
            "watchlist": "YES" if watch_item else "NO",
            "status": symbol_result.get("status", watch_item.get("status", "SCAN") if watch_item else "SCAN"),
            "regime": symbol_result.get("regime", "N/A"),
            "top_strategy": row_top_strategy,
            "fit": row_fit,
            "readiness": symbol_result.get("readiness", "N/A"),
            "candidate": candidate.get("strategy", "N/A") if symbol == st.session_state.get("runtime_symbol") else "N/A",
            "signal": candidate.get("direction", "N/A") if symbol == st.session_state.get("runtime_symbol") else "N/A",
        })
    return rows


def _attach_strategy_to_watchlist(state, symbol: str, timeframe: str, selected_ranked: dict) -> None:
    strategy_name = (
        selected_ranked.get("strategy")
        or selected_ranked.get("strategy_name")
        or st.session_state.get("runtime_strategy")
        or "N/A"
    )
    rank = selected_ranked.get("rank", st.session_state.get("runtime_strategy_rank", "N/A"))
    state.trading_watchlist = getattr(state, "trading_watchlist", [])
    for item in state.trading_watchlist:
        if item.get("symbol") == symbol:
            item["timeframe"] = timeframe
            item["strategy"] = strategy_name
            item["rank"] = rank
            item["status"] = item.get("status", "WATCHING")
            return
    state.trading_watchlist.append({
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "WATCHING",
        "strategy": strategy_name,
        "rank": rank,
    })


def render_dashboard_view(state, engine) -> None:
    st.markdown("### Dashboard View")
    st.caption("Dashboard reflects the market basket selected and analyzed in Analysis Lab.")

    runtime_symbol = st.session_state.get("runtime_symbol", "XAUUSD")
    default_symbols = st.session_state.get("runtime_symbols") or st.session_state.get("analysis_selected_symbols") or st.session_state.get("dashboard_symbols") or [runtime_symbol]
    default_symbols = [str(sym).strip().upper() for sym in default_symbols if str(sym).strip()] or ["XAUUSD"]
    if runtime_symbol not in default_symbols:
        default_symbols = [runtime_symbol] + default_symbols
    current_timeframe = str(st.session_state.get("runtime_timeframe") or st.session_state.get("dashboard_timeframe") or "M5").upper()
    if current_timeframe not in DASHBOARD_TIMEFRAMES:
        current_timeframe = "M5"
    if st.session_state.get("dashboard_timeframe") != current_timeframe:
        st.session_state["dashboard_timeframe"] = current_timeframe

    selected_symbols = default_symbols[:5]
    c1, c2 = st.columns([2.2, 0.8])
    with c1:
        st.markdown("#### Analysis Basket")
        st.write(", ".join(selected_symbols))
        st.caption("Change this basket in Settings.")
    with c2:
        timeframe = st.selectbox(
            "Timeframe",
            DASHBOARD_TIMEFRAMES,
            index=DASHBOARD_TIMEFRAMES.index(current_timeframe),
            key="dashboard_timeframe",
        )

    if len(selected_symbols) < 3:
        st.info("Select at least 3 symbols for the dashboard basket.")
    if len(selected_symbols) > 5:
        st.warning("Dashboard supports up to 5 symbols at once. Showing the first 5.")
        selected_symbols = selected_symbols[:5]

    st.session_state["runtime_timeframe"] = timeframe
    st.session_state["chart_timeframe"] = timeframe
    if hasattr(state, "watchlist_timeframe"):
        state.watchlist_timeframe = timeframe
    try:
        from deployment.engine_runtime import get_global_runtime
        runtime = get_global_runtime()
        if hasattr(runtime, "set_timeframe"):
            runtime.set_timeframe(timeframe)
    except Exception:
        pass

    selected_ranked = render_ranked_strategy_context(state, key_prefix="dashboard", compact=False)
    st.divider()

    st.markdown("#### Selected Symbols")
    symbol_rows = _symbol_rows(selected_symbols, timeframe, state)
    st.dataframe(pd.DataFrame(symbol_rows), use_container_width=True, hide_index=True)

    add_cols = st.columns(max(1, len(selected_symbols)))
    for idx, symbol in enumerate(selected_symbols):
        with add_cols[idx]:
            if st.button(f"Use {symbol}", key=f"dash_use_{symbol}", use_container_width=True):
                st.session_state["runtime_symbol"] = symbol
                st.session_state["chart_symbol"] = symbol
                st.session_state["runtime_timeframe"] = timeframe
                st.session_state["chart_timeframe"] = timeframe
                st.toast(f"{symbol} {timeframe} is now the active workflow context.")
                st.rerun()
            if st.button(f"Watch {symbol}", key=f"dash_watch_{symbol}", use_container_width=True):
                if hasattr(state, "add_to_watchlist"):
                    state.add_to_watchlist(symbol, timeframe)
                else:
                    state.trading_watchlist = getattr(state, "trading_watchlist", [])
                _attach_strategy_to_watchlist(state, symbol, timeframe, selected_ranked)
                st.toast(f"{symbol} {timeframe} added to watchlist.")
                st.rerun()

    watchlist = getattr(state, "trading_watchlist", []) or []
    st.markdown("#### Trading Engine Watchlist")
    if watchlist:
        st.dataframe(pd.DataFrame(watchlist), use_container_width=True, hide_index=True)
        remove_symbol = st.selectbox(
            "Remove Symbol",
            options=[item.get("symbol") for item in watchlist],
            key="dashboard_remove_symbol",
        )
        if st.button("Remove From Watchlist", key="dashboard_remove_btn"):
            if hasattr(state, "remove_from_watchlist"):
                state.remove_from_watchlist(remove_symbol)
            st.rerun()
    else:
        st.info("No symbols are currently in the trading-engine watchlist.")

    st.markdown("#### Registered Strategies")
    strategy_rows = _registered_strategy_rows()
    st.dataframe(pd.DataFrame(strategy_rows), use_container_width=True, hide_index=True)
