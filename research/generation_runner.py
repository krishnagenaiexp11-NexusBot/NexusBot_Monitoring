import time
import pandas as pd
from engine.backtest_engine import BacktestEngine
from ai.strategy_analyzer import calculate_stability_score, calculate_equity_r2
from research.deployment_score import calculate_deployment_score
from research.orchestration_models import VariantResult

def run_generation_batch(
    variants: list[dict],
    strategy_cls,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    starting_balance: float,
    progress_callback = None,
    cancel_flag = None
) -> list[VariantResult]:
    results = []
    total = len(variants)
    start_time = time.time()

    for idx, run_params in enumerate(variants):
        if cancel_flag and cancel_flag():
            break

        # Calculate estimated time remaining
        elapsed = time.time() - start_time
        avg_time = elapsed / idx if idx > 0 else 0.0
        est_remaining = avg_time * (total - idx) if idx > 0 else 0.0
        
        variant_name = f"Variant_{idx + 1}"
        if progress_callback:
            progress_callback(idx + 1, total, est_remaining, variant_name)

        try:
            # 1. Backtest on Train data
            train_strategy = strategy_cls(run_params)
            train_engine = BacktestEngine(train_strategy, starting_balance=starting_balance)
            train_res = train_engine.run(train_df)
            train_metrics = train_res["metrics"]
            train_stability = calculate_stability_score(train_metrics, train_res["equity_curve"])
            train_r2 = calculate_equity_r2(train_res["equity_curve"])

            # 2. Backtest on Validation data
            val_strategy = strategy_cls(run_params)
            val_engine = BacktestEngine(val_strategy, starting_balance=starting_balance)
            val_res = val_engine.run(val_df)
            val_metrics = val_res["metrics"]
            val_stability = calculate_stability_score(val_metrics, val_res["equity_curve"])
            val_r2 = calculate_equity_r2(val_res["equity_curve"])

            # 3. Calculate Deployment Readiness Score
            score, grade, warnings = calculate_deployment_score(
                train_metrics=train_metrics,
                val_metrics=val_metrics,
                train_stability=train_stability,
                val_stability=val_stability,
                train_r2=train_r2,
                val_r2=val_r2
            )

            # Store results
            result_obj = VariantResult(
                variant_name=variant_name,
                parameters=run_params,
                train_metrics=train_metrics,
                val_metrics=val_metrics,
                stability_score=train_stability,
                validation_stability_score=val_stability,
                deployment_score=score,
                warnings=warnings
            )
            results.append(result_obj)

        except Exception as e:
            # Safely capture failures without breaking the loop
            print(f"Error backtesting variant {variant_name}: {e}")
            
    # Rank results by deployment score descending
    results = sorted(results, key=lambda x: x.deployment_score, reverse=True)
    for rank, r in enumerate(results, 1):
        r.ranking = rank

    return results
