"""
deployment/trading_modes.py
Trading Mode definitions for NexusBot V3.

A Trading Mode is a top-level preset that controls:
  - Which strategies are eligible to compete in the tournament
  - The execution timeframe
  - Risk parameters (risk per trade, max positions, max spread)
  - Default minimum confidence (user-adjustable via UI slider)
  - Allowed trading sessions
"""
from dataclasses import dataclass, field, asdict
from typing import List


@dataclass
class TradingMode:
    """Defines a trading mode preset."""
    name: str
    eligible_strategies: List[str]
    timeframe: str
    risk_per_trade: float
    max_positions: int
    default_confidence: float
    max_spread: float
    allowed_sessions: List[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── 5 Preset Trading Modes ──────────────────────────────────────────────────

TRADING_MODES = {
    "Aggressive Scalper": TradingMode(
        name="Aggressive Scalper",
        description="Fast M5 entries with momentum-driven strategies.",
        eligible_strategies=[
            "Aggressive Scalper",
            "Momentum Continuation",
            "Session Breakout",
            "Structure Shift",
            "Spike Catcher",
        ],
        timeframe="M5",
        risk_per_trade=1.5,
        max_positions=3,
        default_confidence=50.0,
        max_spread=30.0,
        allowed_sessions=["LONDON", "NEW_YORK", "NY_OVERLAP", "LONDON_NY_OVERLAP"],
    ),
    "Swing Trader": TradingMode(
        name="Swing Trader",
        description="Multi-hour trend continuation on H1 timeframe.",
        eligible_strategies=[
            "Elder Swing",
            "Compression Breakout",
            "Breakout Hunter",
            "Liquidity Sweep Reversal",
            "Momentum Continuation",
        ],
        timeframe="H1",
        risk_per_trade=1.0,
        max_positions=2,
        default_confidence=55.0,
        max_spread=50.0,
        allowed_sessions=["LONDON", "NEW_YORK", "ASIAN", "NY_OVERLAP", "LONDON_NY_OVERLAP"],
    ),
    "Reversal Hunter": TradingMode(
        name="Reversal Hunter",
        description="Counter-trend and mean reversion setups on M15.",
        eligible_strategies=[
            "Mean Reversion",
            "Exhaustion Reversal",
            "Trap Reversal",
            "Dead Cat Bounce",
            "FVG Reaction",
        ],
        timeframe="M15",
        risk_per_trade=0.75,
        max_positions=2,
        default_confidence=58.0,
        max_spread=25.0,
        allowed_sessions=["LONDON", "NEW_YORK", "NY_OVERLAP", "LONDON_NY_OVERLAP"],
    ),
    "Breakout Specialist": TradingMode(
        name="Breakout Specialist",
        description="Compression and range breakout plays on M15.",
        eligible_strategies=[
            "Compression Breakout",
            "Breakout Hunter",
            "Session Breakout",
            "Structure Shift",
            "FVG Reaction",
        ],
        timeframe="M15",
        risk_per_trade=1.0,
        max_positions=2,
        default_confidence=55.0,
        max_spread=30.0,
        allowed_sessions=["LONDON", "NEW_YORK", "NY_OVERLAP", "LONDON_NY_OVERLAP"],
    ),
    "Conservative": TradingMode(
        name="Conservative",
        description="Low-risk, high-conviction setups on H1.",
        eligible_strategies=[
            "Mean Reversion",
            "Elder Swing",
            "Absorption",
            "Liquidity Sweep Reversal",
            "Exhaustion Reversal",
        ],
        timeframe="H1",
        risk_per_trade=0.5,
        max_positions=1,
        default_confidence=65.0,
        max_spread=25.0,
        allowed_sessions=["LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
    ),
}

DEFAULT_MODE_NAME = "Aggressive Scalper"


def get_mode(name: str) -> TradingMode:
    """Returns the requested trading mode or the default."""
    return TRADING_MODES.get(name, TRADING_MODES[DEFAULT_MODE_NAME])


def list_mode_names() -> list:
    """Returns the ordered list of available trading mode names."""
    return list(TRADING_MODES.keys())
