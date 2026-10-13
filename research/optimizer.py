import uuid
import datetime
import json
from storage.database import Database
from research.walkforward import split_walkforward
from research.generation_runner import run_generation_batch
from research.ai_optimizer import AIOptimizer
from research.orchestration_models import GenerationResult

class OptimizationOrchestrator:
    def __init__(self, strategy_cls, api_key: str = "", starting_balance: float = 10000.0):
        self.strategy_cls = strategy_cls
        self.starting_balance = starting_balance
        self.ai_opt = AIOptimizer(api_key)
        self.db = Database()

    def run_orchestration(
        self,
        df,
        dataset_name: str,
        max_generations: int = 5,
        max_variants: int = 12,
        progress_callback = None,
        cancel_flag = None
    ) -> tuple[str, list[GenerationResult]]:
        run_id = f"opt_run_{uuid.uuid4().hex[:8]}"
        
        train_df, val_df = split_walkforward(df, train_ratio=0.7)
        
        from utils.data_loader import get_dataset_fingerprint
        fingerprint_info = get_dataset_fingerprint(df, dataset_name)
        fingerprint_str = fingerprint_info["fingerprint"]
        
        strategy_name = self.strategy_cls.metadata["name"]
        
        try:
            cur = self.db.conn.cursor()
            cur.execute(
                """
                INSERT INTO orchestrator_runs (run_id, strategy, dataset_fingerprint, max_generations, max_variants, started_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, strategy_name, fingerprint_str, max_generations, max_variants, datetime.datetime.now().isoformat())
            )
            self.db.conn.commit()
        except Exception:
            pass

        base_params = self.strategy_cls.default_params
        current_variants = self.ai_opt._local_heuristic_mutate(base_params, max_variants)
        
        generation_results = []
        
        for gen_idx in range(1, max_generations + 1):
            if cancel_flag and cancel_flag():
                break

            def batch_progress_cb(var_idx, total_vars, est_remaining, active_var_name):
                if progress_callback:
                    total_gens_remaining = max_generations - gen_idx + 1
                    scaled_est = est_remaining + (avg_gen_time * (total_gens_remaining - 1) if 'avg_gen_time' in locals() else est_remaining * (total_gens_remaining - 1))
                    progress_callback(gen_idx, max_generations, var_idx, total_vars, scaled_est, active_var_name)

            gen_start_time = datetime.datetime.now()
            
            results = run_generation_batch(
                variants=current_variants,
                strategy_cls=self.strategy_cls,
                train_df=train_df,
                val_df=val_df,
                starting_balance=self.starting_balance,
                progress_callback=batch_progress_cb,
                cancel_flag=cancel_flag
            )
            
            if not results:
                break

            gen_duration = (datetime.datetime.now() - gen_start_time).total_seconds()
            if 'avg_gen_time' not in locals():
                avg_gen_time = gen_duration
            else:
                avg_gen_time = (avg_gen_time + gen_duration) / 2.0

            next_variants, ai_diag = self.ai_opt.generate_next_generation(
                strategy_name=strategy_name,
                generation_index=gen_idx,
                results=results,
                max_variants=max_variants
            )
            
            gen_res = GenerationResult(
                generation_index=gen_idx,
                variants=results,
                ai_diagnostics=ai_diag
            )
            generation_results.append(gen_res)

            try:
                cur = self.db.conn.cursor()
                cur.execute(
                    """
                    INSERT INTO orchestrator_generations (run_id, generation_index, ai_diagnostics, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (run_id, gen_idx, ai_diag, datetime.datetime.now().isoformat())
                )
                
                for r in results:
                    cur.execute(
                        """
                        INSERT INTO orchestrator_variants (
                            run_id, generation_index, variant_name, parameters, train_metrics, val_metrics,
                            stability_score, validation_stability_score, deployment_score, ranking, warnings
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            gen_idx,
                            r.variant_name,
                            json.dumps(r.parameters),
                            json.dumps(r.train_metrics),
                            json.dumps(r.val_metrics),
                            r.stability_score,
                            r.validation_stability_score,
                            r.deployment_score,
                            r.ranking,
                            json.dumps(r.warnings)
                        )
                    )
                self.db.conn.commit()
            except Exception as e:
                print(f"Error saving orchestrator run to DB: {e}")
                
            current_variants = next_variants

        return run_id, generation_results
