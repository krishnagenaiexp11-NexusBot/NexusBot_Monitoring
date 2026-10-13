"""
ui/strategy_panels.py
Strategy Tournament results UI panels.
"""
import streamlit as st
import pandas as pd


def render_tournament_panel(results: list, regime: dict | None = None) -> None:
    """
    Renders the Strategy Tournament ranking panel.

    Args:
        results : Output from StrategyTournamentEngine.rank() after strip_internal_fields()
        regime  : Current regime dict for contextual labeling [optional]
    """
    if not results:
        st.info("Run the Strategy Tournament to see results.")
        return

    regime_label = (regime or {}).get("regime", "")

    # ── Ranking table ─────────────────────────────────────────────────────────
    rows = []
    for item in results:
        score   = item["market_fit_score"]
        support = "✅" if item.get("supported") else "–"
        rows.append({
            "Rank":             item["rank"],
            "Strategy":         item["strategy"],
            "Market Fit Score": score,
            "Regime Match":     support,
            "Supported Regimes": ", ".join(item.get("supported_regimes", [])),
        })

    df_results = pd.DataFrame(rows)
    st.dataframe(df_results, use_container_width=True, hide_index=True)

    # ── Score bar chart ───────────────────────────────────────────────────────
    with st.expander("Score Distribution Chart", expanded=False):
        try:
            import plotly.graph_objects as go
            names  = [r["strategy"]         for r in results]
            scores = [r["market_fit_score"] for r in results]
            colors = ["#22c55e" if r.get("supported") else "#94a3b8" for r in results]

            fig = go.Figure(go.Bar(
                x=scores, y=names,
                orientation="h",
                marker_color=colors,
                text=[f"{s:.1f}" for s in scores],
                textposition="outside",
            ))
            fig.update_layout(
                xaxis=dict(range=[0, 105], title="Market Fit Score"),
                yaxis=dict(autorange="reversed"),
                height=260,
                margin=dict(l=10, r=10, t=20, b=10),
                plot_bgcolor="#0f172a",
                paper_bgcolor="#0f172a",
                font=dict(color="#e2e8f0"),
            )
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.caption("Install plotly for score chart.")

    # ── Recommended callout ───────────────────────────────────────────────────
    if results:
        best = results[0]
        score = best["market_fit_score"]
        color = "green" if best.get("supported") else "orange"
        st.success(
            f"🏆 **Recommended: {best['strategy']}** — "
            f"Market Fit Score: **{score:.1f}** "
            + (f"| ✅ Supported in {regime_label}" if best.get("supported") else "| ⚠️ Not ideal regime")
        )

    with st.expander("About regime fit scores", expanded=False):
        st.markdown("""
        **How scores are calculated:**
        - Each strategy scores itself against the detected market regime.
        - Scores reflect expected suitability (0 = poor fit, 100 = perfect fit).
        - ✅ **Regime Match** = current regime is in the strategy's supported list.
        - Alignment bonus from M15 context can shift scores by up to ±8 points.
        """)


def render_recommended_strategy_card(strategy_name: str, score: float) -> None:
    """Renders a compact card highlighting the recommended strategy."""
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#1e3a5f,#0f172a);
                    border:1px solid #22c55e;border-radius:12px;padding:16px 20px;
                    margin-bottom:12px;">
            <div style="color:#94a3b8;font-size:0.8rem;text-transform:uppercase;
                        letter-spacing:1px;">Recommended Strategy</div>
            <div style="color:#22c55e;font-size:1.6rem;font-weight:800;">{strategy_name}</div>
            <div style="color:#e2e8f0;font-size:0.95rem;">
                Market Fit Score: <strong style="color:#f59e0b;">{score:.1f}/100</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
