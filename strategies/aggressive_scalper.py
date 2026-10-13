from strategies.base_strategy import BaseStrategy
from utils.indicators import atr, ema, supertrend


class AggressiveScalper(BaseStrategy):
    metadata = {
        "name": "Aggressive Scalper",
        "description": "Fast ATR and Supertrend scalping with aggressive trailing.",
        "risk_level": "HIGH",
        "recommended_markets": ["XAUUSD", "NAS100"],
        "supported_timeframes": ["M1", "M5"],
    }

    default_params = {
        **BaseStrategy.default_params,
        "max_parallel_positions": 1,
        "entry_cooldown_candles": 10,
        "sl_atr_multiplier": 2.4,
        "tp_atr_multiplier": 3.2,
        "breakeven_atr": 2.0,
        "trailing_start_atr": 2.0,
        "trailing_step_atr": 1.8,
        "partial_close_enabled": False,
        "rsi_period": 14,
        "rsi_buy_min": 58,
        "rsi_sell_max": 42,
        "adx_period": 14,
        "adx_threshold": 20.0,
        "htf_confirmation_enabled": True,
        "htf_timeframe": "15Min",
        "htf_ema_period": 50,
    }

    def prepare_indicators(self, df):
        df = df.copy()
        df["ema_fast"] = ema(df["close"], self.params["ema_fast"])
        df["ema_slow"] = ema(df["close"], self.params["ema_slow"])
        df["atr"] = atr(df, self.params["atr_period"])
        df = df.join(supertrend(df, self.params["supertrend_period"], self.params["supertrend_multiplier"]))
        
        from utils.indicators import rsi, adx, htf_ema
        df["rsi"] = rsi(df["close"], self.params["rsi_period"])
        df["adx"] = adx(df, self.params["adx_period"])

        if self.params.get("htf_confirmation_enabled", False):
            df["htf_ema"] = htf_ema(df, self.params["htf_timeframe"], self.params["htf_ema_period"])
        else:
            df["htf_ema"] = float("nan")

        # Relaxed EMA slowing exit threshold: change 0.05 to 0.15
        df["ema_slowing"] = df["ema_fast"].diff(self.params["ema_slowing_lookback"]).abs() < df["atr"] * 0.15
        return df

    def generate_signal(self, df):
        if not self.validate_entry(df):
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        import pandas as pd
        row = df.iloc[-1]
        reasons = []
        strength = 50

        # Base Direction
        is_buy = row["ema_fast"] > row["ema_slow"] and row["supertrend_dir"] == 1
        is_sell = row["ema_fast"] < row["ema_slow"] and row["supertrend_dir"] == -1

        if not is_buy and not is_sell:
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        if is_buy:
            reasons.append("EMA Fast > Slow & Supertrend Bullish")
            # ADX Filter
            if row["adx"] <= self.params["adx_threshold"]:
                return {"signal": "HOLD", "strength": 0, "reasons": []}
            reasons.append(f"ADX Trend Strength ({row['adx']:.1f} > {self.params['adx_threshold']:.1f})")
            if row["adx"] > 25:
                strength += 15
                reasons.append("Strong Trend (ADX > 25)")

            # RSI Filter
            if row["rsi"] <= self.params["rsi_buy_min"]:
                return {"signal": "HOLD", "strength": 0, "reasons": []}
            reasons.append(f"RSI Momentum ({row['rsi']:.1f} > {self.params['rsi_buy_min']:.1f})")
            if row["rsi"] > 65:
                strength += 15
                reasons.append("High Momentum (RSI > 65)")

            # HTF Confirmation Filter
            if self.params.get("htf_confirmation_enabled", False):
                if pd.isna(row["htf_ema"]) or row["close"] <= row["htf_ema"]:
                    return {"signal": "HOLD", "strength": 0, "reasons": []}
                reasons.append(f"HTF Trend Alignment (Close > {row['htf_ema']:.2f})")
                strength += 20

            strength = min(strength, 100)
            return {"signal": "BUY", "strength": int(strength), "reasons": reasons}

        if is_sell:
            reasons.append("EMA Fast < Slow & Supertrend Bearish")
            # ADX Filter
            if row["adx"] <= self.params["adx_threshold"]:
                return {"signal": "HOLD", "strength": 0, "reasons": []}
            reasons.append(f"ADX Trend Strength ({row['adx']:.1f} > {self.params['adx_threshold']:.1f})")
            if row["adx"] > 25:
                strength += 15
                reasons.append("Strong Trend (ADX > 25)")

            # RSI Filter
            if row["rsi"] >= self.params["rsi_sell_max"]:
                return {"signal": "HOLD", "strength": 0, "reasons": []}
            reasons.append(f"RSI Momentum ({row['rsi']:.1f} < {self.params['rsi_sell_max']:.1f})")
            if row["rsi"] < 35:
                strength += 15
                reasons.append("High Momentum (RSI < 35)")

            # HTF Confirmation Filter
            if self.params.get("htf_confirmation_enabled", False):
                if pd.isna(row["htf_ema"]) or row["close"] >= row["htf_ema"]:
                    return {"signal": "HOLD", "strength": 0, "reasons": []}
                reasons.append(f"HTF Trend Alignment (Close < {row['htf_ema']:.2f})")
                strength += 20

            strength = min(strength, 100)
            return {"signal": "SELL", "strength": int(strength), "reasons": reasons}

        return {"signal": "HOLD", "strength": 0, "reasons": []}

    def calculate_sl_tp(self, price, atr, direction):
        return self._atr_sl_tp(price, atr, direction)

    def validate_entry(self, df):
        if not super().validate_entry(df):
            return False

        required = ["ema_fast", "ema_slow", "atr", "supertrend_dir", "rsi", "adx"]
        if self.params.get("htf_confirmation_enabled", False):
            required.append("htf_ema")

        return self._last_ready(df, required) and df.iloc[-1]["atr"] > 0

    def should_exit(self, position, candle):
        if position["direction"] == "BUY":
            return candle["supertrend_dir"] == -1
        return candle["supertrend_dir"] == 1
