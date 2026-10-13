"""
providers/provider_manager.py
Provider manager orchestrator that loads the correct AI provider class and handles fallback template generation.
"""
import threading
import logging
from typing import Dict, Any, Type
from providers.base_provider import BaseProvider
from providers.gemini_provider import GeminiProvider
from providers.openai_provider import OpenAIProvider
from providers.claude_provider import ClaudeProvider
from providers.openrouter_provider import OpenRouterProvider
from providers.ollama_provider import OllamaProvider
from providers.lmstudio_provider import LMStudioProvider

logger = logging.getLogger("ProviderManager")


class ProviderManager:
    """
    Singleton AI provider manager for configuring and querying AI narrative briefings.
    """

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.active_provider: BaseProvider | None = None
        self.lock = threading.Lock()

    def configure(self, config: Dict[str, Any]) -> None:
        """
        Dynamically configures and instantiates the active provider.
        """
        with self.lock:
            self.config = config
            provider_name = config.get("provider", "Deterministic Heuristic")
            
            provider_classes: Dict[str, Type[BaseProvider]] = {
                "Google Gemini": GeminiProvider,
                "OpenAI": OpenAIProvider,
                "Claude": ClaudeProvider,
                "OpenRouter": OpenRouterProvider,
                "Ollama": OllamaProvider,
                "LM Studio": LMStudioProvider,
                "Custom REST": OpenAIProvider # fallback to standard OpenAI model for custom endpoint
            }
            
            cls = provider_classes.get(provider_name)
            if cls:
                self.active_provider = cls(config)
                logger.info(f"AI Provider successfully configured: {provider_name}")
            else:
                self.active_provider = None
                logger.info("Using local deterministic heuristic briefs.")

    def test_connection(self) -> bool:
        """Tests connection to the active provider."""
        with self.lock:
            if self.active_provider:
                return self.active_provider.test_connection()
            return True # Heuristic template requires no connection

    def generate_briefing(self, structured_context: Dict[str, Any]) -> Dict[str, Any]:
        """Generates briefing via active provider, falling back to deterministic template on failure."""
        provider = None
        with self.lock:
            provider = self.active_provider
            
        if provider:
            try:
                return provider.generate_briefing(structured_context)
            except Exception as e:
                logger.error(f"AI generation failed, falling back to heuristic template: {e}")
                
        # Deterministic Heuristic Fallback
        return self._generate_heuristic_briefing(structured_context)

    def _generate_heuristic_briefing(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Generates a structured briefing dynamically from diagnostics without LLM APIs."""
        market_regime = ctx.get("market_regime", {})
        if not market_regime:
            market_regime = ctx.get("market_state", {})
            
        regime = market_regime.get("regime", market_regime.get("macro_regime", "RANGING"))
        direction = market_regime.get("direction", market_regime.get("macro_direction", "NEUTRAL"))
        
        # Risk level
        risk = ctx.get("institutional_risk", {})
        risk_level = risk.get("risk_level", "LOW")
        
        # Readiness
        ready = ctx.get("execution_readiness", {})
        ready_state = ready.get("execution_state", "WATCHLIST")
        ready_score = ready.get("readiness_score", 50.0)

        # Contradictions
        contra = ctx.get("contradiction_state", ctx.get("contradiction_engine", {}))
        conflicts = contra.get("conflict_count", 0)

        # Opportunities
        opps = []
        if regime == "TRENDING" and direction == "BULLISH":
            opps.append("🟢 **Bullish Trend Alignment:** Market is exhibiting steady upward expansion; ideal for momentum strategies.")
        elif regime == "RANGING":
            opps.append("🟢 **Mean Reversion Overlap:** Prices are oscillating near liquidity boundaries; favorable for Bollinger and RSI exhaustion tags.")
        else:
            opps.append("🟢 **Exhaustion Identification:** Volatility spike indicates potential climax; monitor extreme levels for reversals.")
            
        opps.append("🟢 **Liquidity Window:** Active trading session aligns with positive liquidity acceleration indices.")

        # Risks
        risks = []
        if conflicts > 0:
            risks.append(f"🔴 **Structural Contradictions:** {conflicts} active contradictions identified between timeframes. High probability of chop.")
        if risk_level in ("HIGH", "CRITICAL"):
            risks.append(f"🔴 **Elevated Operations Risk:** Risk score is elevated at {risk.get('risk_score', 0):.0f}/100. Restrict sizing.")
        else:
            risks.append("🟡 **Low Trend Stability:** Macro index points to a shifting transition state. Watch out for fakeouts.")
            
        if ready_state != "READY":
            risks.append(f"🔴 **Execution Block:** Readiness score is {ready_score:.1f}%. Deployment gating is active.")

        return {
            "executive_summary": (
                f"Deterministically evaluated market state identifies a {regime} regime with a {direction} bias. "
                f"System Readiness score sits at {ready_score:.1f}% under {risk_level} risk conditions."
            ),
            "key_opportunities": opps,
            "key_risks": risks,
            "timing_summary": f"Timing environment evaluated as {ready_state} based on active session parameters.",
            "deployment_context": (
                f"Tournament deployment gating is {ready_state} (Conflict Count: {conflicts}). "
                f"Safety locks are fully operational."
            )
        }


# Global manager singleton
_provider_manager = None
_pm_lock = threading.Lock()

def get_provider_manager() -> ProviderManager:
    global _provider_manager
    with _pm_lock:
        if _provider_manager is None:
            _provider_manager = ProviderManager()
        return _provider_manager
