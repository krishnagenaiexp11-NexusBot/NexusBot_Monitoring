from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class TournamentInput:
    h4_structure: Dict[str, Any]
    mtf_context: Dict[str, Any]
    m5_execution: Dict[str, Any]
    session_context: Dict[str, Any]
    candlestick_intelligence: Dict[str, Any]
    execution_readiness: Dict[str, Any]

    contradiction_state: Optional[Dict[str, Any]] = None
    institutional_risk: Optional[Dict[str, Any]] = None
    confidence_hierarchy: Optional[Dict[str, Any]] = None
    signal_saturation: Optional[Dict[str, Any]] = None
    edge_validation: Optional[Dict[str, Any]] = None
    market_similarity: Optional[Dict[str, Any]] = None
    cross_asset_intelligence: Optional[Dict[str, Any]] = None
