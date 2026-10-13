from datetime import datetime, timezone
import math
import pandas as pd


def sanitize_trade_snapshot(data: dict) -> dict:
    sanitized = {}

    def clean_val(val, default):
        if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))) or pd.isna(val):
            return default
        return val

    sanitized["rsi"] = float(clean_val(data.get("rsi"), 50.0))
    sanitized["atr"] = float(clean_val(data.get("atr"), 0.0))
    sanitized["volume_ratio"] = float(clean_val(data.get("volume_ratio"), 1.0))
    sanitized["momentum"] = float(clean_val(data.get("momentum"), 0.0))
    sanitized["signal_strength"] = int(clean_val(data.get("signal_strength"), 100))
    sanitized["session"] = str(clean_val(data.get("session"), "UNKNOWN"))
    sanitized["market_regime"] = str(clean_val(data.get("market_regime"), "RANGING"))
    return sanitized


class ExecutionEngine:
    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self.next_ticket = 1

    def open_position(self, strategy, signal: str, candle: dict, qty: float, signal_strength: int = 100, entry_reasons: list | None = None) -> dict:
        spread = float(strategy.params.get("spread", 0.0))
        entry_price = candle["close"]
        if signal == "BUY":
            entry_price += spread
        elif signal == "SELL":
            entry_price -= spread

        sl, tp = strategy.calculate_sl_tp(entry_price, candle["atr"], signal)

        # Extract indicators for snapshot
        vol = candle.get("volume", 0.0)
        vol_mean = candle.get("volume_mean", 0.0)
        vol_ratio = float(vol / vol_mean) if vol_mean > 0 else 1.0

        # Session calculation (UTC hour check)
        timestamp = candle.get("timestamp")
        session_name = "ASIAN/ROLLOVER"
        try:
            dt = pd.to_datetime(timestamp)
            hour = dt.hour
            if 8 <= hour < 13:
                session_name = "LONDON"
            elif 13 <= hour < 17:
                session_name = "NY_OVERLAP"
            elif 17 <= hour < 22:
                session_name = "NEW_YORK"
        except Exception:
            pass

        # Market Regime classification (ADX/ATR based)
        adx_val = candle.get("adx", 0.0) or 0.0
        atr_val = candle.get("atr", 0.0) or 0.0
        atr_mean = candle.get("atr_mean", 0.0) or 0.0

        if atr_mean > 0 and atr_val > atr_mean * 1.5:
            market_regime = "VOLATILE"
        elif atr_mean > 0 and atr_val < atr_mean * 0.7:
            market_regime = "LOW_VOLATILITY"
        elif adx_val > 25:
            market_regime = "TRENDING"
        else:
            market_regime = "RANGING"

        # Gather snapshot data
        raw_snapshot = {
            "rsi": candle.get("rsi"),
            "atr": candle.get("atr"),
            "volume_ratio": vol_ratio,
            "momentum": candle.get("momentum"),
            "signal_strength": signal_strength,
            "session": session_name,
            "market_regime": market_regime,
        }
        # Sanitize data to avoid NaNs
        clean_snapshot = sanitize_trade_snapshot(raw_snapshot)

        position = {
            "ticket": self.next_ticket,
            "strategy": strategy.metadata["name"],
            "strategy_version": strategy.metadata.get("version", "1.0.0"),
            "direction": signal,
            "entry_time": candle["timestamp"],
            "entry_price": entry_price,
            "initial_sl": sl,
            "sl": sl,
            "tp": tp,
            "qty": qty,
            "status": "OPEN",
            "opened_at_utc": datetime.now(timezone.utc).isoformat(),
            "signal_strength": clean_snapshot["signal_strength"],
            "entry_reasons": entry_reasons or [],
            "rsi": clean_snapshot["rsi"],
            "atr": clean_snapshot["atr"],
            "volume_ratio": clean_snapshot["volume_ratio"],
            "momentum": clean_snapshot["momentum"],
            "session": clean_snapshot["session"],
            "market_regime": clean_snapshot["market_regime"],
            "outlier_flag": 0,  # post-processed after backtest run
        }
        self.next_ticket += 1
        if self.event_bus:
            self.event_bus.emit("ORDER EXECUTED")
        return position
