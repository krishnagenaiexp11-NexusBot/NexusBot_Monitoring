import json
import math
import numpy as np
import pandas as pd
from engine.backtest_engine import BacktestEngine
from strategies.spike_catcher import SpikeCatcher


def calculate_equity_r2(equity_curve: pd.DataFrame) -> float:
    try:
        y = equity_curve["equity"].values
        if len(y) < 3:
            return 1.0
        x = np.arange(len(y))
        slope, intercept = np.polyfit(x, y, 1)
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        return float(max(0.0, r2))
    except Exception:
        return 0.0


def calculate_stability_score(metrics: dict, equity_curve: pd.DataFrame) -> float:
    r2 = calculate_equity_r2(equity_curve)
    pf = metrics.get("profit_factor", 0.0)
    wr = metrics.get("win_rate", 0.0) / 100.0
    dd = metrics.get("max_drawdown_pct", 0.0)
    streak = metrics.get("longest_losing_streak", 0)
    trades = metrics.get("trades", 0)

    if trades == 0:
        return 0.0

    # Win Rate contribution (max 25 pts)
    wr_points = wr * 25.0

    # Profit Factor contribution (max 25 pts)
    if pf >= 2.0:
        pf_points = 25.0
    elif pf >= 1.0:
        pf_points = (pf - 1.0) * 25.0
    else:
        pf_points = 0.0

    # Drawdown penalty (max 20 pts, decreases by drawdown %)
    dd_points = max(0.0, 20.0 - (dd * 0.8))

    # Consecutive losses penalty (max 10 pts)
    streak_points = max(0.0, 10.0 - (streak * 1.5))

    # Smoothness contribution (max 20 pts)
    r2_points = r2 * 20.0

    score = wr_points + pf_points + dd_points + streak_points + r2_points

    # Penalize low sample size (< 30 trades) to avoid statistical noise
    if trades < 30:
        score *= (trades / 30.0)

    return float(max(0.0, min(score, 100.0)))


def calculate_health_score(metrics: dict) -> str:
    pf = metrics.get("profit_factor", 0.0)
    wr = metrics.get("win_rate", 0.0)
    dd = metrics.get("max_drawdown_pct", 0.0)
    trades = metrics.get("trades", 0)

    if trades == 0:
        return "Unsafe"

    if pf >= 1.8 and dd < 10.0 and wr >= 55.0 and trades >= 30:
        return "A+"
    elif pf >= 1.4 and dd < 15.0 and wr >= 50.0:
        return "A"
    elif pf >= 1.0 and dd < 20.0:
        return "B"
    elif pf >= 0.8 and dd < 30.0:
        return "C"
    else:
        return "Unsafe"


def check_overfitting_warnings(metrics: dict, stability_score: float) -> list[str]:
    warnings = []
    wr = metrics.get("win_rate", 0.0)
    pf = metrics.get("profit_factor", 0.0)
    trades = metrics.get("trades", 0)
    dd = metrics.get("max_drawdown_pct", 0.0)

    if trades > 0:
        if wr > 85.0:
            warnings.append("⚠️ HIGH WIN RATE WARNING: Win rate > 85% is typically unrealistic and indicates overfitting.")
        if pf > 4.5:
            warnings.append("⚠️ SUSPICIOUS PROFIT FACTOR: Profit factor > 4.5 is highly indicative of curve-fitting.")
        if trades < 15:
            warnings.append("⚠️ LOW SAMPLE SIZE: Less than 15 trades is too small to verify strategy robustness.")
        if dd < 1.0 and wr > 70.0 and trades > 20:
            warnings.append("⚠️ DUBIOUSLY LOW DRAWDOWN: Drawdown < 1% suggests over-optimization to noise.")
        if stability_score < 40.0 and metrics.get("net_profit", 0.0) > 0:
            warnings.append("⚠️ VOLATILE EQUITY: Smoothness is low. Profit relies heavily on single outlier trades.")
    else:
        warnings.append("⚠️ NO TRADES GENERATED: Unable to analyze strategy consistency.")
        
    return warnings


