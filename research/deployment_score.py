def calculate_grade(score: float) -> str:
    try:
        import math
        import pandas as pd
        if score is None or (isinstance(score, float) and (math.isnan(score) or math.isinf(score))) or pd.isna(score):
            return "UNKNOWN"
        
        score_val = float(score)
        if score_val < 40.0:
            return "UNSAFE"
        elif score_val < 60.0:
            return "EXPERIMENTAL"
        elif score_val < 75.0:
            return "PROMISING"
        elif score_val < 90.0:
            return "ROBUST"
        return "RARE"
    except Exception:
        return "UNKNOWN"


def calculate_deployment_score(
    train_metrics: dict,
    val_metrics: dict,
    train_stability: float,
    val_stability: float,
    train_r2: float,
    val_r2: float
) -> tuple[float, str, list[str]]:
    warnings = []
    
    base_score = (val_stability * 0.6) + (train_stability * 0.4)
    
    val_trades = val_metrics.get("trades", 0)
    train_trades = train_metrics.get("trades", 0)
    
    if val_trades < 15:
        warnings.append("⚠️ SEVERE LOW VALIDATION TRADES: Too few trades to evaluate validation safety.")
        base_score -= 20.0
    elif val_trades < 30:
        warnings.append("⚠️ LOW VALIDATION TRADES: Under 30 trades may produce statistical noise.")
        base_score *= (val_trades / 30.0)

    train_pf = train_metrics.get("profit_factor", 0.0)
    val_pf = val_metrics.get("profit_factor", 0.0)
    train_wr = train_metrics.get("win_rate", 0.0)
    val_wr = val_metrics.get("win_rate", 0.0)
    
    if train_wr > 85.0 or val_wr > 85.0:
        warnings.append("⚠️ HIGH WIN RATE WARNING: Over 85% is typically unrealistic and indicates overfitting.")
        base_score -= 15.0
        
    if train_pf > 4.5:
        warnings.append("⚠️ SUSPICIOUS TRAIN PROFIT FACTOR: Train PF > 4.5 is highly indicative of curve-fitting.")
        base_score -= 20.0
        
    if val_pf < 1.0:
        warnings.append("⚠️ NEGATIVE VALIDATION OUTCOME: Profit factor is unprofitable on validation data.")
        base_score -= 30.0
        
    if train_pf > 0 and val_pf < 0.75 * train_pf:
        warnings.append(f"⚠️ SIGNIFICANT PERFORMANCE DIVERGENCE: Validation PF ({val_pf:.2f}) dropped below 75% of Train PF ({train_pf:.2f}).")
        base_score -= 20.0
        
    val_dd = val_metrics.get("max_drawdown_pct", 0.0)
    if val_dd > 30.0:
        warnings.append(f"⚠️ HIGH DRAWDOWN ON VALIDATION: Drawdown exceeded 30% ({val_dd:.1f}%).")
        base_score -= 25.0
    elif val_dd > 20.0:
        warnings.append(f"⚠️ ELEVATED DRAWDOWN ON VALIDATION: Drawdown exceeded 20% ({val_dd:.1f}%).")
        base_score -= 10.0
        
    if val_r2 < 0.5:
        warnings.append("⚠️ VOLATILE VALIDATION EQUITY: Smoothness is low (R² < 0.5). Profit relies on outlier trades.")
        base_score -= 15.0

    score = float(max(0.0, min(base_score, 100.0)))
    grade = calculate_grade(score)
        
    return score, grade, warnings
