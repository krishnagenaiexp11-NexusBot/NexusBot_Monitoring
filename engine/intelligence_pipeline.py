"""
engine/intelligence_pipeline.py
Central Intelligence Pipeline Orchestrator for NexusBot V3.

Strict rules: no live trading, no threading, no websockets, pure functions only.
"""
import pandas as pd

from engine.orchestration_context import OrchestrationContext
from engine.context_cache import ContextCache
from engine.feature_engineering import compute_features
from engine.strategy_registry import get_eligible_strategies

from engine.h4_structure import H4StructureEngine
from engine.mtf_context import MTFContextEngine
from engine.session_context import SessionContextEngine
from engine.regime_transition import RegimeTransitionEngine
from engine.market_memory import MarketMemoryEngine
from engine.m5_execution import M5ExecutionEngine
from engine.execution_clock import ExecutionClock
from engine.signal_quality import SignalQualityEngine
from engine.candlestick_intelligence import CandlestickIntelligenceEngine
from engine.contradiction_engine import ContradictionEngine
from engine.confidence_hierarchy import ConfidenceHierarchyEngine
from engine.signal_saturation import SignalSaturationEngine
from engine.institutional_risk import InstitutionalRiskEngine
from engine.execution_readiness import ExecutionReadinessEngine
from engine.strategy_tournament import StrategyTournamentEngine
from engine.tournament_models import TournamentInput
from engine.market_explainer import MarketExplainer
from engine.narrative_compression import NarrativeCompressionEngine
from engine.market_regime import MarketRegimeEngine


_h4_engine = H4StructureEngine()
_mtf_engine = MTFContextEngine()
_session_engine = SessionContextEngine()
_transition_engine = RegimeTransitionEngine()
_memory_engine = MarketMemoryEngine()
_m5_engine = M5ExecutionEngine()
_clock_engine = ExecutionClock()
_signal_q_engine = SignalQualityEngine()
_candle_engine = CandlestickIntelligenceEngine()
_contradiction_eng = ContradictionEngine()
_confidence_eng = ConfidenceHierarchyEngine()
_saturation_eng = SignalSaturationEngine()
_risk_eng = InstitutionalRiskEngine()
_readiness_eng = ExecutionReadinessEngine()
_tournament_eng = StrategyTournamentEngine()
_explainer_eng = MarketExplainer()
_narrative_eng = NarrativeCompressionEngine()
_regime_eng = MarketRegimeEngine()

_cache = ContextCache()


