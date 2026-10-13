"""
engine/orchestration_context.py
Orchestration Context Container for NexusBot V3.

Acts as the single source-of-truth object that holds the complete quantitative
state across H4 structure, H1 context, M15 execution, M5 precision, sessions,
signal quality, market memory, transitions, and tournament standings.

V3 additions:
  - contradiction_engine    : Structural conflict detection
  - confidence_hierarchy    : Timeframe-weighted trust scoring
  - signal_saturation       : Correlated cluster de-duplication
  - institutional_risk      : Multi-factor operational risk
  - narrative_compression   : 5-point institutional insight bullets
  - candlestick_intelligence: Wick/body pattern detection
  - execution_clock         : Closed-candle timing context
"""
import pandas as pd


class OrchestrationContext:
    """
    Unified immutable-style state container for NexusBot V3.
    Ensures indicators and metrics are computed once and shared globally.
    """

    def __init__(self, bundle: dict):
        """
        Initializes the context container with the timeframe bundle.

        Args:
            bundle: Dict containing DataFrames for 'm5', 'm15', 'h1', 'h4'.
        """
        self.bundle = bundle

        # Phase 2: Structure Layers
        self.h4_structure = {}
        self.h1_structure = {}
        self.session_context = {}
        self.regime_transition = {}
        self.market_memory = {}
        self.market_regime = {}
        self.liquidity_state = {}
        self.volatility_state = {}
        self.structure_state = {}

        # Phase 3: Execution Layers
        self.m15_execution = {}
        self.m5_precision = {}
        self.signal_quality = {}
        self.execution_readiness = {}
        self.execution_clock = {}
        self.active_strategies = []
        self.execution_candidates = []

        # V3 Intelligence Engines
        self.candlestick_intelligence = {}
        self.contradiction_state = {}
        self.contradiction_engine = {}
        self.confidence_hierarchy = {}
        self.signal_saturation = {}
        self.institutional_risk = {}
        self.edge_validation = {}
        self.market_similarity = {}
        self.cross_asset_intelligence = {}
        self.narrative_compression = {}

        # Tournament & Explanations
        self.tournament_results = []
        self.recommended_strategy = None
        self.market_explainer = {}

    def get_df(self, tf: str) -> pd.DataFrame:
        """Helper to safely fetch a timeframe DataFrame."""
        return self.bundle.get(tf, pd.DataFrame())

    def to_dict(self) -> dict:
        """Converts the full state context into a serializable dictionary."""
        return {
            # Phase 2
            "h4_structure": self.h4_structure,
            "h1_structure": self.h1_structure,
            "session_context": self.session_context,
            "regime_transition": self.regime_transition,
            "market_memory": self.market_memory,
            "market_regime": self.market_regime,
            "liquidity_state": self.liquidity_state,
            "volatility_state": self.volatility_state,
            "structure_state": self.structure_state,
            # Phase 3
            "m15_execution": self.m15_execution,
            "m5_precision": self.m5_precision,
            "signal_quality": self.signal_quality,
            "execution_readiness": self.execution_readiness,
            "execution_clock": self.execution_clock,
            "active_strategies": self.active_strategies,
            "execution_candidates": self.execution_candidates,
            # V3 Intelligence
            "candlestick_intelligence": self.candlestick_intelligence,
            "contradiction_state": self.contradiction_state,
            "contradiction_engine": self.contradiction_engine,
            "confidence_hierarchy": self.confidence_hierarchy,
            "signal_saturation": self.signal_saturation,
            "institutional_risk": self.institutional_risk,
            "edge_validation": self.edge_validation,
            "market_similarity": self.market_similarity,
            "cross_asset_intelligence": self.cross_asset_intelligence,
            "narrative_compression": self.narrative_compression,
            # Tournament
            "tournament_results": self.tournament_results,
            "recommended_strategy": self.recommended_strategy,
            "market_explainer": self.market_explainer,
        }
