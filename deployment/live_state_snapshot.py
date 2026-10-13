"""
deployment/live_state_snapshot.py
Immutable snapshot representing the state of the NexusBot V3 execution system.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List


@dataclass(frozen=True)
class LiveStateSnapshot:
    """
    Authoritative read-only snapshot of the entire NexusBot V3 execution state.
    """
    engine_state: str = "STOPPED"
    market_state: Dict[str, Any] = field(default_factory=lambda: {
        "regime": "NEUTRAL",
        "macro_direction": "NEUTRAL",
        "phase": "Developing",
        "stress_index": "LOW",
        "price": 0.0,
        "spread": 0.0,
        "volatility": "NORMAL",
        "collapse_prob": 0.0
    })
    strategy_rankings: List[Dict[str, Any]] = field(default_factory=list)
    active_positions: List[Dict[str, Any]] = field(default_factory=list)
    pending_orders: List[Dict[str, Any]] = field(default_factory=list)
    execution_candidates: List[Dict[str, Any]] = field(default_factory=list)
    runtime_snapshot: Dict[str, Any] = field(default_factory=lambda: {
        "current_price": 0.0,
        "bid": 0.0,
        "ask": 0.0,
        "spread": 0.0,
        "symbol": "UNKNOWN",
        "positions": [],
        "orders": [],
    })
    active_trade_plan: Dict[str, Any] = field(default_factory=dict)
    macro_context: Dict[str, Any] = field(default_factory=dict)
    live_trade_state: str = "SCANNING"
    risk_state: Dict[str, Any] = field(default_factory=lambda: {
        "drawdown": 0.0,
        "consecutive_losses": 0,
        "max_drawdown": 5.0,
        "max_losses": 3,
        "safety_locked": False
    })
    event_feed: List[Dict[str, Any]] = field(default_factory=list)
    replay_state: Dict[str, Any] = field(default_factory=lambda: {
        "candle_pointer": 0,
        "play_status": "PAUSED",
        "speed": 1.0,
        "total_candles": 0
    })
    live_metrics: Dict[str, Any] = field(default_factory=lambda: {
        "balance": 10000.0,
        "equity": 10000.0,
        "leverage": 100,
        "currency": "USD",
        "daily_pnl": 0.0
    })
    engine_diagnostics: Dict[str, Any] = field(default_factory=dict)
    pipeline_flow: List[Dict[str, Any]] = field(default_factory=list)
    ai_narrative: Dict[str, Any] = field(default_factory=lambda: {
        "status": "DISCONNECTED",
        "provider": "Deterministic Heuristic",
        "model": "—"
    })
    focus_mode: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the snapshot to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LiveStateSnapshot":
        """Deserializes a dictionary into a LiveStateSnapshot instance."""
        valid_data = {}
        for k, v in data.items():
            if k in cls.__dataclass_fields__:
                valid_data[k] = v
        return cls(**valid_data)
