from strategies.aggressive_scalper import AggressiveScalper
from utils.indicators import rsi


class ConservativeScalper(AggressiveScalper):
    metadata = {
        "name": "Conservative Scalper",
        "description": "Lower-frequency scalper with RSI confirmation and stricter trend validation.",
        "risk_level": "MEDIUM",
        "recommended_markets": ["XAUUSD", "EURUSD", "NAS100"],
        "supported_timeframes": ["M5", "M15"],
    }

    default_params = {
        **AggressiveScalper.default_params,
        "max_parallel_positions": 3,
        "entry_cooldown_candles": 12,
        "sl_atr_multiplier": 2.2,
        "tp_atr_multiplier": 3.5,
        "breakeven_atr": 2.2,
        "trailing_start_atr": 2.2,
        "trailing_step_atr": 2.0,
        "rsi_buy_min": 55,
        "rsi_buy_max": 70,
        "rsi_sell_min": 30,
        "rsi_sell_max": 45,
        "adx_period": 14,
        "adx_threshold": 20.0,
        "htf_confirmation_enabled": True,
        "htf_timeframe": "15Min",
        "htf_ema_period": 50,
    }

    def generate_signal(self, df):
        if not self.validate_entry(df):
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        import pandas as pd
        row = df.iloc[-1]
        reasons = []
        strength = 50

        # Gap confirmation
        trend_gap = abs(row["ema_fast"] - row["ema_slow"]) > row["atr"] * 0.08
        is_buy = trend_gap and row["ema_fast"] > row["ema_slow"] and row["supertrend_dir"] == 1
        is_sell = trend_gap and row["ema_fast"] < row["ema_slow"] and row["supertrend_dir"] == -1

        if not is_buy and not is_sell:
            return {"signal": "HOLD", "strength": 0, "reasons": []}

        if is_buy:
            reasons.append("EMA Fast > Slow & Supertrend Bullish & Trend Gap OK")
            
            # ADX filter
            if row["adx"] <= self.params["adx_threshold"]:
                return {"signal": "HOLD", "strength": 0, "reasons": []}
            reasons.append(f"ADX Trend Strength ({row['adx']:.1f} > {self.params['adx_threshold']:.1f})")
            if row["adx"] > 25:
                strength += 15
                reasons.append("Strong Trend (ADX > 25)")

            # RSI Filter (55 < RSI < 70)
            if not (self.params["rsi_buy_min"] < row["rsi"] < self.params["rsi_buy_max"]):
                return {"signal": "HOLD", "strength": 0, "reasons": []}
            reasons.append(f"RSI Momentum ({self.params['rsi_buy_min']:.1f} < {row['rsi']:.1f} < {self.params['rsi_buy_max']:.1f})")
            if 60 < row["rsi"] < 68:
                strength += 15
                reasons.append("Optimal Bullish RSI Range")

            # HTF Confirmation Filter
            if self.params.get("htf_confirmation_enabled", False):
                if pd.isna(row["htf_ema"]) or row["close"] <= row["htf_ema"]:
                    return {"signal": "HOLD", "strength": 0, "reasons": []}
                reasons.append(f"HTF Trend Alignment (Close > {row['htf_ema']:.2f})")
                strength += 20

            strength = min(strength, 100)
            return {"signal": "BUY", "strength": int(strength), "reasons": reasons}

        if is_sell:
            reasons.append("EMA Fast < Slow & Supertrend Bearish & Trend Gap OK")
            
            # ADX filter
            if row["adx"] <= self.params["adx_threshold"]:
                return {"signal": "HOLD", "strength": 0, "reasons": []}
            reasons.append(f"ADX Trend Strength ({row['adx']:.1f} > {self.params['adx_threshold']:.1f})")
            if row["adx"] > 25:
                strength += 15
                reasons.append("Strong Trend (ADX > 25)")

            # RSI Filter (30 < RSI < 45)
            if not (self.params["rsi_sell_min"] < row["rsi"] < self.params["rsi_sell_max"]):
                return {"signal": "HOLD", "strength": 0, "reasons": []}
            reasons.append(f"RSI Momentum ({self.params['rsi_sell_min']:.1f} < {row['rsi']:.1f} < {self.params['rsi_sell_max']:.1f})")
            if 32 < row["rsi"] < 40:
                strength += 15
                reasons.append("Optimal Bearish RSI Range")

            # HTF Confirmation Filter
            if self.params.get("htf_confirmation_enabled", False):
                if pd.isna(row["htf_ema"]) or row["close"] >= row["htf_ema"]:
                    return {"signal": "HOLD", "strength": 0, "reasons": []}
                reasons.append(f"HTF Trend Alignment (Close < {row['htf_ema']:.2f})")
                strength += 20

            strength = min(strength, 100)
            return {"signal": "SELL", "strength": int(strength), "reasons": reasons}

        return {"signal": "HOLD", "strength": 0, "reasons": []}
