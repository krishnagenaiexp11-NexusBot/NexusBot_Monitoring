"""
ui/settings_page.py
Clean runtime settings workspace for AI, MT5, execution mode, safety, and commands.
Market selection belongs to Analysis Lab, not here.
"""
import streamlit as st


SYMBOLS_BY_ASSET_CLASS = {
    "Forex": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD"],
    "Indices": ["US500", "NAS100", "US30", "GER40", "UK100"],
    "Commodities": ["XAUUSD", "XAGUSD", "USOIL", "UKOIL"],
    "Crypto": ["BTCUSD", "ETHUSD"],
    "Stocks": ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL"],
    "Custom": [],
}
DEFAULT_SYMBOL_UNIVERSE = [
    symbol
    for symbols in SYMBOLS_BY_ASSET_CLASS.values()
    for symbol in symbols
]


AI_MODEL_OPTIONS = {
    "Google Gemini": [
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ],
    "OpenRouter": [
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "anthropic/claude-3.5-sonnet:beta",
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "google/gemini-2.0-flash-001",
        "google/gemini-2.5-flash",
        "meta-llama/llama-3.1-70b-instruct",
        "mistralai/mistral-large",
        "Custom",
    ],
    "OpenAI": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"],
    "Claude": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
    "Ollama": ["llama3", "llama3.1", "mistral", "qwen2.5"],
    "LM Studio": ["local-model"],
}


def _provider_state_key(prefix: str, provider: str) -> str:
    safe_provider = "".join(ch.lower() if ch.isalnum() else "_" for ch in provider).strip("_")
    return f"{prefix}_{safe_provider}"


def _default_model(provider: str) -> str:
    options = AI_MODEL_OPTIONS.get(provider, [])
    return options[0] if options else ""


def _normalize_symbol(value: str | None) -> str:
    return str(value or "").strip().upper()


def _parse_manual_symbols(value: str) -> list[str]:
    symbols = []
    for raw in str(value or "").replace("\n", ",").split(","):
        sym = _normalize_symbol(raw)
        if sym and sym not in symbols:
            symbols.append(sym)
    return symbols


def _runtime_symbol_basket() -> list[str]:
    active = _normalize_symbol(st.session_state.get("runtime_symbol")) or "XAUUSD"
    basket = st.session_state.get("runtime_symbols") or [active]
    normalized = [_normalize_symbol(sym) for sym in basket if _normalize_symbol(sym)]
    if active not in normalized:
        normalized.insert(0, active)
    return list(dict.fromkeys(normalized))[:5] or ["XAUUSD"]


def _render_market_basket_settings(runtime) -> None:
    with st.container(border=True):
        st.markdown("#### Market Basket")
        st.caption("This saved basket drives Analysis, Dashboard, Live Trading, and Optimizer.")

        current_basket = _runtime_symbol_basket()
        asset_class = st.selectbox(
            "Add From Asset Class",
            list(SYMBOLS_BY_ASSET_CLASS.keys()),
            index=0,
            key="settings_symbol_asset_class",
        )
        class_options = SYMBOLS_BY_ASSET_CLASS.get(asset_class, [])

        c1, c2 = st.columns([1.5, 1.0])
        with c1:
            universe = list(dict.fromkeys(DEFAULT_SYMBOL_UNIVERSE + current_basket))
            widget_seq = int(st.session_state.get("settings_symbols_widget_seq", 0))
            saved_symbols = st.multiselect(
                "Saved Symbols",
                options=universe,
                default=[sym for sym in current_basket if sym in universe],
                key=f"settings_runtime_symbols_{widget_seq}",
            )
        with c2:
            add_symbol = ""
            if class_options:
                add_symbol = st.selectbox(
                    f"Quick Add {asset_class}",
                    options=class_options,
                    index=0,
                    key=f"settings_add_symbol_{asset_class}",
                )
            manual_symbols = st.text_input(
                "Manual Add",
                placeholder="XAUUSD, EURUSD, US500",
                key="settings_manual_symbols",
            )
            add_clicked = st.button("Add To Basket", key="settings_add_to_basket", use_container_width=True)

        merged = list(dict.fromkeys(
            [_normalize_symbol(sym) for sym in saved_symbols if _normalize_symbol(sym)]
        ))[:5]
        if add_clicked:
            merged = list(dict.fromkeys(
                merged + [_normalize_symbol(add_symbol)] + _parse_manual_symbols(manual_symbols)
            ))[:5]
        if not merged:
            merged = ["XAUUSD"]

        active = st.radio(
            "Active Symbol",
            merged,
            index=merged.index(st.session_state.get("runtime_symbol")) if st.session_state.get("runtime_symbol") in merged else 0,
            horizontal=True,
            key="settings_active_symbol",
        )

        st.session_state["runtime_symbols"] = merged
        st.session_state["analysis_selected_symbols"] = merged
        st.session_state["dashboard_symbols"] = merged
        st.session_state["runtime_symbol"] = active
        st.session_state["chart_symbol"] = active
        runtime.set_symbol(active)

        st.caption(f"Saved basket: {', '.join(merged)}")
        if add_clicked:
            st.session_state["settings_symbols_widget_seq"] = int(st.session_state.get("settings_symbols_widget_seq", 0)) + 1
            st.rerun()


