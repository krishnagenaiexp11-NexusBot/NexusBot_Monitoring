"""
app_v2.py
NexusBot V2 — Clean Guided Workflow & Visual Intelligence Terminal

A structured 5-step trading intelligence platform:
  1. Upload Dataset
  2. Analyse Market Regime
  3. Run Strategy Tournament
  4. Optimise Recommended Strategy
  5. Generate Deployment Candidate
"""
import io
import os
import streamlit as st
import pandas as pd
import numpy as np
import datetime
from datetime import timezone
from utils.data_loader import resolve_symbol

# ── Page config (MUST be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title = "NexusBot V3 Terminal",
    page_icon  = "🤖",
    layout     = "wide",
    initial_sidebar_state = "collapsed",
)

# ── Premium Terminal CSS & Glassmorphism Styling ──────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #050816 !important;
    color: #e6edf3 !important;
}

.stApp {
    background: #050816 !important;
    color: #e6edf3 !important;
}

.main {
    background: #050816 !important;
}

.block-container {
    background: #050816 !important;
}

[data-testid="stAppViewContainer"] {
    background: #050816 !important;
}

[data-testid="stHeader"] {
    background-color: #050816 !important;
}

/* Glassmorphism Card Accents */
div[data-testid="stExpander"], [data-testid="stExpander"], .step-card, .metric-card, .winner-card, .rejection-card {
    background: rgba(11, 18, 32, 0.7) !important;
    border: 1px solid rgba(51, 65, 85, 0.5) !important;
    border-radius: 10px !important;
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37) !important;
    backdrop-filter: blur(8px) !important;
    -webkit-backdrop-filter: blur(8px) !important;
    margin-bottom: 15px !important;
}

div[data-testid="stSidebar"], [data-testid="stSidebar"], [data-testid="collapsedControl"] {
    display: none !important;
}

[data-testid="stDataFrame"] {
    background-color: #0b1220 !important;
}

div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input, select {
    background-color: #0b111e !important;
    color: #f1f5f9 !important;
    border: 1px solid #1e293b !important;
}

.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #3b82f6, #22c55e) !important;
}

@keyframes pulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }
    70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(34, 197, 94, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
}
</style>
""", unsafe_allow_html=True)

_ui_theme = st.session_state.get("ui_theme", "Dark")
if _ui_theme == "Light":
    st.markdown(
        """
        <style>
        :root {
            --nx-bg: #f4f7fb;
            --nx-surface: #ffffff;
            --nx-surface-soft: #f8fafc;
            --nx-border: #d6e0ec;
            --nx-border-strong: #b9c7d8;
            --nx-text: #0f172a;
            --nx-muted: #475569;
            --nx-faint: #64748b;
            --nx-blue: #2563eb;
            --nx-green: #16a34a;
            --nx-red: #dc2626;
            --nx-yellow: #b7791f;
            --nx-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
        }

        html, body, .stApp, .main, .block-container,
        [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            background: var(--nx-bg) !important;
            color: var(--nx-text) !important;
        }

        .block-container {
            padding-top: 1rem !important;
            max-width: 96rem !important;
        }

        div[data-testid="stMarkdownContainer"],
        label, p, h1, h2, h3, h4, h5, h6, small {
            color: var(--nx-text) !important;
            text-shadow: none !important;
        }

        [data-testid="stCaptionContainer"], .stCaptionContainer,
        div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stMarkdownContainer"] small {
            color: var(--nx-muted) !important;
        }

        div[data-testid="stExpander"], [data-testid="stExpander"],
        [data-testid="stVerticalBlockBorderWrapper"], div[data-testid="stForm"],
        .step-card, .metric-card, .winner-card, .rejection-card {
            background: var(--nx-surface) !important;
            border: 1px solid var(--nx-border) !important;
            border-radius: 8px !important;
            box-shadow: var(--nx-shadow) !important;
            color: var(--nx-text) !important;
        }

        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary * {
            background: var(--nx-surface) !important;
            color: var(--nx-text) !important;
        }

        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stDateInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-baseweb="select"] > div,
        div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
        textarea, select {
            background: var(--nx-surface) !important;
            color: var(--nx-text) !important;
            border: 1px solid var(--nx-border-strong) !important;
            box-shadow: none !important;
        }

        div[data-baseweb="popover"], div[data-baseweb="menu"], ul[role="listbox"] {
            background: var(--nx-surface) !important;
            color: var(--nx-text) !important;
        }

        div[data-testid="stButton"] button {
            background: var(--nx-surface) !important;
            color: var(--nx-text) !important;
            border: 1px solid var(--nx-border-strong) !important;
            border-radius: 8px !important;
            box-shadow: none !important;
            font-weight: 600 !important;
        }

        div[data-testid="stButton"] button:hover {
            border-color: var(--nx-blue) !important;
            color: var(--nx-blue) !important;
        }

        div[data-testid="stButton"] button[kind="primary"] {
            background: var(--nx-blue) !important;
            color: #ffffff !important;
            border-color: var(--nx-blue) !important;
        }

        div[data-testid="stButton"] button[kind="primary"] * {
            color: #ffffff !important;
        }

        [data-testid="stDataFrame"], [data-testid="stTable"] {
            background: var(--nx-surface) !important;
            border: 1px solid var(--nx-border) !important;
            border-radius: 8px !important;
            color: var(--nx-text) !important;
            box-shadow: var(--nx-shadow) !important;
        }

        [data-testid="stDataFrame"] * {
            color: var(--nx-text) !important;
        }

        [data-testid="stDataFrame"] iframe {
            background: var(--nx-surface) !important;
        }

        .stDataFrame div,
        .stDataFrame span,
        .stDataFrame p {
            color: var(--nx-text) !important;
        }

        div[data-testid="stHorizontalBlock"] {
            gap: 0.75rem !important;
        }

        div[data-testid="stAlert"] {
            border-radius: 8px !important;
            color: var(--nx-text) !important;
        }

        div[data-testid="stAlert"] * {
            color: var(--nx-text) !important;
        }

        div[data-testid="stMetric"], div[data-testid="stMetric"] * {
            color: var(--nx-text) !important;
        }

        div[data-testid="stRadio"] label,
        div[data-testid="stCheckbox"] label,
        div[data-testid="stToggle"] label {
            color: var(--nx-text) !important;
        }

        hr {
            border-color: var(--nx-border) !important;
        }

        .js-plotly-plot, .plot-container, .svg-container {
            background: var(--nx-surface) !important;
            border-radius: 8px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ── Global Background Engine Initialization ───────────────────────────────────
from deployment.engine_runtime import get_global_runtime
runtime = get_global_runtime()
runtime.start()

state = runtime.state_manager
engine = runtime.engine

CLOUD_DEMO = os.getenv("NEXUSBOT_CLOUD_DEMO", "0") == "1"
if CLOUD_DEMO:
    # The hosted edition is intentionally analysis-only. Streamlit Community
    # Cloud has no local MetaTrader terminal, and public visitors must never be
    # able to switch the shared runtime into broker execution mode.
    state.deployment_mode = "ADVISORY"
    st.info("Cloud demo: analysis and simulation only. Live broker execution is disabled.")

SYMBOLS_BY_ASSET_CLASS = {
    "Forex": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD"],
    "Indices": ["US500", "NAS100", "US30", "GER40", "UK100"],
    "Commodities": ["XAUUSD", "XAGUSD", "USOIL", "UKOIL"],
    "Crypto": ["BTCUSD", "ETHUSD"],
    "Stocks": [],
    "Custom": [],
}

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

AI_DEFAULT_MODELS = {
    provider: options[0]
    for provider, options in AI_MODEL_OPTIONS.items()
    if options
}


def _normalize_runtime_symbol(value: str | None, fallback: str = "UNKNOWN") -> str:
    return str(value or fallback).strip().upper() or fallback


def _provider_state_key(prefix: str, provider: str) -> str:
    safe_provider = "".join(ch.lower() if ch.isalnum() else "_" for ch in provider).strip("_")
    return f"{prefix}_{safe_provider}"


CANDLE_TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 5 * 60,
    "M15": 15 * 60,
    "M30": 30 * 60,
    "H1": 60 * 60,
    "H4": 4 * 60 * 60,
    "D1": 24 * 60 * 60,
}


