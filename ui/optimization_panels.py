"""
ui/optimization_panels.py
Optimization progress and results UI panels.
"""
import streamlit as st
import pandas as pd


def render_optimization_results(results: list, mode: str = "quick_scan") -> None:
    """
    Renders optimization results table.

    Args:
        results : List of result dicts from OptimizerEngine
        mode    : "quick_scan" or "full_validate"
    """
    if not results:
        st.info("No optimization results yet.")
        return

    is_full = mode == "full_validate"

    rows = []
    for r in results:
        row = {
            "Rank":           r.get("rank",            "-"),
            "SL ATR":         r.get("sl_atr_multiplier", r.get("parameters", {}).get("sl_atr_multiplier", "-")),
            "TP ATR":         r.get("tp_atr_multiplier", r.get("parameters", {}).get("tp_atr_multiplier", "-")),
            "Cooldown":       r.get("entry_cooldown_candles", r.get("parameters", {}).get("entry_cooldown_candles", "-")),
            "Stability":      f"{r.get('stability_score', 0.0):.1f}",
            "Net Profit":     f"${r.get('net_profit', 0.0):.2f}",
            "PF":             f"{r.get('profit_factor', 0.0):.2f}",
            "Win Rate":       f"{r.get('win_rate', 0.0):.1f}%",
            "Max DD":         f"{r.get('max_drawdown_pct', 0.0):.2f}%",
            "Trades":         r.get("trades", 0),
        }
        if is_full:
            row["Deploy Score"] = f"{r.get('deployment_score', 0.0):.1f}"
            row["Grade"]        = r.get("grade", "-")
        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Low sample warning
    low_trades = [r for r in results if r.get("trades", 0) < 30]
    if low_trades:
        st.warning(
            f"⚠️ {len(low_trades)} parameter set(s) produced <30 trades. "
            "Stability scores are penalised for low sample size."
        )

    # Best params expander
    if results:
        best = results[0]
        with st.expander("📋 Best Parameter Set (JSON)", expanded=False):
            import json
            params = best.get("parameters", {k: best.get(k) for k in
                              ("sl_atr_multiplier", "tp_atr_multiplier", "entry_cooldown_candles")
                              if k in best})
            st.json(params)


def render_optimization_mode_selector() -> str:
    """Renders mode radio and returns selected mode string."""
    st.markdown("##### Optimization Mode")
    mode_label = st.radio(
        "Select mode",
        options=["⚡ Quick Scan (15–45 sec)", "🔬 Full Validation (2–5 min)"],
        horizontal=True,
        label_visibility="collapsed",
    )
    return "quick_scan" if "Quick" in mode_label else "full_validate"


def render_optimization_summary(results: list, strategy_name: str, mode: str) -> None:
    """Renders a compact text summary of the optimization run."""
    if not results:
        return
    best = results[0]
    pf_key = "profit_factor" if "profit_factor" in best else "val_profit_factor"
    st.success(
        f"✅ **{strategy_name}** optimization complete ({mode.replace('_', ' ').title()}). "
        f"Best: PF {best.get(pf_key, best.get('profit_factor', 0)):.2f} | "
        f"DD {best.get('max_drawdown_pct', best.get('val_metrics', {}).get('max_drawdown_pct', 0)):.1f}% | "
        f"{len(results)} variants tested."
    )