def _render_status_cards(state, runtime) -> None:
    mt5_connected = st.session_state.get("mt5_connected", False)
    status_cols = st.columns(4)
    status_cols[0].metric("MT5", "LIVE" if mt5_connected else "OFFLINE")
    status_cols[1].metric("Engine", getattr(state, "engine_state", "UNKNOWN"))
    status_cols[2].metric("Mode", getattr(state, "deployment_mode", "ADVISORY"))
    status_cols[3].metric("Active Symbol", st.session_state.get("runtime_symbol", getattr(runtime, "symbol", "UNKNOWN")))


def _render_appearance_settings() -> None:
    with st.container(border=True):
        st.markdown("#### Appearance")
        current_theme = st.session_state.get("ui_theme", "Dark")
        theme = st.radio(
            "Theme",
            ["Light", "Dark"],
            index=0 if current_theme == "Light" else 1,
            horizontal=True,
            key="settings_ui_theme",
        )
        if theme != current_theme:
            st.session_state["ui_theme"] = theme
            st.rerun()
        st.caption("Light mode reduces visual load for analysis-heavy screens. Dark mode keeps the terminal look.")


def _render_execution_settings(state) -> None:
    with st.container(border=True):
        st.markdown("#### Execution")
        modes = ["ADVISORY", "SEMI_AUTO", "LIVE"]
        curr_mode = getattr(state, "deployment_mode", "ADVISORY")
        selected_mode = st.selectbox(
            "Deployment Mode",
            options=modes,
            index=modes.index(curr_mode) if curr_mode in modes else 0,
            key="settings_execution_mode",
        )
        if selected_mode != curr_mode:
            state.deployment_mode = selected_mode
            st.rerun()


def _render_ai_settings() -> None:
    with st.container(border=True):
        st.markdown("#### AI Explanation Provider")
        providers = ["Google Gemini", "OpenAI", "Claude", "OpenRouter", "Ollama", "LM Studio", "Deterministic Template"]
        current_provider = st.session_state.get("ai_provider", "Deterministic Template")
        provider = st.selectbox(
            "Provider",
            providers,
            index=providers.index(current_provider) if current_provider in providers else len(providers) - 1,
            key="settings_ai_provider",
        )
        st.session_state["ai_provider"] = provider

        model = ""
        model_options = AI_MODEL_OPTIONS.get(provider, [])
        if provider == "OpenRouter":
            current_model = st.session_state.get("openrouter_model") or _default_model("OpenRouter")
            presets = [opt for opt in model_options if opt != "Custom"] + ["Use typed model"]
            preset = st.selectbox(
                "OpenRouter Preset",
                presets,
                index=presets.index(current_model) if current_model in presets else presets.index("Use typed model"),
                key="settings_openrouter_preset",
            )
            typed_default = current_model if preset == "Use typed model" else preset
            model = st.text_input(
                "OpenRouter Model",
                value=typed_default,
                placeholder="provider/model-name",
                key="settings_openrouter_model",
            ).strip() or typed_default
            st.session_state["openrouter_model"] = model
        elif model_options:
            stored_model = st.session_state.get(_provider_state_key("ai_model", provider)) or st.session_state.get("ai_model") or _default_model(provider)
            model = st.selectbox(
                "Model",
                model_options,
                index=model_options.index(stored_model) if stored_model in model_options else 0,
                key=_provider_state_key("settings_ai_model", provider),
            )

        if model:
            st.session_state[_provider_state_key("ai_model", provider)] = model
            st.session_state["ai_model"] = model

        key_state = _provider_state_key("ai_api_key", provider)
        existing_key = st.session_state.get(
            "gemini_api_key" if provider == "Google Gemini" else key_state,
            st.session_state.get(key_state, ""),
        )
        api_key = st.text_input(
            f"API Key - {provider}",
            value=existing_key,
            type="password",
            key=_provider_state_key("settings_api_key", provider),
        )
        st.session_state[key_state] = api_key
        st.session_state["ai_api_key"] = api_key
        if provider == "Google Gemini":
            st.session_state["gemini_api_key"] = api_key
        elif provider == "OpenRouter":
            st.session_state["openrouter_api_key"] = api_key