def run_intelligence_pipeline(
    bundle: dict,
    use_cache: bool = True,
    timeframe_minutes: int = 5,
) -> OrchestrationContext:
    m5_df = bundle.get("m5", pd.DataFrame())
    m15_df = bundle.get("m15", pd.DataFrame())
    h1_df = bundle.get("h1", pd.DataFrame())
    h4_df = bundle.get("h4", pd.DataFrame())

    cache_key = _cache.get_hash(h1_df)
    if use_cache:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

    ctx = OrchestrationContext(bundle)

    try:
        m5_feat = compute_features(m5_df) if not m5_df.empty and len(m5_df) >= 20 else m5_df
        m15_feat = compute_features(m15_df) if not m15_df.empty and len(m15_df) >= 20 else m15_df
        h1_feat = compute_features(h1_df) if not h1_df.empty and len(h1_df) >= 20 else h1_df
        h4_feat = compute_features(h4_df) if not h4_df.empty and len(h4_df) >= 20 else h4_df
    except Exception:
        m5_feat = m5_df
        m15_feat = m15_df
        h1_feat = h1_df
        h4_feat = h4_df

    # Stage 1: structure / session interpretation
    ctx.h4_structure = _h4_engine.analyze(h4_feat)
    mtf_context = _mtf_engine.analyze(h1_feat, m15_feat)
    ctx.h1_structure = mtf_context.get("h1_structure", {})
    ctx.m15_execution = mtf_context.get("m15_execution", {})

    base_df = m5_feat if not m5_feat.empty else m15_feat
    ctx.session_context = _session_engine.analyze(base_df)
    ctx.regime_transition = _transition_engine.analyze(h1_feat)
    ctx.market_memory = _memory_engine.analyze(h1_feat)

    h1_direction = ctx.h4_structure.get("macro_direction", "NEUTRAL")
    ctx.m5_precision = _m5_engine.analyze(m5_feat, h1_direction=h1_direction)
    ctx.execution_clock = _clock_engine.analyze(base_df, timeframe_minutes=timeframe_minutes)

    # Stage 2: liquidity / volatility / regime interpretation
    regime = _regime_eng.detect(h1_feat if not h1_feat.empty else m15_feat)
    ctx.market_regime = regime
    ctx.liquidity_state = regime.get("liquidity_state", {})
    ctx.volatility_state = regime.get("volatility_state", {})
    ctx.structure_state = _build_structure_state(ctx=ctx, regime=regime, mtf_context=mtf_context)

    direction = regime.get("direction", "NEUTRAL")
    ctx.signal_quality = _signal_q_engine.analyze(base_df, direction=direction)
    ctx.candlestick_intelligence = _candle_engine.analyze(base_df)

    ctx.contradiction_engine = _contradiction_eng.analyze(
        h4_structure=ctx.h4_structure,
        session_context=ctx.session_context,
        signal_quality=ctx.signal_quality,
        m5_execution=ctx.m5_precision,
        regime_transition=ctx.regime_transition,
        mtf_context=mtf_context,
    )
    ctx.contradiction_state = ctx.contradiction_engine

    ctx.confidence_hierarchy = _confidence_eng.compute(
        h4_structure=ctx.h4_structure,
        mtf_context=mtf_context,
        session_context=ctx.session_context,
        signal_quality=ctx.signal_quality,
        m5_execution=ctx.m5_precision,
    )
    ctx.signal_saturation = _saturation_eng.analyze(
        signal_quality=ctx.signal_quality,
        h4_structure=ctx.h4_structure,
        regime_transition=ctx.regime_transition,
        m5_execution=ctx.m5_precision,
    )
    ctx.institutional_risk = _risk_eng.analyze(
        h4_structure=ctx.h4_structure,
        session_context=ctx.session_context,
        signal_quality=ctx.signal_quality,
        regime_transition=ctx.regime_transition,
        market_memory=ctx.market_memory,
    )
    ctx.execution_readiness = _readiness_eng.compute(
        h4_structure=ctx.h4_structure,
        session_context=ctx.session_context,
        signal_quality=ctx.signal_quality,
        m5_execution=ctx.m5_precision,
        execution_clock=ctx.execution_clock,
    )

    # Stage 3: strategy eligibility and candidate ranking
    market_state = regime.get("market_state", regime.get("regime", "RANGING"))
    base_regime = regime.get("regime", "RANGING")
    eligible_strategies = get_eligible_strategies(market_state=market_state, regime=base_regime)
    ctx.active_strategies = [strategy.get_strategy_name() for strategy in eligible_strategies]
    ctx.execution_candidates = _build_execution_candidates(ctx=ctx, strategies=eligible_strategies)

    tournament_input = TournamentInput(
        h4_structure=ctx.h4_structure,
        mtf_context=mtf_context,
        m5_execution=ctx.m5_precision,
        session_context=ctx.session_context,
        candlestick_intelligence=ctx.candlestick_intelligence,
        execution_readiness=ctx.execution_readiness,
        contradiction_state=ctx.contradiction_engine,
        institutional_risk=ctx.institutional_risk,
        confidence_hierarchy=ctx.confidence_hierarchy,
        signal_saturation=ctx.signal_saturation,
        edge_validation=getattr(ctx, "edge_validation", None),
        market_similarity=getattr(ctx, "market_similarity", None),
        cross_asset_intelligence=getattr(ctx, "cross_asset_intelligence", None),
    )
    tournament_results = _tournament_eng.rank(tournament_input, eligible_strategies=eligible_strategies)
    ctx.tournament_results = _tournament_eng.strip_internal_fields(tournament_results)
    ctx.recommended_strategy = _tournament_eng.get_recommended(tournament_results)

    ctx.market_explainer = _explainer_eng.explain(
        mtf_context=mtf_context,
        tournament_results=ctx.tournament_results,
        h1_df=h1_feat,
        m15_df=m15_feat,
    )
    ctx.narrative_compression = _narrative_eng.compress(
        h4_structure=ctx.h4_structure,
        mtf_context=mtf_context,
        session_context=ctx.session_context,
        regime_transition=ctx.regime_transition,
        market_memory=ctx.market_memory,
        signal_quality=ctx.signal_quality,
        institutional_risk=ctx.institutional_risk,
        execution_readiness=ctx.execution_readiness,
        confidence_hierarchy=ctx.confidence_hierarchy,
        contradiction_engine=ctx.contradiction_engine,
        tournament_results=ctx.tournament_results,
    )

    # Log decision for observability
    try:
        from storage.decision_logger import DecisionLogger
        sym = bundle.get("symbol", "UNKNOWN")
        tf_str = f"M{timeframe_minutes}"
        DecisionLogger.log_decision(symbol=sym, timeframe=tf_str, ctx=ctx)
    except Exception:
        pass

    _cache.set(cache_key, ctx)
    return ctx


def _build_structure_state(ctx: OrchestrationContext, regime: dict, mtf_context: dict) -> dict:
    state = dict(regime.get("structure_state", {}))
    state.setdefault("macro_direction", ctx.h4_structure.get("macro_direction", "NEUTRAL"))
    state.setdefault("macro_strength", ctx.h4_structure.get("macro_strength", 0.0))
    state.setdefault("macro_regime", mtf_context.get("h1_structure", {}).get("macro_regime", regime.get("regime", "RANGING")))
    state.setdefault("transition_state", ctx.regime_transition.get("transition_state", "STABLE"))
    return state


def _build_execution_candidates(ctx: OrchestrationContext, strategies: list) -> list:
    candidates = []
    for strategy in strategies:
        try:
            if not strategy.validate_context(ctx):
                continue
            candidate = strategy.build_execution_candidate(ctx)
            if candidate is None:
                continue
            if isinstance(candidate, dict):
                payload = dict(candidate)
                payload.setdefault("strategy", strategy.get_strategy_name())
                candidates.append(payload)
        except Exception:
            continue
    return candidates


def clear_pipeline_cache() -> None:
    """Clears the intelligence pipeline cache (call when new data is loaded)."""
    _cache.clear()