def calculate_trade_attribution(trades: list[dict]) -> dict:
    closed = [t for t in trades if t.get("status") == "CLOSED"]
    if not closed:
        return {
            "winning_stats": {}, "losing_stats": {},
            "best_session": "None", "worst_session": "None",
            "best_duration": 0.0, "worst_duration": 0.0,
            "trending_pct": 0.0, "ranging_pct": 0.0, "volatile_pct": 0.0, "low_vol_pct": 0.0,
            "correlations": {}, "outliers_count": 0
        }

    wins = [t for t in closed if t.get("profit", 0.0) > 0]
    losses = [t for t in closed if t.get("profit", 0.0) < 0]

    def get_avg_stats(trade_list):
        if not trade_list:
            return {}
        keys = ["rsi", "atr", "volume_ratio", "momentum", "signal_strength", "trade_duration_minutes"]
        return {k: float(sum(t.get(k, 0.0) or 0.0 for t in trade_list) / len(trade_list)) for k in keys}

    winning_stats = get_avg_stats(wins)
    losing_stats = get_avg_stats(losses)

    # Session performance
    session_profits = {}
    for t in closed:
        sess = t.get("session", "UNKNOWN")
        session_profits[sess] = session_profits.get(sess, 0.0) + t.get("profit", 0.0)
    best_session = max(session_profits, key=session_profits.get) if session_profits else "None"
    worst_session = min(session_profits, key=session_profits.get) if session_profits else "None"

    # Durations
    best_duration = float(np.mean([t.get("trade_duration_minutes", 0.0) or 0.0 for t in wins])) if wins else 0.0
    worst_duration = float(np.mean([t.get("trade_duration_minutes", 0.0) or 0.0 for t in losses])) if losses else 0.0

    # Regime breakdown
    regimes = [t.get("market_regime", "RANGING") for t in closed]
    total_regimes = len(regimes)
    trending_pct = float(regimes.count("TRENDING") / total_regimes * 100) if total_regimes else 0.0
    ranging_pct = float(regimes.count("RANGING") / total_regimes * 100) if total_regimes else 0.0
    volatile_pct = float(regimes.count("VOLATILE") / total_regimes * 100) if total_regimes else 0.0
    low_vol_pct = float(regimes.count("LOW_VOLATILITY") / total_regimes * 100) if total_regimes else 0.0

    # Outliers count
    outliers_count = sum(1 for t in closed if t.get("outlier_flag", 0) == 1)

    # correlations
    correlations = {}
    if len(closed) >= 3:
        indicators = ["rsi", "atr", "volume_ratio", "momentum", "signal_strength"]
        profits = [t.get("profit", 0.0) for t in closed]
        for ind in indicators:
            vals = [t.get(ind, 0.0) or 0.0 for t in closed]
            if np.std(vals) > 0 and np.std(profits) > 0:
                corr = np.corrcoef(vals, profits)[0, 1]
                correlations[ind] = float(corr) if not np.isnan(corr) else 0.0
            else:
                correlations[ind] = 0.0

    return {
        "winning_stats": winning_stats,
        "losing_stats": losing_stats,
        "best_session": best_session,
        "worst_session": worst_session,
        "best_duration": best_duration,
        "worst_duration": worst_duration,
        "trending_pct": trending_pct,
        "ranging_pct": ranging_pct,
        "volatile_pct": volatile_pct,
        "low_vol_pct": low_vol_pct,
        "correlations": correlations,
        "outliers_count": outliers_count,
        "profit_by_session": session_profits
    }


def run_spike_catcher_variants(df: pd.DataFrame, starting_balance: float, progress_bar=None, cancel_flag=None) -> list[dict]:
    variants = [
        {
            "name": "Spike Catcher Base",
            "params": {"use_adx_filter": False, "session_filter_enabled": False, "max_spread_atr_ratio": 999.0},
            "features": "Raw Spike Catcher breakout logic with filters bypassed."
        },
        {
            "name": "Spike Catcher + ADX Filter",
            "params": {"use_adx_filter": True, "adx_threshold": 20.0},
            "features": "Filters out entries when ADX <= 20 to avoid flat chop ranges."
        },
        {
            "name": "Spike Catcher + HTF Trend",
            "params": {"htf_confirmation_enabled": True, "htf_timeframe": "15Min", "htf_ema_period": 50},
            "features": "Validates direction using M15 higher timeframe trend alignment."
        },
        {
            "name": "Spike Catcher + Strong RSI",
            "params": {"rsi_buy_min": 60, "rsi_sell_max": 40},
            "features": "Restricts entries to high-momentum candles (RSI > 60 BUY / < 40 SELL)."
        },
        {
            "name": "Spike Catcher Conservative",
            "params": {"entry_cooldown_candles": 10, "sl_atr_multiplier": 2.0, "tp_atr_multiplier": 4.0},
            "features": "Applies a wide 10-candle entry cooldown and wider stops."
        },
        {
            "name": "Spike Catcher High Volatility",
            "params": {"atr_expansion_mult": 2.0, "volume_spike_mult": 3.0},
            "features": "Triggers only on extreme volume and volatility expansions."
        }
    ]

    results = []
    total = len(variants)
    for idx, var in enumerate(variants):
        if cancel_flag and cancel_flag():
            break

        if progress_bar:
            progress_bar.progress((idx + 1) / total, text=f"Running Variant {idx+1}/{total}: {var['name']}...")

        params = {**SpikeCatcher.default_params, **var["params"]}
        strategy = SpikeCatcher(params)
        engine = BacktestEngine(strategy, starting_balance=starting_balance)
        res = engine.run(df)

        stability = calculate_stability_score(res["metrics"], res["equity_curve"])
        results.append({
            "variant_name": var["name"],
            "features": var["features"],
            "parameters": var["params"],
            "metrics": res["metrics"],
            "stability_score": stability,
            "net_profit": res["metrics"]["net_profit"],
            "max_drawdown_pct": res["metrics"]["max_drawdown_pct"],
            "profit_factor": res["metrics"]["profit_factor"],
            "win_rate": res["metrics"]["win_rate"],
            "trades": res["metrics"]["trades"],
        })

    results = sorted(results, key=lambda x: x["stability_score"], reverse=True)
    for rank, res_item in enumerate(results, 1):
        res_item["ranking"] = rank

    return results


