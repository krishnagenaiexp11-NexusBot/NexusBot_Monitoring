"""
optimizer/optimizer_engine.py
V2 Optimizer Engine.

Operates in two modes:
  - QUICK SCAN   : Fast local parameter sweep, no walk-forward, stability score only.
                   Target runtime: 15-45 seconds.
  - FULL VALIDATE: Walk-forward validation + deployment scoring.
                   Target runtime: 2-5 minutes.

Only optimizes the tournament-recommended (winning) strategy.
"""
import hashlib
import json
import random
import time
import pandas as pd

from optimizer.walkforward import split_walkforward
from optimizer.deployment_score import calculate_deployment_score, calculate_grade
from optimizer.parameter_space import get_space_for_strategy
from engine.strategy_registry import get_strategy_by_name

from engine.backtest_engine import BacktestEngine
from engine.event_bus import EventBus

try:
    from ai.strategy_analyzer import calculate_stability_score, calculate_equity_r2
except Exception:
    def calculate_stability_score(metrics, equity_curve): return 50.0
    def calculate_equity_r2(equity_curve): return 0.5


class OptimizerEngine:
    """
    Runs parameter sweeps for a single strategy in Quick Scan or Full Validate mode.
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def quick_scan(
        self,
        strategy_name:    str,
        df:               pd.DataFrame,
        base_params:      dict | None = None,
        starting_balance: float = 10_000.0,
        max_combinations: int = 12,
        progress_callback = None,
        cancel_flag       = None,
    ) -> list:
        """
        Runs a fast parameter sweep (no walk-forward).
        Returns list of result dicts sorted by stability_score descending.
        """
        strategy_obj = get_strategy_by_name(strategy_name)
        defaults     = strategy_obj.get_default_parameters()
        params       = {**defaults, **(base_params or {})}
        space        = get_space_for_strategy(strategy_name)
        variants     = self._generate_variants(params, space, max_combinations)

        results = []
        for idx, variant_params in enumerate(variants):
            if cancel_flag and cancel_flag():
                break
            if progress_callback:
                progress_callback(idx + 1, len(variants), "Quick Scan")

            try:
                result = self._run_single(strategy_obj, variant_params, df, starting_balance)
                if result:
                    results.append(result)
            except Exception:
                continue

        results.sort(key=lambda x: x.get("stability_score", 0), reverse=True)
        for rank, r in enumerate(results, 1):
            r["rank"] = rank
        return results

    def full_validate(
        self,
        strategy_name:    str,
        df:               pd.DataFrame,
        base_params:      dict | None = None,
        starting_balance: float = 10_000.0,
        max_combinations: int = 24,
        train_ratio:      float = 0.70,
        progress_callback = None,
        cancel_flag       = None,
    ) -> list:
        """
        Runs walk-forward validation with deployment scoring.
        Returns list of result dicts sorted by deployment_score descending.
        """
        strategy_obj = get_strategy_by_name(strategy_name)
        defaults     = strategy_obj.get_default_parameters()
        params       = {**defaults, **(base_params or {})}
        space        = get_space_for_strategy(strategy_name)
        variants     = self._generate_variants(params, space, max_combinations)

        train_df, val_df = split_walkforward(df, train_ratio=train_ratio)

        if len(train_df) < 50 or len(val_df) < 30:
            return []

        results = []
        for idx, variant_params in enumerate(variants):
            if cancel_flag and cancel_flag():
                break
            if progress_callback:
                progress_callback(idx + 1, len(variants), "Full Validate")

            try:
                train_res = self._run_single(strategy_obj, variant_params, train_df, starting_balance)
                val_res   = self._run_single(strategy_obj, variant_params, val_df, starting_balance)

                if not train_res or not val_res:
                    continue

                dep_score, grade, warnings = calculate_deployment_score(
                    train_metrics  = train_res["metrics"],
                    val_metrics    = val_res["metrics"],
                    train_stability= train_res.get("stability_score", 50.0),
                    val_stability  = val_res.get("stability_score",   50.0),
                    train_r2       = train_res.get("equity_r2",       0.5),
                    val_r2         = val_res.get("equity_r2",         0.5),
                )

                results.append({
                    "parameters":       variant_params,
                    "deployment_score": dep_score,
                    "grade":            grade,
                    "warnings":         warnings,
                    "train_metrics":    train_res["metrics"],
                    "val_metrics":      val_res["metrics"],
                    "stability_score":  val_res.get("stability_score", 50.0),
                    "equity_r2":        val_res.get("equity_r2", 0.5),
                    "mode":             "full_validate",
                })
            except Exception:
                continue

        results.sort(key=lambda x: x.get("deployment_score", 0), reverse=True)
        for rank, r in enumerate(results, 1):
            r["rank"] = rank
        return results

    # ── Internals ─────────────────────────────────────────────────────────────

    def _run_single(self, strategy_obj, params: dict, df: pd.DataFrame, balance: float) -> dict | None:
        """Runs BacktestEngine for a single parameter variant."""
        try:
            inner_strategy = strategy_obj._create_parameterised_instance(params)
            bus    = EventBus()
            engine = BacktestEngine(inner_strategy, starting_balance=balance, event_bus=bus)
            result = engine.run(df)
            metrics = result.get("metrics", {})
            equity  = result.get("equity_curve")

            stability = calculate_stability_score(metrics, equity) if equity is not None else 50.0
            r2        = calculate_equity_r2(equity)                if equity is not None else 0.5

            return {
                "parameters":      params,
                "metrics":         metrics,
                "stability_score": stability,
                "equity_r2":       r2,
                "net_profit":      metrics.get("net_profit",      0.0),
                "profit_factor":   metrics.get("profit_factor",   0.0),
                "win_rate":        metrics.get("win_rate",        0.0),
                "max_drawdown_pct":metrics.get("max_drawdown_pct",0.0),
                "trades":          metrics.get("trades",          0),
                "mode":            "quick_scan",
                **{k: params.get(k) for k in ("sl_atr_multiplier", "tp_atr_multiplier", "entry_cooldown_candles")
                   if k in params},
            }
        except Exception:
            return None

    def _generate_variants(self, base_params: dict, space: dict, max_combinations: int) -> list:
        """
        Generates up to `max_combinations` parameter dicts using deterministic
        step-walk + random sampling from the search space.
        """
        variants = [base_params.copy()]
        param_keys = list(space.keys())

        # Step-walk: shift each parameter one step up / down
        for key in param_keys:
            if key not in base_params:
                continue
            current = base_params[key]
            space_list = space[key]
            if current not in space_list:
                closest_idx = min(range(len(space_list)), key=lambda i: abs(space_list[i] - current))
            else:
                closest_idx = space_list.index(current)
            for delta in (-1, +1):
                new_idx = closest_idx + delta
                if 0 <= new_idx < len(space_list):
                    new_params = base_params.copy()
                    new_params[key] = space_list[new_idx]
                    if new_params not in variants:
                        variants.append(new_params)
            if len(variants) >= max_combinations:
                break

        # Fill remaining with random sampling (deterministic seed from base_params)
        seed = int(hashlib.sha256(json.dumps(base_params, sort_keys=True).encode()).hexdigest(), 16) % (2**32)
        rng  = random.Random(seed)
        attempts = 0
        while len(variants) < max_combinations and attempts < 500:
            attempts += 1
            new_params = base_params.copy()
            keys_to_mutate = rng.sample(param_keys, min(rng.randint(1, 2), len(param_keys)))
            for key in keys_to_mutate:
                if key in base_params:
                    new_params[key] = rng.choice(space[key])
            if new_params not in variants:
                variants.append(new_params)

        return variants[:max_combinations]
