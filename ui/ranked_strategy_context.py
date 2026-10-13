"""
Shared ranked-strategy context panels for Dashboard and Live Trading.
Presentation-only: reads deterministic tournament state and writes the selected
ranked strategy name to session_state for downstream UI context.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd


def _strategy_name(item: dict) -> str:
    return str(item.get("strategy") or item.get("strategy_name") or item.get("name") or "N/A")


def _num(item: dict, *keys: str, default="N/A"):
    for key in keys:
        value = item.get(key)
        if isinstance(value, (int, float)):
            return value
        if value not in (None, ""):
            return value
    return default


def _ordered_ranked_strategies(state) -> list[dict]:
    ranked = (
        getattr(state, "latest_tournament", None)
        or st.session_state.get("tournament_results")
        or []
    )
    if not ranked:
        recommended = st.session_state.get("recommended_strategy")
        if isinstance(recommended, dict):
            ranked = [recommended]
    rows = [item for item in ranked if isinstance(item, dict)]
    return sorted(rows, key=lambda row: int(row.get("rank", 999)))


def _strategy_rows(ranked: list[dict]) -> list[dict]:
    rows = []
    for idx, item in enumerate(ranked, start=1):
        name = _strategy_name(item)
        rows.append({
            "rank": item.get("rank", idx),
            "strategy": name,
            "fit": _num(item, "market_fit_score", "fit_score"),
            "readiness": _num(item, "readiness", "readiness_score", "execution_readiness"),
            "bias": item.get("deployment_bias", item.get("bias", "N/A")),
            "signal": item.get("signal", item.get("direction", "N/A")),
            "risk": item.get("risk_level", item.get("risk", "N/A")),
            "confidence": _num(item, "confidence", "confidence_score"),
        })
    return rows


def selected_ranked_strategy(state) -> dict:
    ranked = _ordered_ranked_strategies(state)
    selected_name = st.session_state.get("runtime_strategy")
    if selected_name:
        for item in ranked:
            if _strategy_name(item).lower() == str(selected_name).lower():
                return item
    return ranked[0] if ranked else {}


def render_ranked_strategy_context(state, *, key_prefix: str, compact: bool = False) -> dict:
    ranked = _ordered_ranked_strategies(state)
    if not ranked:
        st.info("No ranked strategy context yet. Run Analysis first so Dashboard and Live Trading can inherit tournament selection.")
        return {}

    current = selected_ranked_strategy(state)
    current_name = _strategy_name(current)
    options = [_strategy_name(item) for item in ranked]
    if current_name not in options:
        current_name = options[0]

    label_map = {
        _strategy_name(item): (
            f"#{item.get('rank', idx)} | {_strategy_name(item)} | "
            f"fit {_num(item, 'market_fit_score', 'fit_score')} | "
            f"{item.get('deployment_bias', item.get('bias', 'N/A'))}"
        )
        for idx, item in enumerate(ranked, start=1)
    }

    st.markdown("#### Ranked Strategy Context")
    selected_name = st.selectbox(
        "Strategy selected from Analysis tournament",
        options,
        index=options.index(current_name),
        format_func=lambda name: label_map.get(name, name),
        key=f"{key_prefix}_ranked_strategy_selector",
    )

    selected = next((item for item in ranked if _strategy_name(item) == selected_name), ranked[0])
    st.session_state["runtime_strategy"] = selected_name
    st.session_state["runtime_strategy_rank"] = selected.get("rank", 1)
    st.session_state["runtime_strategy_context"] = selected

    cols = st.columns(4 if compact else 6)
    cols[0].metric("Rank", f"#{selected.get('rank', 1)}")
    cols[1].metric("Fit", str(_num(selected, "market_fit_score", "fit_score")))
    cols[2].metric("Bias", str(selected.get("deployment_bias", selected.get("bias", "N/A"))))
    cols[3].metric("Signal", str(selected.get("signal", selected.get("direction", "N/A"))))
    if not compact:
        cols[4].metric("Risk", str(selected.get("risk_level", selected.get("risk", "N/A"))))
        cols[5].metric("Confidence", str(_num(selected, "confidence", "confidence_score")))

    if not compact:
        st.dataframe(pd.DataFrame(_strategy_rows(ranked)), use_container_width=True, hide_index=True)
    else:
        with st.expander("Ranked tournament table", expanded=False):
            st.dataframe(pd.DataFrame(_strategy_rows(ranked)), use_container_width=True, hide_index=True)

    return selected
