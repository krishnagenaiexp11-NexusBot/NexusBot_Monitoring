import pandas as pd
import plotly.graph_objects as go

from utils.metrics import monthly_returns


def equity_curve_chart(equity_curve: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity_curve["timestamp"], y=equity_curve["equity"], mode="lines", name="Equity"))
    fig.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=20), title="Equity Curve")
    return fig


def drawdown_chart(equity_curve: pd.DataFrame):
    dd = equity_curve["equity"] - equity_curve["equity"].cummax()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity_curve["timestamp"], y=dd, mode="lines", fill="tozeroy", name="Drawdown"))
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20), title="Drawdown")
    return fig


def trade_marker_chart(df: pd.DataFrame, trades: list[dict]):
    fig = go.Figure(data=[go.Candlestick(x=df["timestamp"], open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="Price")])
    for trade in trades:
        color = "#16a34a" if trade["direction"] == "BUY" else "#dc2626"
        fig.add_trace(go.Scatter(x=[trade["entry_time"]], y=[trade["entry_price"]], mode="markers", marker=dict(color=color, size=9), name=f"{trade['direction']} entry"))
        if trade.get("exit_time"):
            fig.add_trace(go.Scatter(x=[trade["exit_time"]], y=[trade["exit_price"]], mode="markers", marker=dict(color="#111827", size=8, symbol="x"), name="Exit"))
    fig.update_layout(height=440, margin=dict(l=20, r=20, t=30, b=20), title="Trade Markers", xaxis_rangeslider_visible=False)
    return fig


def monthly_returns_chart(equity_curve: pd.DataFrame):
    monthly = monthly_returns(equity_curve)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=monthly["month"], y=monthly["return"], name="Monthly return"))
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20), title="Monthly Returns")
    return fig
