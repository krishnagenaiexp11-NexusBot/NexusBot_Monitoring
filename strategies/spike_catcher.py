from strategies.base_strategy import BaseStrategy
from utils.indicators import atr, ema, rsi


class SpikeCatcher(BaseStrategy):
    metadata = {
        "name": "Spike Catcher",
        "description": "Volatility expansion breakout strategy with fast exits.",
        "risk_level": "HIGH",
        "recommended_markets": ["XAUUSD", "NAS100", "US30"],
        "supported_timeframes": ["M1", "M5", "M15"],
        "version": "1.0.0",
    }

    default_params = {
        **BaseStrategy.default_params,
        "sl_atr_multiplier": 1.4,
        "tp_atr_multiplier": 2.6,
        "volume_spike_mult": 2.0,
        "atr_expansion_mult": 1.5,
        "max_spread_atr_ratio": 0.25,
        "entry_cooldown_candles": 2,
        "use_adx_filter": False,
        "adx_period": 14,
        "adx_threshold": 20.0,
    }

    def prepare_indicators(self, df):
        df = df.copy()
        df["ema_fast"] = ema(df["close"], self.params["ema_fast"])
        df["ema_slow"] = ema(df["close"], self.params["ema_slow"])
        df["atr"] = atr(df, self.params["atr_period"])
        df["atr_mean"] = df["atr"].rolling(20).mean()
        df["rsi"] = rsi(df["close"], 7)
        df["volume_mean"] = df["volume"].rolling(20).mean()
        df["momentum"] = df["close"].diff(3)
        df["ema_slowing"] = df["momentum"].abs() < df["atr"] * 0.10
        
        from utils.indicators import adx
        df["adx"] = adx(df, self.params["adx_period"])
        return df

    def generate_signal(self, df):
        if not self.validate_entry(df):
            row = df.iloc[-1]
            rejections = []
            if not self._is_in_session(row["timestamp"]):
                rejections.append("session_filter")
            if not self._validate_candle_strength(row):
                rejections.append("candle_strength_filter")
            if not self._validate_min_atr(row):
                rejections.append("min_atr_filter")

            spread = float(self.params.get("spread", 0.0))
            atr_val = row.get("atr", 0.0) or 0.0
            if atr_val > 0 and (spread / atr_val) > self.params.get("max_spread_atr_ratio", 0.25):
                rejections.append("spread_protection")

            return {"signal": "HOLD", "strength": 0, "reasons": [], "rejections": rejections}

        row = df.iloc[-1]
        reasons = []
        rejections = []
        strength = 50

        atr_expansion = row["atr"] > row["atr_mean"] * self.params["atr_expansion_mult"]
        volume_spike = row["volume"] > row["volume_mean"] * self.params["volume_spike_mult"]

        is_buy_base = atr_expansion and volume_spike and row["momentum"] > 0 and row["close"] > row["ema_fast"] and row["rsi"] > 55
        is_sell_base = atr_expansion and volume_spike and row["momentum"] < 0 and row["close"] < row["ema_fast"] and row["rsi"] < 45

        if not is_buy_base and not is_sell_base:
            return {"signal": "HOLD", "strength": 0, "reasons": [], "rejections": []}

        base_dir = "BUY" if is_buy_base else "SELL"

        if self.params.get("use_adx_filter", False):
            if row["adx"] <= self.params["adx_threshold"]:
                rejections.append("adx_filter")
                return {"signal": "HOLD", "strength": 0, "reasons": [], "rejections": rejections, "base_direction": base_dir}

        reasons.append(f"Volatility Expansion (ATR {row['atr']:.4f} > Mean * {self.params['atr_expansion_mult']})")
        reasons.append(f"Volume Spike (Volume {row['volume']:.0f} > Mean * {self.params['volume_spike_mult']})")

        if is_buy_base:
            reasons.append("Breakout Direction: Bullish (Momentum > 0, Price > EMA Fast, RSI > 55)")
            if self.params.get("use_adx_filter", False):
                reasons.append(f"ADX Trend Strength ({row['adx']:.1f} > {self.params['adx_threshold']:.1f})")
            if row["rsi"] > 65:
                strength += 25
                reasons.append("Strong Momentum Confluence (RSI > 65)")
            if row["volume"] > row["volume_mean"] * 3.0:
                strength += 25
                reasons.append("Extreme Volume Confluence (> 3x mean)")

            strength = min(strength, 100)
            return {"signal": "BUY", "strength": int(strength), "reasons": reasons, "rejections": []}

        if is_sell_base:
            reasons.append("Breakout Direction: Bearish (Momentum < 0, Price < EMA Fast, RSI < 45)")
            if self.params.get("use_adx_filter", False):
                reasons.append(f"ADX Trend Strength ({row['adx']:.1f} > {self.params['adx_threshold']:.1f})")
            if row["rsi"] < 35:
                strength += 25
                reasons.append("Strong Momentum Confluence (RSI < 35)")
            if row["volume"] > row["volume_mean"] * 3.0:
                strength += 25
                reasons.append("Extreme Volume Confluence (> 3x mean)")

            strength = min(strength, 100)
            return {"signal": "SELL", "strength": int(strength), "reasons": reasons, "rejections": []}

        return {"signal": "HOLD", "strength": 0, "reasons": [], "rejections": []}

    def calculate_sl_tp(self, price, atr, direction):
        return self._atr_sl_tp(price, atr, direction)

    def validate_entry(self, df):
        if not super().validate_entry(df):
            return False

        # Spread Protection Check (Spread awareness)
        row = df.iloc[-1]
        spread = float(self.params.get("spread", 0.0))
        atr_val = row.get("atr", 0.0) or 0.0
        if atr_val > 0 and (spread / atr_val) > self.params.get("max_spread_atr_ratio", 0.25):
            return False

        required = ["ema_fast", "ema_slow", "atr", "atr_mean", "rsi", "volume_mean", "momentum", "adx"]
        return self._last_ready(df, required) and df.iloc[-1]["atr"] > 0

    def should_exit(self, position, candle):
        if position["direction"] == "BUY":
            return candle["momentum"] < 0 or candle["rsi"] < 50
        return candle["momentum"] > 0 or candle["rsi"] > 50
