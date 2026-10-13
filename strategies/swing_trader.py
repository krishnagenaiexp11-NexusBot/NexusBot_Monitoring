from strategies.base_strategy import BaseStrategy
from utils.indicators import atr, ema, macd


class SwingTrader(BaseStrategy):
    metadata = {
        "name": "Swing Trader",
        "description": "Multi-hour trend continuation with wider ATR stops and MACD confirmation.",
        "risk_level": "MEDIUM",
        "recommended_markets": ["XAUUSD", "EURUSD", "US30", "NAS100"],
        "supported_timeframes": ["H1", "H4"],
    }

    default_params = {
        **BaseStrategy.default_params,
        "ema_fast": 21,
        "ema_slow": 50,
        "sl_atr_multiplier": 2.8,
        "tp_atr_multiplier": 4.0,
        "trailing_step_atr": 1.5,
        "entry_cooldown_candles": 12,
        "use_adx_filter": False,
        "adx_period": 14,
        "adx_threshold": 20.0,
    }

    def prepare_indicators(self, df):
        df = df.copy()
        df["ema_fast"] = ema(df["close"], self.params["ema_fast"])
        df["ema_slow"] = ema(df["close"], self.params["ema_slow"])
        df["atr"] = atr(df, self.params["atr_period"])
        df = df.join(macd(df["close"]))
        
        from utils.indicators import adx
        df["adx"] = adx(df, self.params["adx_period"])
        
        # Keep original swing threshold: 0.03
        df["ema_slowing"] = df["ema_fast"].diff(self.params["ema_slowing_lookback"]).abs() < df["atr"] * 0.03
        return df

    def generate_signal(self, df):
        if not self.validate_entry(df):
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        row = df.iloc[-1]
        reasons = []
        strength = 60

        is_buy = row["ema_fast"] > row["ema_slow"] and row["macd"] > row["macd_signal"]
        is_sell = row["ema_fast"] < row["ema_slow"] and row["macd"] < row["macd_signal"]

        if not is_buy and not is_sell:
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        if is_buy:
            reasons.append("EMA Fast > Slow & MACD Bullish Crossover")
            
            # Optional ADX filter
            if self.params.get("use_adx_filter", False):
                if row["adx"] <= self.params["adx_threshold"]:
                    return {"signal": "HOLD", "strength": 0, "reasons": []}
                reasons.append(f"ADX Trend Strength ({row['adx']:.1f} > {self.params['adx_threshold']:.1f})")
                strength += 20
            else:
                if row["adx"] > self.params["adx_threshold"]:
                    reasons.append(f"Bullish ADX Confluence ({row['adx']:.1f} > {self.params['adx_threshold']:.1f})")
                    strength += 15

            trend_gap = (row["ema_fast"] - row["ema_slow"]) / row["close"] * 100
            if trend_gap > 0.5:
                strength += 15
                reasons.append("Strong Trend Separation (> 0.5%)")

            strength = min(strength, 100)
            return {"signal": "BUY", "strength": int(strength), "reasons": reasons}

        if is_sell:
            reasons.append("EMA Fast < Slow & MACD Bearish Crossover")
            
            # Optional ADX filter
            if self.params.get("use_adx_filter", False):
                if row["adx"] <= self.params["adx_threshold"]:
                    return {"signal": "HOLD", "strength": 0, "reasons": []}
                reasons.append(f"ADX Trend Strength ({row['adx']:.1f} > {self.params['adx_threshold']:.1f})")
                strength += 20
            else:
                if row["adx"] > self.params["adx_threshold"]:
                    reasons.append(f"Bearish ADX Confluence ({row['adx']:.1f} > {self.params['adx_threshold']:.1f})")
                    strength += 15

            trend_gap = (row["ema_slow"] - row["ema_fast"]) / row["close"] * 100
            if trend_gap > 0.5:
                strength += 15
                reasons.append("Strong Trend Separation (> 0.5%)")

            strength = min(strength, 100)
            return {"signal": "SELL", "strength": int(strength), "reasons": reasons}

        return {"signal": "HOLD", "strength": 0, "reasons": []}

    def calculate_sl_tp(self, price, atr, direction):
        return self._atr_sl_tp(price, atr, direction)

    def validate_entry(self, df):
        if not super().validate_entry(df):
            return False

        required = ["ema_fast", "ema_slow", "atr", "macd", "macd_signal", "adx"]
        return self._last_ready(df, required) and df.iloc[-1]["atr"] > 0

    def should_exit(self, position, candle):
        if position["direction"] == "BUY":
            return candle["macd"] < candle["macd_signal"]
        return candle["macd"] > candle["macd_signal"]