def _active_candle_timeframe() -> str:
    tf = (
        st.session_state.get("runtime_timeframe")
        or st.session_state.get("dashboard_timeframe")
        or st.session_state.get("chart_timeframe")
        or st.session_state.get("mt5_tf_input_lab")
        or st.session_state.get("mt5_tf_input")
        or "M5"
    )
    tf = str(tf or "M5").upper()
    return tf if tf in CANDLE_TIMEFRAME_SECONDS else "M5"


def _seconds_to_next_candle(timeframe: str) -> int:
    now_ts = int(datetime.datetime.now(timezone.utc).timestamp())
    tf_seconds = CANDLE_TIMEFRAME_SECONDS.get(timeframe, 60)
    elapsed = now_ts % tf_seconds
    remaining = tf_seconds - elapsed
    return max(1, int(remaining))


def _asset_class_for_symbol(symbol: str) -> str:
    for asset_class, symbols in SYMBOLS_BY_ASSET_CLASS.items():
        if symbol in symbols:
            return asset_class
    return "Custom"

# Sync runtime values to session state defaults
if "active_workspace_sel" not in st.session_state:
    st.session_state["active_workspace_sel"] = "Analysis Lab"
if "gemini_api_key" not in st.session_state:
    st.session_state["gemini_api_key"] = ""
if "ai_provider" not in st.session_state:
    st.session_state["ai_provider"] = "Deterministic Template"
if "ai_model" not in st.session_state:
    st.session_state["ai_model"] = ""
if "openrouter_api_key" not in st.session_state:
    st.session_state["openrouter_api_key"] = ""
if "openrouter_model" not in st.session_state:
    st.session_state["openrouter_model"] = AI_DEFAULT_MODELS.get("OpenRouter", "")

if "runtime_symbol" not in st.session_state:
    st.session_state["runtime_symbol"] = "XAUUSD"
if "runtime_symbols" not in st.session_state:
    st.session_state["runtime_symbols"] = [st.session_state["runtime_symbol"]]
if "runtime_timeframe" not in st.session_state:
    st.session_state["runtime_timeframe"] = "M5"

# Resolve active symbol for app execution
symbol = _normalize_runtime_symbol(st.session_state.get("runtime_symbol"))
runtime_symbols = [
    _normalize_runtime_symbol(sym)
    for sym in st.session_state.get("runtime_symbols", [symbol])
    if _normalize_runtime_symbol(sym)
]
if not runtime_symbols:
    runtime_symbols = [symbol]
if symbol not in runtime_symbols:
    runtime_symbols.insert(0, symbol)
runtime_symbols = list(dict.fromkeys(runtime_symbols))[:5]
st.session_state["runtime_symbols"] = runtime_symbols
st.session_state["runtime_symbol"] = symbol
runtime_timeframe = str(st.session_state.get("runtime_timeframe") or "M5").upper()
if runtime_timeframe not in CANDLE_TIMEFRAME_SECONDS:
    runtime_timeframe = "M5"
st.session_state["runtime_timeframe"] = runtime_timeframe
if hasattr(state, "watchlist_timeframe"):
    state.watchlist_timeframe = runtime_timeframe
runtime.set_symbol(symbol)
if hasattr(runtime, "set_timeframe"):
    runtime.set_timeframe(runtime_timeframe)

