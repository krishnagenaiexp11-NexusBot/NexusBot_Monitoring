"""
engine/deployment_candidate.py
Deployment Candidate Engine — generates clean deployment profiles
from optimization results.
"""
import datetime
from research.deployment_score import calculate_grade


def generate_candidate(
    symbol:        str,
    strategy_name: str,
    opt_result:    dict,
) -> dict:
    """
    Converts an optimizer result into a clean deployment candidate profile.

    Args:
        symbol        : Trading symbol, e.g. "XAUUSD"
        strategy_name : Name of the optimized strategy
        opt_result    : Dict from OptimizerEngine containing best variant data

    Returns:
        Clean deployment candidate dict ready for storage / export.
    """
    if not opt_result:
        raise ValueError(
            "No optimization candidates available for deployment profile generation."
        )

    params         = opt_result.get("parameters",       {})
    dep_score      = float(opt_result.get("deployment_score", 0.0))
    val_metrics    = opt_result.get("val_metrics",       {})
    train_metrics  = opt_result.get("train_metrics",     {})
    stability      = float(opt_result.get("stability_score",  0.0))
    warnings       = opt_result.get("warnings",          [])
    grade          = opt_result.get("grade") or calculate_grade(dep_score)

    candidate = {
        "symbol":            symbol,
        "strategy":          strategy_name,
        "deployment_score":  round(dep_score, 2),
        "grade":             grade,
        "parameters": {
            "sl_atr":  params.get("sl_atr_multiplier",      1.8),
            "tp_atr":  params.get("tp_atr_multiplier",      3.5),
            "cooldown": params.get("entry_cooldown_candles", 6),
            **{k: v for k, v in params.items()
               if k not in ("sl_atr_multiplier", "tp_atr_multiplier", "entry_cooldown_candles")},
        },
        "full_parameters":   params,
        "validation_metrics": {
            "profit_factor":     round(float(val_metrics.get("profit_factor",   0.0)), 3),
            "win_rate_pct":      round(float(val_metrics.get("win_rate",        0.0)), 2),
            "max_drawdown_pct":  round(float(val_metrics.get("max_drawdown_pct",0.0)), 2),
            "trades":            int(val_metrics.get("trades",                  0)),
        },
        "train_metrics": {
            "profit_factor":     round(float(train_metrics.get("profit_factor", 0.0)), 3),
            "win_rate_pct":      round(float(train_metrics.get("win_rate",      0.0)), 2),
            "trades":            int(train_metrics.get("trades",                0)),
        },
        "stability_score": round(stability, 2),
        "warnings":        warnings,
        "generated_at":    datetime.datetime.utcnow().isoformat() + "Z",
        "ready_for_deployment": dep_score >= 60.0 and len(warnings) == 0,
    }
    return candidate


def candidate_summary_line(candidate: dict) -> str:
    """Returns a single-line human-readable summary of a deployment candidate."""
    return (
        f"{candidate['strategy']} | {candidate['symbol']} | "
        f"Score: {candidate['deployment_score']:.1f} ({candidate['grade']}) | "
        f"Val PF: {candidate['validation_metrics']['profit_factor']:.2f} | "
        f"Val DD: {candidate['validation_metrics']['max_drawdown_pct']:.1f}%"
    )
