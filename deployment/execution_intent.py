"""
deployment/execution_intent.py
ExecutionIntent definition for standardized broker-independent order intents.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class ExecutionIntent:
    """
    Standardized intent payload carrying all details required for executing a trade.
    """
    symbol: str
    direction: str              # BUY / SELL
    execution_type: str         # MARKET / LIMIT
    strategy: str
    risk_profile: str
    confidence: float
    sl: float
    tp: float
    risk_per_trade: float
    qty: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionIntent":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