def run_parameter_sweep(df: pd.DataFrame, strategy_cls, base_params: dict, starting_balance: float, progress_bar=None, cancel_flag=None, max_combinations: int = 12) -> list[dict]:
    import itertools
    import time

    # Generate 12 combinations
    sl_values = [1.5, 2.0, 2.8]
    tp_values = [2.5, 4.0]
    cooldown_values = [3, 10]

    combinations = list(itertools.product(sl_values, tp_values, cooldown_values))[:max_combinations]
    results = []
    total = len(combinations)
    start_time = time.time()

    for idx, (sl, tp, cd) in enumerate(combinations):
        if cancel_flag and cancel_flag():
            break

        elapsed = time.time() - start_time
        avg_time = elapsed / idx if idx > 0 else 0.0
        est_remaining = avg_time * (total - idx) if idx > 0 else 0.0

        if progress_bar:
            time_str = f"{int(est_remaining)}s remaining" if idx > 0 else "estimating..."
            progress_bar.progress((idx + 1) / total, text=f"Running Sweep {idx+1}/{total} (SL={sl}, TP={tp}, CD={cd}). Est. {time_str}")

        run_params = {
            **base_params,
            "sl_atr_multiplier": sl,
            "tp_atr_multiplier": tp,
            "entry_cooldown_candles": cd
        }

        strategy = strategy_cls(run_params)
        engine = BacktestEngine(strategy, starting_balance=starting_balance)
        res = engine.run(df)
        metrics = res["metrics"]

        stability = calculate_stability_score(metrics, res["equity_curve"])
        r2 = calculate_equity_r2(res["equity_curve"])

        results.append({
            "parameters": run_params,
            "sl_atr_multiplier": sl,
            "tp_atr_multiplier": tp,
            "entry_cooldown_candles": cd,
            "metrics": metrics,
            "stability_score": stability,
            "equity_curve_r2": r2,
            "net_profit": metrics["net_profit"],
            "max_drawdown_pct": metrics["max_drawdown_pct"],
            "profit_factor": metrics["profit_factor"],
            "win_rate": metrics["win_rate"],
            "trades": metrics["trades"]
        })

    return results


def validate_ai_response(raw_text: str) -> dict:
    import re
    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()

    try:
        data = json.loads(cleaned)
    except Exception as e:
        raise ValueError(f"Invalid JSON format in LLM response: {str(e)}")

    required_keys = ["confidence_score", "why_won_reasons", "why_lost_reasons", "summary", "strengths", "weaknesses", "recommendations"]
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise KeyError(f"Missing required JSON keys in LLM output: {', '.join(missing)}")

    for k in ["why_won_reasons", "why_lost_reasons", "strengths", "weaknesses", "recommendations"]:
        if not isinstance(data.get(k), list):
            data[k] = [str(data[k])] if data.get(k) is not None else []

    # Normalize bullet points count to exactly 3 for NexusBot signature intelligence
    if len(data["why_won_reasons"]) != 3:
        data["why_won_reasons"] = (data["why_won_reasons"] + [
            "EMA alignment capturing macro direction",
            "Strong breakout volume confluence",
            "ATR spread checks protecting margins"
        ])[:3]

    if len(data["why_lost_reasons"]) != 3:
        data["why_lost_reasons"] = (data["why_lost_reasons"] + [
            "Asian session chop triggers stop losses",
            "Exiting too early on tight breakeven trail",
            "Low ATR conditions failing to sustain momentum"
        ])[:3]

    return data
