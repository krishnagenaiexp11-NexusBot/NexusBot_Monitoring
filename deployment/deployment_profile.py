"""
deployment/deployment_profile.py
Deployment Profile presets and configurations for Auto Trade Engine.
"""
from dataclasses import dataclass, field, asdict
from typing import List


@dataclass
class AutoTradeDeploymentProfile:
    """
    User configuration profile for live strategy deployment.
    """
    name: str
    minimum_confidence: float
    max_spread: float
    max_positions: int
    allowed_sessions: List[str] = field(default_factory=list)
    risk_per_trade: float = 0.5

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AutoTradeDeploymentProfile":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# Define canonical presets
PRESETS = {
    "Momentum Moderate": AutoTradeDeploymentProfile(
        name="Momentum Moderate",
        minimum_confidence=58.0,
        max_spread=25.0,
        max_positions=2,
        allowed_sessions=["LONDON", "NEW_YORK", "NY_OVERLAP", "LONDON_NY_OVERLAP"],
        risk_per_trade=0.5
    ),
    "Conservative Scalping": AutoTradeDeploymentProfile(
        name="Conservative Scalping",
        minimum_confidence=65.0,
        max_spread=15.0,
        max_positions=1,
        allowed_sessions=["LONDON", "LONDON_NY_OVERLAP"],
        risk_per_trade=0.25
    ),
    "Aggressive Swing": AutoTradeDeploymentProfile(
        name="Aggressive Swing",
        minimum_confidence=50.0,
        max_spread=40.0,
        max_positions=4,
        allowed_sessions=["LONDON", "NEW_YORK", "ASIAN", "NY_OVERLAP"],
        risk_per_trade=1.0
    ),
    "Aggressive Scalping": AutoTradeDeploymentProfile(
        name="Aggressive Scalping",
        minimum_confidence=52.0,
        max_spread=20.0,
        max_positions=3,
        allowed_sessions=["LONDON", "NEW_YORK", "NY_OVERLAP"],
        risk_per_trade=0.75
    ),
    "Conservative Swing": AutoTradeDeploymentProfile(
        name="Conservative Swing",
        minimum_confidence=68.0,
        max_spread=30.0,
        max_positions=1,
        allowed_sessions=["LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
        risk_per_trade=0.25
    ),
    "Mean Reversion Moderate": AutoTradeDeploymentProfile(
        name="Mean Reversion Moderate",
        minimum_confidence=55.0,
        max_spread=20.0,
        max_positions=2,
        allowed_sessions=["LONDON", "NEW_YORK", "ASIAN", "NY_OVERLAP"],
        risk_per_trade=0.5
    )
}


def get_preset(name: str) -> AutoTradeDeploymentProfile:
    """Returns the requested preset profile or the default Momentum Moderate."""
    return PRESETS.get(name, PRESETS["Momentum Moderate"])