def _render_mt5_settings(runtime) -> None:
    with st.container(border=True):
        st.markdown("#### MT5 Connection")
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("Connect MT5", key="settings_connect_mt5", use_container_width=True):
                connector = runtime.mt5.connector
                conn_status = connector.initialize()
                runtime.mt5.connection_status = conn_status
                st.session_state["mt5_connected"] = conn_status.get("connected", False)
                st.session_state["mt5_broker"] = conn_status.get("broker", "N/A")
                st.session_state["mt5_server"] = conn_status.get("server", "N/A")
                st.session_state["mt5_terminal"] = conn_status.get("terminal", "N/A")
                if conn_status.get("connected"):
                    acc_info = connector.get_account_info()
                    st.session_state["mt5_balance"] = acc_info.get("balance", 0.0)
                    st.session_state["mt5_equity"] = acc_info.get("equity", 0.0)
                    st.session_state["mt5_currency"] = acc_info.get("currency", "")
                    st.session_state["mt5_leverage"] = acc_info.get("leverage", "")
                    st.success("Connected to MT5.")
                else:
                    st.error(f"MT5 connection failed: {conn_status.get('last_error')}")
        with c2:
            st.caption(f"Broker: {st.session_state.get('mt5_broker', 'N/A')}")
            st.caption(f"Server: {st.session_state.get('mt5_server', 'N/A')}")
            st.caption(f"Terminal: {st.session_state.get('mt5_terminal', 'N/A')}")


def _render_safety_settings(state, engine) -> None:
    with st.container(border=True):
        st.markdown("#### Safety")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Reset Runtime Lock", key="settings_reset_runtime", use_container_width=True):
                state.reset_daily_stats()
                st.rerun()
        with c2:
            if st.button("Flatten Local Positions", key="settings_flatten_positions", type="primary", use_container_width=True):
                for pos in list(getattr(state, "active_positions", [])):
                    cd = {"close": state.last_price, "high": state.last_price, "low": state.last_price, "open": state.last_price}
                    closed = engine.trade_manager.close_position(pos, cd, state.last_price, "settings_flatten")
                    state.remove_position(pos["ticket"])
                    engine.balance += closed["profit"]
                state.set_engine_state("EMERGENCY")
                st.rerun()


def render_settings_page(state, engine) -> None:
    st.markdown("### Settings")
    st.caption("Runtime controls for AI explanations, MT5 connectivity, execution mode, safety, and commands.")
    from deployment.engine_runtime import get_global_runtime
    runtime = get_global_runtime()

    _render_market_basket_settings(runtime)
    _render_status_cards(state, runtime)
    left, right = st.columns(2, gap="large")
    with left:
        _render_appearance_settings()
        _render_execution_settings(state)
        _render_mt5_settings(runtime)
    with right:
        _render_ai_settings()
        _render_safety_settings(state, engine)

    with st.container(border=True):
        from ui.command_palette import render_command_palette
        render_command_palette(state, engine)