# Set defaults to prevent downstream KeyError
defaults = {
    "uploaded_df":          runtime.uploaded_df,
    "h1_df":                runtime.h1_df,
    "m15_df":               runtime.m15_df,
    "market_regime":        None,
    "mtf_context":          None,
    "market_explainer":     None,
    "tournament_results":   None,
    "recommended_strategy": runtime.recommended_strategy,
    "optimization_result":  runtime.optimization_result,
    "optimization_results": runtime.optimization_results,
    "optimization_status":  "PENDING",
    "opt_results_count":    0,
    "deployment_candidate": None,
    "workflow_complete":    False,
    "step_1_complete":      runtime.uploaded_df is not None,
    "step_2_complete":      False,
    "step_3_complete":      False,
    "step_4_complete":      False,
    "step_5_complete":      False,
    "orchestration_context": runtime.latest_orch_ctx,
    "v3_pipeline_complete":  runtime.latest_orch_ctx is not None,
    "last_uploaded_filename": None,
    "last_uploaded_filesize": 0,
    "opt_mode":             "quick_scan",
    "ingestion_source":     "Upload CSV",
    "mt5_connected":        False,
    "mt5_broker":           "N/A",
    "mt5_server":           "N/A",
    "mt5_balance":          0.0,
    "mt5_equity":           0.0,
    "mt5_currency":         "USD",
    "mt5_leverage":         100,
    "mt5_terminal":         "N/A",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

_runtime_mt5_status = getattr(runtime.mt5, "connection_status", {})
if _runtime_mt5_status.get("connected"):
    st.session_state["mt5_connected"] = True
    st.session_state["mt5_broker"] = _runtime_mt5_status.get("broker", st.session_state.get("mt5_broker", "N/A"))
    st.session_state["mt5_server"] = _runtime_mt5_status.get("server", st.session_state.get("mt5_server", "N/A"))
    st.session_state["mt5_terminal"] = _runtime_mt5_status.get("terminal", st.session_state.get("mt5_terminal", "N/A"))

# ── Engine State Atmosphere + Micro-Rail CSS ─────────────────────────────────
eng_st = state.engine_state
atmosphere_css = ""
if eng_st == "WATCHING":
    atmosphere_css = "border: 2px solid rgba(59,130,246,0.45) !important; box-shadow: 0 0 18px rgba(59,130,246,0.2) inset !important;"
elif eng_st == "ARMED":
    atmosphere_css = "border: 2px solid rgba(245,158,11,0.7) !important; animation: armed-pulse 2s infinite !important;"
elif eng_st in ("EXECUTING", "ACTIVE"):
    atmosphere_css = "border: 2px solid rgba(34,197,94,0.7) !important; animation: exec-pulse 3s infinite !important;"
elif eng_st == "LOCKED":
    atmosphere_css = "border: 2px solid rgba(239,68,68,0.6) !important;"
elif eng_st == "EMERGENCY":
    atmosphere_css = "border: 3px solid rgba(220,38,38,0.9) !important; animation: emergency-pulse 1.2s infinite !important;"

st.markdown(f"""
<style>
/* ── Collapse & hide default Streamlit sidebar toggle button ── */

/* ── Micro Icon Rail: 68px collapsed, 240px on hover ── */
[data-testid="stSidebar"] {{
    background: #050811 !important;
    border-right: 1px solid #1e293b !important;
}}
[data-testid="stSidebar"] > div:first-child {{
    padding: 10px 12px !important;
}}

/* ── Main content area offset for micro-rail ── */
[data-testid="stAppViewContainer"] {{
    {atmosphere_css}
}}

/* Hide hidden sync button */
div.element-container:has(button[key="sync_state_button_hidden"]) {{
    display: none !important;
}}

/* Rail icon labels: hidden by default, shown on sidebar hover */

/* Atmosphere keyframes */
@keyframes armed-pulse {{
    0%,100% {{ border-color: rgba(245,158,11,0.3); }}
    50% {{ border-color: rgba(245,158,11,0.9); box-shadow: 0 0 25px rgba(245,158,11,0.4) inset; }}
}}
@keyframes exec-pulse {{
    0%,100% {{ border-color: rgba(34,197,94,0.4); }}
    50% {{ border-color: rgba(239,68,68,0.5); box-shadow: 0 0 15px rgba(239,68,68,0.25) inset; }}
}}
@keyframes emergency-pulse {{
    0%,100% {{ border-color: rgba(220,38,38,0.4); }}
    50% {{ border-color: rgba(220,38,38,1.0); box-shadow: 0 0 35px rgba(220,38,38,0.65) inset; }}
}}
</style>
""", unsafe_allow_html=True)

# Automatic background synchronization JS script (ticks once every 2 seconds)
st.components.v1.html(
    """
    <script>
    // Legacy 2-second sync disabled. Candle-bound refresh is scheduled later.
    window.parent.__nexusbot_auto_refresh = false;
    </script>
    """,
    height=0,
    width=0
)


# Runtime settings moved to ui/settings_page.py. Market selection lives in Analysis Lab.

# ── Top Navigation Bar + Status Header ────────────────────────────────────────
active_ws = st.session_state.get("active_workspace_sel", "Analysis Lab")

# Compute display values for top nav
_mt5_conn     = st.session_state.get("mt5_connected", False)
_mt5_color    = "#22c55e" if _mt5_conn else "#ef4444"
_mt5_txt      = "LIVE" if _mt5_conn else "OFFLINE"
_regime       = state.current_regime.upper()
_regime_colors = {"TRENDING": "#22c55e", "RANGING": "#3b82f6", "VOLATILE": "#f59e0b",
                  "LOW_VOLATILITY": "#94a3b8", "NEUTRAL": "#cbd5e1"}
_reg_color    = _regime_colors.get(_regime, "#cbd5e1")
_eng_state    = state.engine_state
_eng_colors   = {"SAFE": "#3b82f6", "ARMED": "#f59e0b", "ACTIVE": "#22c55e",
                 "EXECUTING": "#22c55e", "PAUSED": "#64748b",
                 "LOCKED": "#ef4444", "EMERGENCY": "#dc2626", "WATCHING": "#3b82f6"}
_eng_color    = _eng_colors.get(_eng_state, "#cbd5e1")
try:
    _snapshot = runtime.snapshot_store.get_snapshot().to_dict()
except Exception:
    _snapshot = {}
_live_metrics = _snapshot.get("live_metrics", {}) if isinstance(_snapshot, dict) else {}
_market_state = _snapshot.get("market_state", {}) if isinstance(_snapshot, dict) else {}
_bal          = float(_live_metrics.get("balance") or st.session_state.get("mt5_balance") or engine.balance or 0.0)
_equity       = float(_live_metrics.get("equity") or st.session_state.get("mt5_equity") or _bal or 0.0)
_currency     = _live_metrics.get("currency", "USD")
_pnl          = _equity - _bal
_pnl_color    = "#22c55e" if _pnl >= 0 else "#ef4444"
_pnl_txt      = f"{_currency} {_pnl:+.2f}"
_utc          = datetime.datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
_spread       = float(_market_state.get("spread", getattr(state, "last_spread", 0.0)) or 0.0)
_live_price   = float(_market_state.get("price") or st.session_state.get("last_live_price") or getattr(state, "last_price", 0.0) or 0.0)
_symbol       = st.session_state.get("runtime_symbol", "UNKNOWN")
_cand_name    = "—"
if state.active_candidates:
    _c = state.active_candidates[0]
    _cand_name = f"{_c.get('strategy','?')} {_c.get('direction','')}"
_conf = 0.0
if state.latest_tournament:
    _conf = state.latest_tournament[0].get("confidence", 0.0)
_stress       = getattr(state, "stress_level", "LOW")
_stress_colors = {"LOW": "#22c55e", "MODERATE": "#f59e0b", "HIGH": "#ef4444", "EXTREME": "#dc2626"}
_stress_color = _stress_colors.get(_stress, "#cbd5e1")
_deploy_mode  = getattr(state, "deployment_mode", "ADVISORY")
_sync_timeframe = _active_candle_timeframe()
_secs_left = _seconds_to_next_candle(_sync_timeframe)
_sync_delay_ms = (_secs_left + 1) * 1000
_price_decimals = 2 if any(tok in str(_symbol).upper() for tok in ("XAU", "XAG", "US", "NAS", "GER", "UK", "OIL")) else 5
_price_txt = f"{_live_price:.{_price_decimals}f}" if _live_price > 0 else "-"

# Nav tab definitions
_nav_tabs = [
    ("Analysis Lab", "A", "Analysis"),
    ("Dashboard View", "D", "Dashboard"),
    ("Optimizer Lab", "O", "Optimizer"),
    ("Settings", "S", "Settings"),
]

_light_theme = st.session_state.get("ui_theme", "Dark") == "Light"
_nav_bg = "background:#ffffff;" if _light_theme else "background:linear-gradient(135deg,#090d16 0%,#0f172a 100%);"
_nav_border = "#d6e0ec" if _light_theme else "#1e293b"
_nav_shadow = "0 8px 24px rgba(15,23,42,0.08)" if _light_theme else "0 4px 20px rgba(0,0,0,0.55)"
_nav_brand = "#0f172a" if _light_theme else "#f8fafc"
_nav_label = "#475569" if _light_theme else "#64748b"
_nav_value = "#0f172a" if _light_theme else "#cbd5e1"
_nav_pill_bg = "#f1f5f9" if _light_theme else "#1e293b"
_nav_pill_border = "#cbd5e1" if _light_theme else "#334155"
_nav_pill_text = "#334155" if _light_theme else "#94a3b8"
_nav_row_border = "#e2e8f0" if _light_theme else "#1e293b"
if _light_theme:
    if _regime in ("NEUTRAL", "LOW_VOLATILITY"):
        _reg_color = "#475569"
    if _eng_color == "#cbd5e1":
        _eng_color = "#475569"
    if _stress_color == "#cbd5e1":
        _stress_color = "#475569"

def _nav_tab_html(label: str, icon: str, short: str, active: bool) -> str:
    if _light_theme:
        bg = "background:#eff6ff; border-bottom: 2px solid #2563eb;" if active else "background: transparent; border-bottom: 2px solid transparent;"
        col = "#1d4ed8" if active else "#475569"
    else:
        bg  = "background: linear-gradient(135deg, #1e40af22, #3b82f622); border-bottom: 2px solid #3b82f6;" if active else "background: transparent; border-bottom: 2px solid transparent;"
        col = "#f1f5f9" if active else "#64748b"
    return (
        f'<div id="nav-tab-{label.replace(" ","-").lower()}" '
        f'style="display:inline-flex;align-items:center;gap:6px;padding:8px 18px;'
        f'{bg} border-radius:6px 6px 0 0; transition:all 0.18s; color:{col};'
        f'font-size:0.82rem; font-weight:600; font-family:\'Inter\',sans-serif;">'
        f'<span style="font-size:1rem;">{icon}</span>'
        f'<span>{short}</span>'
        f'</div>'
    )

_tabs_html = "".join(_nav_tab_html(l, ic, sh, l == active_ws) for l, ic, sh in _nav_tabs)

top_nav_html = f"""
<div style="{_nav_bg}
     border:1px solid {_nav_border}; border-radius:10px;
     padding:10px 16px 0 16px; margin-bottom:6px;
     box-shadow:{_nav_shadow}; font-family:'Inter',sans-serif;">

  <!-- Row 1: Brand + live metrics -->
  <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;padding-bottom:8px;border-bottom:1px solid {_nav_row_border};">
    <div style="display:flex;align-items:center;gap:8px;">
      <span style="display:inline-block;width:8px;height:8px;background:#22c55e;border-radius:50%;box-shadow:0 0 8px #22c55e;animation:pulse 2s infinite;"></span>
      <span style="font-weight:900;font-size:1.1rem;color:{_nav_brand};letter-spacing:1px;">NEXUS<span style="color:#3b82f6;">BOT</span></span>
      <span style="background:#3b82f622;border:1px solid #3b82f644;color:#3b82f6;font-size:0.6rem;font-weight:700;padding:1px 6px;border-radius:4px;">V3 OS</span>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:0.72rem;">
      <span style="color:{_nav_label};">MT5: <b style="color:{_mt5_color};">{_mt5_txt}</b></span>
      <span style="color:{_nav_label};">SYMBOL: <b style="color:{_nav_value};">{_symbol}</b></span>
      <span style="color:{_nav_label};">PRICE: <b style="color:{_nav_value};">{_price_txt}</b></span>
      <span style="color:{_nav_label};">REGIME: <b style="color:{_reg_color};">{_regime}</b></span>
      <span style="color:{_nav_label};">ENGINE: <b style="color:{_eng_color};">{_eng_state}</b></span>
      <span style="color:{_nav_label};">SPREAD: <b style="color:{_nav_value};">{_spread:.1f}pt</b></span>
      <span style="color:{_nav_label};">STRATEGY: <b style="color:{_nav_value};">{engine.profile.name}</b></span>
      <span style="color:{_nav_label};">P&amp;L: <b style="color:{_pnl_color};">{_pnl_txt}</b></span>
      <span style="color:{_nav_label};">MODE: <b style="color:#7c3aed;">{_deploy_mode}</b></span>
      <span style="background:{_nav_pill_bg};color:{_nav_pill_text};padding:2px 8px;border-radius:4px;border:1px solid {_nav_pill_border};font-weight:700;">{_utc}</span>
    </div>
  </div>

  <!-- Row 2: Heartbeat + Candidate -->
  <div style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;padding:6px 0 4px 0;font-size:0.7rem;">
    <span style="display:inline-flex;align-items:center;gap:5px;">
      <span style="width:5px;height:5px;background:{_eng_color};border-radius:50%;box-shadow:0 0 5px {_eng_color};display:inline-block;"></span>
      <span style="color:{_nav_label};">Loop: <b style="color:{_eng_color};">{_eng_state}</b></span>
    </span>
    <span style="color:{_nav_label};">Candidate: <b style="color:{_nav_value};">{_cand_name}</b></span>
    <span style="color:{_nav_label};">Confidence: <b style="color:#16a34a;">{_conf:.1f}%</b></span>
    <span style="color:{_nav_label};">Stress: <b style="color:{_stress_color};">{_stress}</b></span>
    <span style="color:{_nav_label};">Next {_sync_timeframe} Candle: <b style="color:#b7791f;font-family:monospace;">T-{_secs_left}s</b></span>
    <span style="color:{_nav_label};">Balance: <b style="color:#b7791f;">{_currency} {_bal:,.2f}</b></span>
    <span style="color:{_nav_label};">Equity: <b style="color:{_nav_value};">{_currency} {_equity:,.2f}</b></span>
    <span style="color:{_nav_label};">Safety: <b style="color:{'#ef4444' if state.emergency_shutdown else '#16a34a'};">{'LOCKED' if state.emergency_shutdown else 'CLEAR'}</b></span>
  </div>

  <!-- Row 3: Tab navigation -->
  <div style="display:flex;gap:4px;align-items:flex-end;padding-top:4px;">
    {_tabs_html}
  </div>
</div>
"""
st.markdown(top_nav_html, unsafe_allow_html=True)

nav_cols = st.columns(len(_nav_tabs))
for idx, (label, _icon, short) in enumerate(_nav_tabs):
    with nav_cols[idx]:
        nav_type = "primary" if label == active_ws else "secondary"
        if st.button(short, key=f"workspace_nav_{label}", type=nav_type, use_container_width=True):
            if st.session_state.get("active_workspace_sel") != label:
                st.session_state["active_workspace_sel"] = label
                st.rerun()


# ── Handle URL-param workspace nav (from tab links) ───────────────────────────
_qs = st.query_params
if "ws" in _qs:
    _qs_ws = _qs["ws"]
    if _qs_ws != active_ws:
        st.session_state["active_workspace_sel"] = _qs_ws
        st.query_params.clear()
        st.rerun()


# ── Background auto-sync (JS tick) ───────────────────────────────────────────
st.components.v1.html(
    f"""
    <script>
    const parentWin = window.parent;
    if (parentWin.__nexusbot_candle_sync_timer) {{
        clearTimeout(parentWin.__nexusbot_candle_sync_timer);
    }}
    parentWin.__nexusbot_auto_refresh = false;
    parentWin.__nexusbot_candle_sync_timer = setTimeout(function() {{
        const btn = Array.from(parentWin.document.querySelectorAll("button"))
            .find(el => el.innerText.trim() === "Candle Sync");
        if (btn) {{
            btn.click();
        }}
    }}, {_sync_delay_ms});
    </script>
    """,
    height=0, width=0
)


# ── Workspace Routing ─────────────────────────────────────────────────────────
if active_ws == "Analysis Lab":
    from ui.analysis_lab import render_analysis_lab
    render_analysis_lab(state, engine)
    st.stop()

elif active_ws == "Dashboard View":
    from ui.dashboard_view import render_dashboard_view
    render_dashboard_view(state, engine)
    st.stop()

elif active_ws == "Live Trade Center":
    from ui.live_trade_center import render_live_trade_center
    render_live_trade_center(state, engine)
    st.stop()

elif active_ws == "Optimizer Lab":
    from ui.optimizer_lab import render_optimizer_lab
    render_optimizer_lab(state, engine)
    st.stop()

elif active_ws == "Settings":
    from ui.settings_page import render_settings_page
    render_settings_page(state, engine)
    st.stop()


# ── Legacy workflow below (will not execute due to st.stop() above) ───────────
# STEP 1 — DATASET INGESTION
# ─────────────────────────────────────────────────────────────────────────────
step_header(1, "Choose Ingestion Source & Normalize Schema", st.session_state["step_1_complete"])

import datetime

ingest_mode = st.radio(
    "Choose Data Ingestion Source",
    options=["Upload CSV", "Download From MT5"],
    index=0 if st.session_state.get("ingestion_source", "Upload CSV") == "Upload CSV" else 1,
    horizontal=True,
    key="ingestion_source_radio"
)
st.session_state["ingestion_source"] = ingest_mode

upload_col, preview_col = st.columns([1.8, 1.2])

if ingest_mode == "Upload CSV":
    with upload_col:
        uploaded_file = st.file_uploader(
            "Upload Broker CSV File",
            type=["csv"],
            help="Supports standard MT5 broker output exports. Normalizes Date+Time and Volume fields automatically.",
        )

    if uploaded_file:
        # Only execute expensive load logic if file actually changed
        if (st.session_state["last_uploaded_filename"] != uploaded_file.name or 
            st.session_state["last_uploaded_filesize"] != uploaded_file.size or 
            not st.session_state["step_1_complete"]):
            
            with st.spinner("Processing Ingestion Pipeline..."):
                try:
                    file_bytes = uploaded_file.read()
                    pipe_data = run_data_pipeline_cached(uploaded_file.name, file_bytes)

                    st.session_state["uploaded_df"] = pipe_data["df"]
                    st.session_state["h1_df"]       = pipe_data["h1_df"]
                    st.session_state["m15_df"]      = pipe_data["m15_df"]
                    st.session_state["pipeline_data"] = pipe_data
                    st.session_state["last_uploaded_filename"] = uploaded_file.name
                    st.session_state["last_uploaded_filesize"] = uploaded_file.size
                    st.session_state["step_1_complete"] = True

                    # Reset all downstream progress
                    for key in ("market_regime", "mtf_context", "market_explainer", "tournament_results", 
                                "recommended_strategy", "optimization_result", "deployment_candidate", "workflow_complete"):
                        st.session_state[key] = None
                    for step_f in ("step_2_complete", "step_3_complete", "step_4_complete", "step_5_complete"):
                        st.session_state[step_f] = False

                except Exception as exc:
                    st.error(f"❌ Ingestion Error: {exc}")
                    st.session_state["step_1_complete"] = False
else:
    # Ingestion via MT5
    with upload_col:
        st.markdown("##### 🔗 MetaTrader 5 Terminal Configuration")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Ingestion Asset Symbol:** `{st.session_state.get('runtime_symbol', 'UNKNOWN')}`")
            mt5_tf = st.selectbox("Base Timeframe", options=["M1", "M5", "M15", "M30", "H1", "H4"], index=1, key="mt5_tf_input")
        with c2:
            mt5_start_dt = st.date_input("Start Date", value=datetime.date.today() - datetime.timedelta(days=90), key="mt5_start_input")
            mt5_end_dt = st.date_input("End Date", value=datetime.date.today(), key="mt5_end_input")

        btn1, btn2, btn3 = st.columns(3)
        with btn1:
            connect_clicked = st.button("🔌 Connect MT5", type="secondary", use_container_width=True, key="btn_connect_mt5")
        with btn2:
            download_clicked = st.button("📥 Download Dataset", type="primary", use_container_width=True, disabled=not st.session_state.get("mt5_connected", False), key="btn_download_mt5")
        with btn3:
            analyze_clicked = st.button("🔍 Analyze Immediately", type="secondary", use_container_width=True, disabled=not st.session_state["step_1_complete"], key="btn_analyze_mt5")

        # Execute actions
        if connect_clicked:
            with st.spinner("Connecting to MT5 terminal..."):
                connector = runtime.mt5.connector
                conn_status = connector.initialize()
                runtime.mt5.connection_status = conn_status
                runtime.set_symbol(st.session_state.get("runtime_symbol", "UNKNOWN"))
                
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
                    st.success("✅ Successfully connected to MT5 API.")
                    st.rerun()
                else:
                    st.error(f"❌ Failed to initialize MT5 connection. last_error={conn_status.get('last_error')}")

        if download_clicked:
            with st.spinner("Downloading historical data from MT5..."):
                try:
                    from runtime.mt5_data_downloader import MT5DataDownloader
                    from runtime.dataset_bundle import DatasetBundle
                    from runtime.dataset_registry import DatasetRegistry
                    
                    connector = runtime.mt5.connector
                    conn_status = connector.initialize()
                    runtime.mt5.connection_status = conn_status
                    runtime.set_symbol(st.session_state.get("runtime_symbol", "UNKNOWN"))
                    
                    # Force simulated flag matching session state
                    if st.session_state.get("mt5_terminal", "") == "MetaTrader 5 (Simulated)":
                        connector.is_simulated = True
                    connector.ensure_symbol(st.session_state["runtime_symbol"])
                        
                    downloader = MT5DataDownloader(connector)
                    
                    # Convert dates to datetimes
                    dt_start = datetime.datetime.combine(mt5_start_dt, datetime.time.min)
                    dt_end = datetime.datetime.combine(mt5_end_dt, datetime.time.max)
                    
                    df, report = downloader.download_historical_data(
                        symbol=st.session_state["runtime_symbol"],
                        timeframe_str=mt5_tf,
                        start_date=dt_start,
                        end_date=dt_end
                    )
                    
                    if df is not None and not df.empty:
                        # Save local bundle
                        bundle_exporter = DatasetBundle()
                        meta = bundle_exporter.save_bundle(
                            symbol=st.session_state["runtime_symbol"],
                            broker=st.session_state.get("mt5_broker", "ICMarkets"),
                            base_df=df,
                            integrity_score=report["integrity_score"]
                        )
                        
                        # Register in SQLite
                        registry = DatasetRegistry()
                        registry.register_dataset(
                            symbol=st.session_state["runtime_symbol"],
                            timeframe=mt5_tf,
                            rows=len(df),
                            integrity_score=report["integrity_score"],
                            dataset_hash=meta["dataset_hash"]
                        )
                        registry.log_download(
                            symbol=st.session_state["runtime_symbol"],
                            timeframe=mt5_tf,
                            start_date=str(mt5_start_dt),
                            end_date=str(mt5_end_dt),
                            rows_downloaded=len(df),
                            status="SUCCESS"
                        )
                        registry.log_integrity_report(
                            dataset_hash=meta["dataset_hash"],
                            duplicates_removed=report["duplicates_removed"],
                            missing_candles=report["missing_candles"],
                            integrity_score=report["integrity_score"]
                        )
                        
                        # Store in session state
                        st.session_state["uploaded_df"] = df
                        # Load resampled bundle frames
                        loaded_bundle = bundle_exporter.load_bundle(st.session_state["runtime_symbol"])
                        if loaded_bundle:
                            # Run feature engineering on each resampled DataFrame once!
                            from engine.feature_engineering import compute_features
                            st.session_state["h1_df"] = compute_features(loaded_bundle["h1"])
                            st.session_state["m15_df"] = compute_features(loaded_bundle["m15"])
                            
                            # Construct Pipeline Summary
                            st.session_state["pipeline_data"] = {
                                "name": f"MT5_{st.session_state['runtime_symbol']}_{mt5_tf}",
                                "df": df,
                                "h1_df": st.session_state["h1_df"],
                                "m15_df": st.session_state["m15_df"],
                                "timeframe": mt5_tf,
                                "summary": {
                                    "rows": len(df),
                                    "date_range": f"{mt5_start_dt} to {mt5_end_dt}",
                                    "integrity_score": report["integrity_score"]
                                },
                                "normalization": {
                                    "mapped": {"time": "timestamp", "tick_volume": "volume"},
                                    "rows_loaded": len(df),
                                    "rows_removed": 0
                                }
                            }
                            st.session_state["step_1_complete"] = True
                            
                            # ── AUTO-PIPELINE TRIGGER ──
                            from engine.orchestration_context import OrchestrationContext
                            from engine.mtf_context import MTFContextEngine
                            from engine.h4_structure import H4StructureEngine
                            from engine.regime_transition import RegimeTransitionEngine
                            from engine.market_memory import MarketMemoryEngine
                            from engine.session_context import SessionContextEngine
                            
                            # Bundle with features pre-computed
                            computed_bundle = {
                                "m5": compute_features(loaded_bundle["m5"]),
                                "m15": st.session_state["m15_df"],
                                "h1": st.session_state["h1_df"],
                                "h4": compute_features(loaded_bundle["h4"])
                            }
                            
                            context_obj = OrchestrationContext(computed_bundle)
                            
                            # Run intelligence engines
                            context_obj.h4_structure = H4StructureEngine().analyze(computed_bundle["h4"])
                            
                            mtf_res = MTFContextEngine().analyze(computed_bundle["h1"], computed_bundle["m15"])
                            context_obj.h1_structure = mtf_res["h1_structure"]
                            context_obj.m15_execution = mtf_res["m15_execution"]
                            
                            context_obj.session_context = SessionContextEngine().analyze(computed_bundle["m5"])
                            context_obj.regime_transition = RegimeTransitionEngine().analyze(computed_bundle["h1"])
                            context_obj.market_memory = MarketMemoryEngine().analyze(computed_bundle["h1"])
                            
                            st.session_state["market_regime"] = context_obj.h1_structure
                            st.session_state["mtf_context"] = mtf_res
                            st.session_state["orchestration_context_obj"] = context_obj
                            st.session_state["step_2_complete"] = True
                            
                            # Reset downstream
                            for key in ("tournament_results", "recommended_strategy", "optimization_result", 
                                        "deployment_candidate", "workflow_complete", "market_explainer"):
                                st.session_state[key] = None
                            for step_f in ("step_3_complete", "step_4_complete", "step_5_complete"):
                                st.session_state[step_f] = False

                            st.success(f"✅ Downloaded {len(df):,} rows. Auto-built MTF bundle and ran market analysis.")
                            st.rerun()
                        else:
                            st.error("❌ Failed to build timeframe bundle from downloaded data.")
                    else:
                        st.error(f"❌ Downloaded dataset is empty. {report.get('error', '')}")
                except Exception as exc:
                    st.error(f"❌ MT5 Download failed: {exc}")
                    
        if analyze_clicked:
            st.rerun()

if st.session_state["step_1_complete"] and st.session_state["pipeline_data"]:
    p = st.session_state["pipeline_data"]
    summ = p.get("summary", {})
    norm = p.get("normalization", {})
    
    st.success(
        f"✅ **{p['name']}** successfully ingested — "
        f"**{summ.get('rows', 0):,} candles** | Timeframe: **{p['timeframe']}** | "
        f"Date Range: **{summ.get('date_range', '–')}**"
    )

    # Columns Merged Notification
    if norm.get("date_time_merged"):
        st.info("📅 Detected separate `Date` + `Time` fields. Dynamically combined them into a single canonical `timestamp`.")

    with st.expander("📋 Columns Normalization Report & Raw Data Preview"):
        r_col1, r_col2 = st.columns(2)
        with r_col1:
            st.markdown("**Column Mapping (Found → Canonical)**")
            for raw, canonical in norm.get("mapped", {}).items():
                st.markdown(f"- `{raw}` → `{canonical}`")
        with r_col2:
            st.markdown("**Data Counts**")
            st.write(f"- Rows loaded: {norm.get('rows_loaded', 0):,}")
            st.write(f"- Rows removed: {summ.get('rows_removed', 0):,}")
        
        st.markdown("**Normalized Sample (Top 5 rows)**")
        st.dataframe(st.session_state["uploaded_df"].head(5), use_container_width=True, hide_index=True)

st.markdown("---")


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2 — ANALYSE MARKET REGIME
# ─────────────────────────────────────────────────────────────────────────────
step_header(2, "Analyse Multi-Timeframe Market Regime", 
            st.session_state["step_2_complete"], 
            not st.session_state["step_1_complete"])

if not st.session_state["step_1_complete"]:
    st.info("Please upload and normalize a dataset in Step 1 first.")
else:
    # Run analysis ONLY on click
    if st.button("🔍 Run V3 Intelligence Pipeline (All 19 Engines)", key="btn_regime", type="primary"):
        with st.spinner("Running 19-engine intelligence pipeline — H4 → H1 → M15 → M5 → Risk → Narrative..."):
            try:
                from engine.intelligence_pipeline import run_intelligence_pipeline, clear_pipeline_cache
                from engine.mtf_context import MTFContextEngine

                h1_data  = st.session_state["h1_df"]
                m15_data = st.session_state["m15_df"]

                # Build bundle — use whatever timeframes we have
                pipe_data = st.session_state.get("pipeline_data", {})
                bundle = {
                    "m5":  pipe_data.get("m5_df", m15_data),   # fallback to m15 if no m5
                    "m15": m15_data,
                    "h1":  h1_data,
                    "h4":  pipe_data.get("h4_df", h1_data),    # fallback to h1 if no h4
                }
                # If the pipeline_data bundle has resampled h4/m5 DataFrames, use those
                if "h4" in pipe_data:
                    bundle["h4"] = pipe_data["h4"]
                if "m5" in pipe_data:
                    bundle["m5"] = pipe_data["m5"]

                # Clear cache so fresh computation runs
                clear_pipeline_cache()

                # Run the full pipeline
                orch_ctx = run_intelligence_pipeline(bundle, use_cache=False)

                # Store context and legacy fields for backward compatibility
                st.session_state["orchestration_context"] = orch_ctx
                st.session_state["market_regime"]   = orch_ctx.h1_structure
                st.session_state["mtf_context"]     = {
                    "h1_structure":   orch_ctx.h1_structure,
                    "m15_execution":  orch_ctx.m15_execution,
                    "alignment_score": orch_ctx.h1_structure.get("_alignment_score", 50.0)
                    if "_alignment_score" in orch_ctx.h1_structure
                    else MTFContextEngine().analyze(h1_data, m15_data).get("alignment_score", 50.0),
                    "context_label": orch_ctx.h1_structure.get("context_label", "Developing"),
                }
                st.session_state["v3_pipeline_complete"] = True
                st.session_state["step_2_complete"] = True

                # Reset downstream
                for key in ("tournament_results", "recommended_strategy", "optimization_result",
                            "deployment_candidate", "workflow_complete", "market_explainer"):
                    st.session_state[key] = None
                for step_f in ("step_3_complete", "step_4_complete", "step_5_complete"):
                    st.session_state[step_f] = False

            except Exception as exc:
                import traceback
                st.error(f"❌ Intelligence Pipeline failed: {exc}")
                st.caption(traceback.format_exc())
                st.session_state["step_2_complete"] = False

    if st.session_state["step_2_complete"]:
        # V3 Institutional Dashboard
        orch_ctx = st.session_state.get("orchestration_context")

        if orch_ctx is not None and st.session_state.get("v3_dashboard_mode", True):
            from ui.institutional_dashboard import render_institutional_dashboard
            render_institutional_dashboard(orch_ctx)

        # Legacy regime display (always shown for context continuity)
        h1_struct = st.session_state.get("market_regime") or {}
        m15_exec  = (st.session_state.get("mtf_context") or {}).get("m15_execution", {})
        context_data = st.session_state.get("mtf_context") or {}
        alignment_score = float(context_data.get("alignment_score", 50.0))

        if h1_struct:
            with st.expander("📊 Legacy Regime + Health Gauges", expanded=False):
                col_m1, col_m2 = st.columns([1.8, 1.2])
                with col_m1:
                    ctx_label = context_data.get("context_label", "")
                    if ctx_label:
                        st.markdown(f"#### 🌐 Context: `{ctx_label}`")
                    direction = h1_struct.get('structure_direction', 'NEUTRAL')
                    macro_regime = h1_struct.get('macro_regime', 'RANGING')
                    pb_qual = m15_exec.get('pullback_quality', 0.5)
                    st.markdown(
                        f"""
                        <div style="background-color:#1e293b;border:1px solid #334155;border-radius:10px;padding:18px;margin-bottom:14px;">
                            <h5 style="margin-top:0;color:#f8fafc;">📰 H1 Market Summary</h5>
                            <p style="color:#cbd5e1;font-size:0.9rem;line-height:1.5;margin-bottom:0;">
                                {st.session_state.get('runtime_symbol','N/A')} — <strong>{direction} {macro_regime}</strong> H1 structure.
                                M15 pullback quality: <strong>{pb_qual:.2f}</strong>.
                                MTF alignment: <strong>{alignment_score:.1f}/100</strong>.
                            </p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    exp_col1, exp_col2 = st.columns(2)
                    with exp_col1:
                        votes_bullish = h1_struct.get("_direction_bullish_votes", 2)
                        st.markdown(f"**📈 Trend — {direction} ({h1_struct.get('trend_strength',0):.0f}%)**")
                        st.write(f"- ADX: {h1_struct.get('_adx', 0):.1f}")
                        st.write(f"- Bullish votes: {votes_bullish}/3")
                        st.write(f"- HH/LL persistence: {h1_struct.get('trend_persistence',0)*100:.0f}%")
                    with exp_col2:
                        vol_state = h1_struct.get('volatility_state', 'NORMAL')
                        st.markdown(f"**❄️ Volatility — {vol_state}**")
                        st.write(f"- ATR ratio: {h1_struct.get('_atr_ratio',1):.2f}x mean")
                        st.write(f"- Compression: {h1_struct.get('_compression_score',1):.2f}")
                        st.write(f"- Breakout bias: {h1_struct.get('breakout_bias','NEUTRAL')}")
                with col_m2:
                    render_health_gauges(h1_struct, m15_exec)
                    render_regime_distribution(st.session_state["h1_df"])

st.markdown("---")


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3 — STRATEGY TOURNAMENT
# ─────────────────────────────────────────────────────────────────────────────
step_header(3, "Run Strategy Tournament Engine", 
            st.session_state["step_3_complete"], 
            not st.session_state["step_2_complete"])

if not st.session_state["step_2_complete"]:
    st.info("Please complete Step 2 Regime Analysis first.")
else:
    if st.button("🏆 Run Strategy Tournament", key="btn_tournament", type="primary"):
        with st.spinner("Scoring strategy fit, evaluating alignment, and computing fits..."):
            try:
                # Add tournament execution simulation logging
                progress_text = st.empty()
                progress_text.text("⚙️ Scoring volatility indicators...")
                import time; time.sleep(0.3)
                progress_text.text("📈 Evaluating multi-timeframe direction alignment...")
                time.sleep(0.3)
                progress_text.text("🏆 Computing final strategy fit scores...")
                time.sleep(0.2)
                progress_text.empty()

                from engine.strategy_tournament import StrategyTournamentEngine
                from engine.tournament_models import TournamentInput
                from engine.market_explainer import MarketExplainer

                tourney = StrategyTournamentEngine()
                orch_ctx = st.session_state.get("orchestration_context")

                h4_default = {"macro_strength": 0.0, "macro_direction": "NEUTRAL", "trend_age": 0, "exhaustion_risk": 50.0}
                readiness_default = {"execution_state": "WATCHLIST", "confluence_count": 0}
                mtf_default = st.session_state.get("mtf_context", {}) or {"h1_structure": {"macro_regime": "RANGING"}, "m15_execution": {"pullback_quality": 0.5}}
                candle_default = {"candle_quality": 50.0, "direction_bias": "NEUTRAL"}

                tourney_input = TournamentInput(
                    h4_structure=orch_ctx.h4_structure if (orch_ctx and orch_ctx.h4_structure) else h4_default,
                    mtf_context=st.session_state.get("mtf_context", {}) if st.session_state.get("mtf_context") else mtf_default,
                    m5_execution=orch_ctx.m5_precision if (orch_ctx and orch_ctx.m5_precision) else {},
                    session_context=orch_ctx.session_context if (orch_ctx and orch_ctx.session_context) else {},
                    candlestick_intelligence=orch_ctx.candlestick_intelligence if (orch_ctx and orch_ctx.candlestick_intelligence) else candle_default,
                    execution_readiness=orch_ctx.execution_readiness if (orch_ctx and orch_ctx.execution_readiness) else readiness_default,
                    contradiction_state=orch_ctx.contradiction_engine if orch_ctx else None,
                    institutional_risk=orch_ctx.institutional_risk if orch_ctx else None,
                    confidence_hierarchy=orch_ctx.confidence_hierarchy if orch_ctx else None,
                    signal_saturation=orch_ctx.signal_saturation if orch_ctx else None,
                    edge_validation=getattr(orch_ctx, "edge_validation", None) if orch_ctx else None,
                    market_similarity=getattr(orch_ctx, "market_similarity", None) if orch_ctx else None,
                    cross_asset_intelligence=getattr(orch_ctx, "cross_asset_intelligence", None) if orch_ctx else None,
                )

                results = tourney.rank(tourney_input)

                # Instantiating explainer to parse winner/rejections
                explainer = MarketExplainer()
                explainer_result = explainer.explain(
                    mtf_context        = st.session_state["mtf_context"],
                    tournament_results = results,
                    h1_df              = st.session_state["h1_df"],
                    m15_df             = st.session_state["m15_df"]
                )

                clean_results = StrategyTournamentEngine.strip_internal_fields(results)
                recommended = StrategyTournamentEngine.get_recommended(results)

                st.session_state["tournament_results"] = clean_results
                st.session_state["recommended_strategy"] = recommended
                st.session_state["market_explainer"] = explainer_result
                st.session_state["step_3_complete"] = True

                # Reset downstream
                for key in ("optimization_result", "deployment_candidate", "workflow_complete"):
                    st.session_state[key] = None
                for step_f in ("step_4_complete", "step_5_complete"):
                    st.session_state[step_f] = False

            except Exception as exc:
                st.error(f"❌ Tournament failed: {exc}")
                st.session_state["step_3_complete"] = False

    if st.session_state["step_3_complete"] and st.session_state["tournament_results"]:
        results = st.session_state["tournament_results"]
        winner = st.session_state["recommended_strategy"]
        explainer = st.session_state["market_explainer"]

        # Strategy reasoning narrative card
        st.markdown(
            f"""
            <div class="winner-card">
                <div style="color:#3b82f6;font-size:0.8rem;text-transform:uppercase;letter-spacing:1px;font-weight:700;">🏆 Tournament Recommendation</div>
                <h3 style="margin:4px 0 8px 0;color:#f8fafc;">{winner['strategy']}</h3>
                <p style="color:#93c5fd;font-size:1rem;margin:0 0 12px 0;">
                    Overall Fit Score: <strong>{winner['market_fit_score']:.1f}/100</strong>
                </p>
                <div style="color:#cbd5e1;font-size:0.9rem;">
                    <strong>Heuristic Reasoning:</strong><br>
                    {explainer['strategy_reasoning'].split('🏆')[1].split(')**')[1] if '🏆' in explainer['strategy_reasoning'] else explainer['strategy_reasoning']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Warning messages
        if explainer.get("warnings"):
            for warn in explainer["warnings"]:
                st.warning(f"⚠️ {warn}")

        t_col1, t_col2 = st.columns([1.8, 1.2])

        with t_col1:
            st.markdown("##### 🏁 Tournament Strategy Standings")
            # Custom styled cards list instead of ugly tables
            for idx, item in enumerate(results, 1):
                name = item["strategy"]
                score = item["market_fit_score"]
                match = "✅ Regime Match" if item["supported"] else "⚠️ No Match"
                border_color = "#3b82f6" if idx == 1 else "#1e293b"
                bg_color = "#172554" if idx == 1 else "#0f172a"
                
                st.markdown(
                    f"""
                    <div style="background:{bg_color};border:1px solid {border_color};border-radius:8px;padding:12px 16px;margin-bottom:8px;display:flex;align-items:center;">
                        <span style="font-weight:800;font-size:1.1rem;color:#64748b;margin-right:12px;">#{idx}</span>
                        <div>
                            <span style="font-weight:700;color:#f1f5f9;">{name}</span><br>
                            <span style="font-size:0.75rem;color:#94a3b8;">{match} ({", ".join(item['supported_regimes'])})</span>
                        </div>
                        <div style="margin-left:auto;text-align:right;">
                            <span style="font-weight:800;font-size:1.15rem;color:#3b82f6;">{score:.1f}</span><br>
                            <span style="font-size:0.7rem;color:#475569;">FIT</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Strategy Rejections Expander
            with st.expander("🚫 Strategy Rejection Log"):
                for name, reason in explainer["strategy_rejections"].items():
                    st.markdown(
                        f"""
                        <div class="rejection-card">
                            <strong>❌ {name}</strong><br>
                            <span style="color:#94a3b8;font-size:0.85rem;">Reason: {reason}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        with t_col2:
            # Signal Pipeline debug checklist for the recommended strategy
            st.markdown("##### 🛠️ Signal Pipeline Debugger")
            pipeline_stages = check_signal_pipeline(
                winner["strategy"], 
                st.session_state["market_regime"],
                st.session_state["mtf_context"]["m15_execution"]
            )
            for stage, passed, detail in pipeline_stages:
                status_icon = "✅ PASS" if passed else "❌ FAIL"
                status_color = "#22c55e" if passed else "#ef4444"
                st.markdown(
                    f"""
                    <div style="background:#111827;border:1px solid #1e293b;border-radius:6px;padding:8px 12px;margin-bottom:6px;display:flex;justify-content:between;align-items:center;">
                        <span style="font-size:0.85rem;font-weight:600;color:#94a3b8;">{stage}</span>
                        <div style="margin-left:auto;text-align:right;">
                            <span style="font-size:0.8rem;font-weight:700;color:{status_color};">{status_icon}</span><br>
                            <span style="font-size:0.7rem;color:#475569;">{detail}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

st.markdown("---")


# ──────────────────────────────────────────────────────────────────────────────
# STEP 4 — OPTIMISE RECOMMENDED STRATEGY
# ─────────────────────────────────────────────────────────────────────────────
step_header(4, "Optimise Recommended Strategy", 
            st.session_state["step_4_complete"], 
            not st.session_state["step_3_complete"])

if not st.session_state["step_3_complete"]:
    st.info("Please run the Strategy Tournament in Step 3 first.")
else:
    winner = st.session_state["recommended_strategy"]
    rec_name = winner["strategy"]
    
    # Render recommended strategy banner
    from ui.strategy_panels import render_recommended_strategy_card
    render_recommended_strategy_card(rec_name, winner["market_fit_score"])

    from ui.optimization_panels import render_optimization_mode_selector
    opt_mode = render_optimization_mode_selector()
    st.session_state["opt_mode"] = opt_mode

    max_comb = st.slider(
        "Max Optimizer Variant Configurations",
        min_value=6, max_value=36,
        value=12 if opt_mode == "quick_scan" else 20,
        step=2,
        key="opt_max_comb",
    )

    if st.button(f"⚡ Launch Optimizer for {rec_name}", key="btn_optimize", type="primary"):
        progress_bar = st.progress(0, text="Initializing mutation parameters...")
        cancel_ph = st.empty()
        cancel_check = cancel_ph.checkbox("Cancel optimization task", value=False, key="opt_cancel_chk")

        def cancel_fn():
            return st.session_state.get("opt_cancel_chk", False)

        def progress_fn(current: int, total: int, label: str):
            ratio = current / max(total, 1)
            progress_bar.progress(ratio, text=f"{label}: {current}/{total} variants")

        with st.spinner(f"Optimizing parameters for {rec_name}..."):
            try:
                from optimizer.optimizer_engine import OptimizerEngine
                optimizer = OptimizerEngine()
                df_data = st.session_state["uploaded_df"]

                if opt_mode == "quick_scan":
                    results = optimizer.quick_scan(
                        strategy_name    = rec_name,
                        df               = df_data,
                        starting_balance = starting_balance,
                        max_combinations = max_comb,
                        progress_callback= progress_fn,
                        cancel_flag      = cancel_fn,
                    )
                else:
                    results = optimizer.full_validate(
                        strategy_name    = rec_name,
                        df               = df_data,
                        starting_balance = starting_balance,
                        max_combinations = max_comb,
                        progress_callback= progress_fn,
                        cancel_flag      = cancel_fn,
                    )

                progress_bar.empty()
                cancel_ph.empty()
                if results and len(results) > 0:
                    st.session_state["optimization_result"] = results
                    st.session_state["optimization_results"] = results
                    st.session_state["opt_results_count"] = len(results)
                    st.session_state["optimization_status"] = "SUCCESS"
                    st.session_state["step_4_complete"] = True
                else:
                    st.session_state["optimization_result"] = []
                    st.session_state["optimization_results"] = []
                    st.session_state["opt_results_count"] = 0
                    st.session_state["optimization_status"] = "NO_VALID_CANDIDATES"
                    st.session_state["step_4_complete"] = False
                    st.warning("Optimization completed but produced no deployment-grade candidates.")
                
                # Reset downstream
                st.session_state["deployment_candidate"] = None
                st.session_state["step_5_complete"] = False
                st.session_state["workflow_complete"] = False

            except Exception as exc:
                progress_bar.empty()
                cancel_ph.empty()
                if st.session_state.get("opt_cancel_chk", False):
                    st.session_state["optimization_status"] = "CANCELLED"
                    st.warning("⚠️ Optimization cancelled by user.")
                else:
                    st.session_state["optimization_status"] = "FAILED"
                    st.error(f"❌ Optimizer crashed: {exc}")
                st.session_state["opt_results_count"] = 0
                st.session_state["step_4_complete"] = False

    if st.session_state["step_4_complete"] and st.session_state["optimization_result"]:
        from ui.optimization_panels import render_optimization_summary, render_optimization_results
        results = st.session_state["optimization_result"]
        render_optimization_summary(results, rec_name, st.session_state["opt_mode"])
        render_optimization_results(results, st.session_state["opt_mode"])

st.markdown("---")


# ──────────────────────────────────────────────────────────────────────────────
# STEP 5 — GENERATE DEPLOYMENT CANDIDATE
# ─────────────────────────────────────────────────────────────────────────────
step_header(5, "Generate Deployment Candidate Profile", 
            st.session_state["step_5_complete"], 
            not st.session_state["step_4_complete"] or st.session_state.get("opt_results_count", 0) == 0)

if not st.session_state["step_4_complete"]:
    st.info("Please optimize the strategy in Step 4 first.")
elif st.session_state.get("opt_results_count", 0) == 0:
    st.warning("⚠️ No profitable deployment-grade variants were produced by the optimizer. Deployment candidate generation is locked.")
else:
    winner = st.session_state["recommended_strategy"]
    rec_name = winner["strategy"]
    symbol = st.session_state.get("runtime_symbol") or "UNKNOWN"

    # Disable button if step 4 is incomplete or count is 0
    is_disabled = not st.session_state.step_4_complete or st.session_state.get("opt_results_count", 0) == 0
    if st.button("🚀 Generate & Export Profile Card", key="btn_deploy", type="primary", disabled=is_disabled):
        with st.spinner("Compiling deployment readiness metrics..."):
            try:
                from engine.deployment_candidate import generate_candidate
                from runtime.deployment_profile import save_profile

                results = st.session_state.get("optimization_result", [])
                if not results:
                    raise ValueError("No optimization candidates available for deployment profile generation.")
                best_result = results[0]
                
                candidate = generate_candidate(
                    symbol        = symbol,
                    strategy_name = rec_name,
                    opt_result    = best_result,
                )
                profile_id = save_profile(candidate)

                st.session_state["deployment_candidate"] = candidate
                st.session_state["profile_id"] = profile_id
                st.session_state["step_5_complete"] = True
                st.session_state["workflow_complete"] = True

            except Exception as exc:
                st.error(f"❌ Candidate creation failed: {exc}")
                st.session_state["step_5_complete"] = False

    if st.session_state["step_5_complete"] and st.session_state["deployment_candidate"]:
        from ui.deployment_panels import render_deployment_panel
        render_deployment_panel(st.session_state["deployment_candidate"])

st.markdown("---")


# ──────────────────────────────────────────────────────────────────────────────
# HISTORICAL PROFILE STORAGE SECTION
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("📁 Terminal Saved Profiles Database", expanded=False):
    try:
        from runtime.deployment_profile import load_all_profiles
        from ui.deployment_panels import render_saved_profiles_panel
        profiles = load_all_profiles()
        render_saved_profiles_panel(profiles)
    except Exception as exc:
        st.warning(f"Could not read profiles database: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# COLLAPSIBLE DEBUG PANEL
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("⚙️ Workflow State Monitor & Debug Panel", expanded=False):
    debug_state = {
        "step_1_complete": st.session_state["step_1_complete"],
        "step_2_complete": st.session_state["step_2_complete"],
        "step_3_complete": st.session_state["step_3_complete"],
        "step_4_complete": st.session_state["step_4_complete"],
        "step_5_complete": st.session_state["step_5_complete"],
        "workflow_complete": st.session_state["workflow_complete"],
        "loaded_file": st.session_state["last_uploaded_filename"],
        "loaded_size_bytes": st.session_state["last_uploaded_filesize"],
        "opt_results_count": len(st.session_state["optimization_result"]) if st.session_state["optimization_result"] else 0,
        "saved_profile_id": st.session_state["profile_id"],
    }
    st.json(debug_state)


# ──────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div style="text-align:center;color:#475569;font-size:0.75rem;
                margin-top:40px;padding-top:20px;border-top:1px solid #1e293b;">
        NexusBot V3 Terminal — Institutional Decision Intelligence OS | Local-First | No Cloud Required<br>
        19-Engine Intelligence Pipeline | Port: 8502 | V1 app running on Port 8501
    </div>
    """,
    unsafe_allow_html=True,
)


