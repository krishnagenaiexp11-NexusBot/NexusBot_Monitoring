import numpy as np
import pandas as pd


def calculate_metrics(trades: list[dict], equity_curve: pd.DataFrame, starting_balance: float) -> dict:
    closed = [trade for trade in trades if trade.get("status") == "CLOSED"]
    profits = np.array([trade.get("profit", 0.0) for trade in closed], dtype=float)
    wins = profits[profits > 0]
    losses = profits[profits < 0]
    gross_profit = wins.sum()
    gross_loss = abs(losses.sum())

    returns = equity_curve["equity"].pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    sharpe = 0.0 if returns.std() == 0 or returns.empty else float((returns.mean() / returns.std()) * np.sqrt(252))
    running_peak = equity_curve["equity"].cummax()
    drawdown = equity_curve["equity"] - running_peak
    drawdown_pct = (drawdown / running_peak.replace(0, np.nan)) * 100
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0
    max_drawdown_pct = float(drawdown_pct.min()) if not drawdown_pct.dropna().empty else 0.0

    streak_wins = streak_losses = best_wins = worst_losses = 0
    for profit in profits:
        if profit > 0:
            streak_wins += 1
            streak_losses = 0
        elif profit < 0:
            streak_losses += 1
            streak_wins = 0
        best_wins = max(best_wins, streak_wins)
        worst_losses = max(worst_losses, streak_losses)

    rr_values = []
    for trade in closed:
        risk = abs(trade["entry_price"] - trade["initial_sl"])
        reward = abs(trade["exit_price"] - trade["entry_price"])
        if risk > 0:
            rr_values.append(reward / risk)

    net_profit = float(profits.sum()) if len(profits) else 0.0

    # Advanced Diagnostics:
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    realized_rr = avg_win / abs(avg_loss) if avg_loss != 0.0 else 0.0

    # Exit Breakdown:
    exit_breakdown = {}
    for trade in closed:
        reason = trade.get("exit_reason", "unknown")
        exit_breakdown[reason] = exit_breakdown.get(reason, 0) + 1

    # Session Grouping:
    def get_session_name(timestamp) -> str:
        try:
            dt = pd.to_datetime(timestamp)
            hour = dt.hour
            if 8 <= hour < 13:
                return "London"
            elif 13 <= hour < 17:
                return "NY Overlap"
            elif 17 <= hour < 22:
                return "NY"
            else:
                return "Asian/Rollover"
        except Exception:
            return "Unknown"

    profit_by_session = {"London": 0.0, "NY Overlap": 0.0, "NY": 0.0, "Asian/Rollover": 0.0}
    for trade in closed:
        sess = get_session_name(trade.get("entry_time"))
        profit_by_session[sess] = profit_by_session.get(sess, 0.0) + trade.get("profit", 0.0)

    # Strategy Grouping:
    profit_by_strategy = {}
    for trade in closed:
        strat = trade.get("strategy", "Unknown")
        profit_by_strategy[strat] = profit_by_strategy.get(strat, 0.0) + trade.get("profit", 0.0)

    # Duration Analytics:
    durations = []
    win_durations = []
    loss_durations = []
    for trade in closed:
        try:
            entry_dt = pd.to_datetime(trade["entry_time"])
            exit_dt = pd.to_datetime(trade["exit_time"])
            duration_sec = (exit_dt - entry_dt).total_seconds()
            durations.append(duration_sec)
            if trade.get("profit", 0.0) > 0:
                win_durations.append(duration_sec)
            elif trade.get("profit", 0.0) < 0:
                loss_durations.append(duration_sec)
        except Exception:
            pass

    avg_duration_min = float(np.mean(durations) / 60.0) if durations else 0.0
    avg_win_duration_min = float(np.mean(win_durations) / 60.0) if win_durations else 0.0
    avg_loss_duration_min = float(np.mean(loss_durations) / 60.0) if loss_durations else 0.0

    # Heatmap Data:
    heatmap_data = []
    for trade in closed:
        try:
            dt = pd.to_datetime(trade["entry_time"])
            heatmap_data.append({
                "hour": int(dt.hour),
                "day_of_week": dt.strftime("%A"),
                "profit": float(trade.get("profit", 0.0))
            })
        except Exception:
            pass

    return {
        "trades": len(closed),
        "win_rate": float(len(wins) / len(closed) * 100) if closed else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss else float(gross_profit > 0),
        "roi": float(net_profit / starting_balance * 100) if starting_balance else 0.0,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "max_drawdown_abs": abs(max_drawdown),
        "max_drawdown_pct": max_drawdown_pct,
        "consecutive_wins": best_wins,
        "consecutive_losses": worst_losses,
        "longest_losing_streak": worst_losses,
        "average_rr": float(np.mean(rr_values)) if rr_values else 0.0,
        "net_profit": net_profit,
        "average_win": avg_win,
        "average_loss": avg_loss,
        "realized_rr": realized_rr,
        "exit_breakdown": exit_breakdown,
        "profit_by_session": profit_by_session,
        "profit_by_strategy": profit_by_strategy,
        "avg_duration_min": avg_duration_min,
        "avg_win_duration_min": avg_win_duration_min,
        "avg_loss_duration_min": avg_loss_duration_min,
        "heatmap_data": heatmap_data,
    }


def monthly_returns(equity_curve: pd.DataFrame) -> pd.DataFrame:
    if equity_curve.empty:
        return pd.DataFrame(columns=["month", "return"])
    data = equity_curve.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    monthly = data.set_index("timestamp")["equity"].resample("ME").last().pct_change().fillna(0) * 100
    return monthly.reset_index().rename(columns={"timestamp": "month", "equity": "return"})
