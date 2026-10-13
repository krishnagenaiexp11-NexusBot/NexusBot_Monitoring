"""
deployment/precision_entry_engine.py
Builds deterministic execution plans from the winning strategy and current context.

This component does not send orders, alter rankings, or change strategy logic.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import timedelta
from typing import Any

import pandas as pd


@dataclass
class TradePlan:
    symbol: str
    timeframe: str
    strategy: str
    direction: str
    entry_zone_low: float
    entry_zone_high: float
    entry_trigger: float
    trigger_condition: str
    execution_condition: str
    invalidation: str
    stop_loss: float
    take_profit: float
    risk_reward: float
    confidence: float
    trade_quality: float
    status: str
    expiration_time: str
    candle_time: str
    created_at: str
    atr: float
    vwap: float | None = None
    market_state: str = "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["sl"] = self.stop_loss
        data["tp"] = self.take_profit
        data["entry_price"] = (self.entry_zone_low + self.entry_zone_high) / 2.0
        data["entry_zone"] = [self.entry_zone_low, self.entry_zone_high]
        data["strategy_winner"] = self.strategy
        return data


class PrecisionEntryEngine:
    """
    Converts a deterministic winner/candidate into a precise executable plan.
    """

    def build_plan(
        self,
        *,
        symbol: str,
        timeframe: str,
        strategy_name: str,
        direction: str,
        current_price: float,
        atr: float,
        confidence: float,
        trade_quality: float,
        sl: float,
        tp: float,
        candle_time,
        market_state: str = "UNKNOWN",
        vwap: float | None = None,
    ) -> TradePlan:
        direction = str(direction or "NEUTRAL").upper()
        if direction == "BULLISH":
            direction = "BUY"
        elif direction == "BEARISH":
            direction = "SELL"
        if direction not in ("BUY", "SELL"):
            direction = "BUY"

        current_price = float(current_price or 0.0)
        atr = max(float(atr or 0.0), current_price * 0.001 if current_price else 1.0)
        zone_half_width = max(atr * 0.18, current_price * 0.00025 if current_price else atr * 0.18)

        if direction == "BUY":
            entry_mid = current_price - atr * 0.22
            entry_low = entry_mid - zone_half_width
            entry_high = entry_mid + zone_half_width
            trigger = entry_high
            trigger_text = f"Bullish {timeframe} close above {trigger:.5f}"
            execution_text = "Price must trade into entry zone, then close through trigger with active readiness gates."
            invalidation = f"Invalid below SL {float(sl):.5f}"
        else:
            entry_mid = current_price + atr * 0.22
            entry_low = entry_mid - zone_half_width
            entry_high = entry_mid + zone_half_width
            trigger = entry_low
            trigger_text = f"Bearish {timeframe} close below {trigger:.5f}"
            execution_text = "Price must trade into entry zone, then close through trigger with active readiness gates."
            invalidation = f"Invalid above SL {float(sl):.5f}"

        risk = abs(current_price - float(sl)) if sl else atr
        reward = abs(float(tp) - current_price) if tp else atr
        risk_reward = reward / risk if risk > 0 else 0.0

        ts = pd.Timestamp(candle_time) if candle_time is not None else pd.Timestamp.utcnow()
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        expiration = ts + timedelta(minutes=15)

        return TradePlan(
            symbol=str(symbol or "UNKNOWN").upper(),
            timeframe=str(timeframe or "M5").upper(),
            strategy=strategy_name,
            direction=direction,
            entry_zone_low=float(min(entry_low, entry_high)),
            entry_zone_high=float(max(entry_low, entry_high)),
            entry_trigger=float(trigger),
            trigger_condition=trigger_text,
            execution_condition=execution_text,
            invalidation=invalidation,
            stop_loss=float(sl or 0.0),
            take_profit=float(tp or 0.0),
            risk_reward=float(risk_reward),
            confidence=float(confidence or 0.0),
            trade_quality=float(trade_quality or confidence or 0.0),
            status="SETUP_FORMING",
            expiration_time=expiration.isoformat(),
            candle_time=ts.isoformat(),
            created_at=pd.Timestamp.utcnow().isoformat(),
            atr=float(atr),
            vwap=float(vwap) if vwap is not None else None,
            market_state=str(market_state or "UNKNOWN"),
        )

