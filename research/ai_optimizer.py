import os
import json
import hashlib
import random
from ai.gemini_client import GeminiClient
from research.search_space import SEARCH_SPACE
from research.orchestration_models import VariantResult

class AIOptimizer:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.client = GeminiClient(api_key) if api_key else None

    def generate_next_generation(
        self,
        strategy_name: str,
        generation_index: int,
        results: list[VariantResult],
        max_variants: int = 12
    ) -> tuple[list[dict], str]:
        if not results:
            return [], "No prior results to analyze."
            
        best_variant = results[0]
        best_params = best_variant.parameters
        
        if not self.api_key or not self.client:
            mutants = self._local_heuristic_mutate(best_params, max_variants)
            diag = (
                f"[Local Fallback Heuristics] Generation {generation_index}: "
                f"Gemini API offline. Running local deterministic parameter grid walk "
                f"centered on best variant (Deployment Score: {best_variant.deployment_score:.1f})."
            )
            return mutants, diag

        top_3 = results[:3]
        bottom_3 = results[-3:] if len(results) >= 6 else results[3:]
        
        prompt = f"""
You are the AI Optimization Orchestrator for NexusBot.
Your task is to analyze the backtest results of Generation {generation_index} for the strategy '{strategy_name}' and suggest the parameters for the next generation.

### BEST PERFORMING CONFIGURATIONS (TOP 3)
"""
        for r in top_3:
            prompt += f"- Variant: {r.variant_name} | Score: {r.deployment_score:.1f} | Train PF: {r.train_metrics.get('profit_factor', 0.0):.2f} | Val PF: {r.val_metrics.get('profit_factor', 0.0):.2f} | Max DD: {r.val_metrics.get('max_drawdown_pct', 0.0):.2f}%\n"
            prompt += f"  Parameters: {json.dumps(r.parameters)}\n"
            
        prompt += "\n### WORST PERFORMING CONFIGURATIONS (BOTTOM 3)\n"
        for r in bottom_3:
            prompt += f"- Variant: {r.variant_name} | Score: {r.deployment_score:.1f} | Train PF: {r.train_metrics.get('profit_factor', 0.0):.2f} | Val PF: {r.val_metrics.get('profit_factor', 0.0):.2f} | Max DD: {r.val_metrics.get('max_drawdown_pct', 0.0):.2f}%\n"
            prompt += f"  Parameters: {json.dumps(r.parameters)}\n"

        prompt += f"""
### VALID SEARCH SPACE LIMITS
{json.dumps(SEARCH_SPACE, indent=2)}

### INSTRUCTIONS
1. Analyze the parameters that succeeded vs failed. E.g. check if wider stops, session changes, or higher cooldowns improved stability and reduced validation drawdown.
2. Recommend exactly {max_variants} parameter configurations for the next generation.
3. Keep parameters strictly within the bounds defined in the search space.
4. Output a JSON object with exactly two keys:
   - "diagnostics": A brief, 2-bullet quantitative diagnostic of why the best variants succeeded and what parameters must adapt (e.g. increase cooldown from 4 -> 8).
   - "suggestions": A list of exactly {max_variants} parameter dictionaries.
   
Example Response:
{{
  "diagnostics": "Top variants succeeded by raising ADX threshold from 20 to 24 to block flat chop. Validation drawdown was reduced by widening Stop Loss ATR from 1.5 to 2.0.",
  "suggestions": [
     {{"sl_atr_multiplier": 2.0, "tp_atr_multiplier": 3.5, "entry_cooldown_candles": 6, "adx_threshold": 24, "breakeven_atr": 1.5, "trailing_step_atr": 1.0}}
  ]
}}
"""

        try:
            res = self.client.generate_content(prompt, temperature=0.1)
            raw_text = res["raw_response_md"]
            
            import re
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
                if match:
                    cleaned = match.group(1).strip()
            
            data = json.loads(cleaned)
            suggestions = data.get("suggestions", [])
            diagnostics = data.get("diagnostics", f"Generation {generation_index} processed by Gemini.")
            
            valid_suggestions = []
            for sug in suggestions:
                if isinstance(sug, dict):
                    clean_sug = best_params.copy()
                    for k, val in sug.items():
                        if k in SEARCH_SPACE:
                            space = SEARCH_SPACE[k]
                            closest_val = min(space, key=lambda x: abs(x - val))
                            clean_sug[k] = closest_val
                    valid_suggestions.append(clean_sug)
            
            if len(valid_suggestions) < max_variants:
                extra = self._local_heuristic_mutate(best_params, max_variants - len(valid_suggestions))
                valid_suggestions.extend(extra)
                
            return valid_suggestions[:max_variants], diagnostics
            
        except Exception as e:
            mutants = self._local_heuristic_mutate(best_params, max_variants)
            diag = (
                f"[Local Heuristic Fallback] Generation {generation_index} API failure ({str(e)}). "
                f"Ran local deterministic parameter grid walk centered on best variant (Score: {best_variant.deployment_score:.1f})."
            )
            return mutants, diag

    def _local_heuristic_mutate(self, best_params: dict, max_variants: int) -> list[dict]:
        mutants = []
        mutants.append(best_params.copy())
        
        param_keys = list(SEARCH_SPACE.keys())
        
        for key in param_keys:
            if key not in best_params:
                continue
            current_val = best_params[key]
            space_list = SEARCH_SPACE[key]
            if current_val not in space_list:
                closest_idx = min(range(len(space_list)), key=lambda idx: abs(space_list[idx] - current_val))
            else:
                closest_idx = space_list.index(current_val)
                
            if closest_idx > 0:
                new_params = best_params.copy()
                new_params[key] = space_list[closest_idx - 1]
                if new_params not in mutants:
                    mutants.append(new_params)
            if closest_idx < len(space_list) - 1:
                new_params = best_params.copy()
                new_params[key] = space_list[closest_idx + 1]
                if new_params not in mutants:
                    mutants.append(new_params)

        hash_seed = int(hashlib.sha256(json.dumps(best_params, sort_keys=True).encode()).hexdigest(), 16)
        rng = random.Random(hash_seed)
        
        attempts = 0
        while len(mutants) < max_variants and attempts < 200:
            attempts += 1
            new_params = best_params.copy()
            keys_to_mutate = rng.sample(param_keys, rng.randint(1, 2))
            for key in keys_to_mutate:
                if key in best_params:
                    new_params[key] = rng.choice(SEARCH_SPACE[key])
            if new_params not in mutants:
                mutants.append(new_params)
                
        return mutants[:max_variants]
