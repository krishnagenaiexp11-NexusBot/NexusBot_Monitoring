"""
engine/candlestick_intelligence.py
Candlestick Pattern Intelligence Engine for NexusBot V3.

Analyzes wicks, bodies, and candle sequences to identify:
- Reversal patterns (pin bars, engulfing, doji)
- Continuation patterns (momentum candles, inside bars)
- Liquidity sweep patterns (wick-trap, stop-hunt)

Fully deterministic — no AI.
"""
import numpy as np
import pandas as pd
from engine.feature_engineering import compute_features


class CandlestickIntelligenceEngine:
    """
    Detects high-probability candlestick formations.
    Uses wicks, body ratios, and volume context.
    """

    def analyze(self, df: pd.DataFrame) -> dict:
        """
        Runs candlestick pattern intelligence on the last 3 candles.

        Args:
            df: OHLCV DataFrame (feature-enriched or raw).

        Returns:
            {
                "pattern_type"       : "REVERSAL | CONTINUATION | LIQUIDITY_SWEEP | NEUTRAL",
                "pattern_name"       : str (e.g. "Bullish Pin Bar"),
                "direction_bias"     : "BULLISH | BEARISH | NEUTRAL",
                "candle_quality"     : float (0-100),
                "upper_wick_ratio"   : float,
                "lower_wick_ratio"   : float,
                "body_ratio"         : float,
                "liquidity_sweep"    : bool
            }
        """
        if df is None or df.empty or len(df) < 3:
            return self._empty()

        try:
            feat = df if "atr" in df.columns else compute_features(df)
            c0 = feat.iloc[-1]   # current candle
            c1 = feat.iloc[-2]   # previous candle
            c2 = feat.iloc[-3]   # candle before that

            def parse(row, key, default=0.0):
                v = row.get(key, default)
                return float(v) if v is not None else default

            # ── Candle Geometry ──────────────────────────────────────────────
            open0  = parse(c0, "open")
            close0 = parse(c0, "close")
            high0  = parse(c0, "high")
            low0   = parse(c0, "low")
            open1  = parse(c1, "open")
            close1 = parse(c1, "close")
            high1  = parse(c1, "high")
            low1   = parse(c1, "low")

            candle_range = max(high0 - low0, 1e-9)
            body = abs(close0 - open0)
            upper_wick = high0 - max(open0, close0)
            lower_wick = min(open0, close0) - low0

            upper_wick_ratio = upper_wick / candle_range
            lower_wick_ratio = lower_wick / candle_range
            body_ratio = body / candle_range

            is_bullish_candle = close0 > open0

            # ── Pattern Detection ─────────────────────────────────────────────
            pattern_type = "NEUTRAL"
            pattern_name = "No Pattern"
            direction_bias = "NEUTRAL"
            candle_quality = 30.0

            # Pin Bar (Reversal): long wick one side, small body
            if lower_wick_ratio >= 0.60 and body_ratio <= 0.25:
                pattern_type = "REVERSAL"
                pattern_name = "Bullish Pin Bar"
                direction_bias = "BULLISH"
                candle_quality = 70.0 + lower_wick_ratio * 30.0

            elif upper_wick_ratio >= 0.60 and body_ratio <= 0.25:
                pattern_type = "REVERSAL"
                pattern_name = "Bearish Pin Bar"
                direction_bias = "BEARISH"
                candle_quality = 70.0 + upper_wick_ratio * 30.0

            # Engulfing (Reversal)
            elif (
                body >= abs(close1 - open1) * 1.5 and
                is_bullish_candle and not (close1 > open1) and
                body_ratio >= 0.55
            ):
                pattern_type = "REVERSAL"
                pattern_name = "Bullish Engulfing"
                direction_bias = "BULLISH"
                candle_quality = 75.0

            elif (
                body >= abs(close1 - open1) * 1.5 and
                not is_bullish_candle and (close1 > open1) and
                body_ratio >= 0.55
            ):
                pattern_type = "REVERSAL"
                pattern_name = "Bearish Engulfing"
                direction_bias = "BEARISH"
                candle_quality = 75.0

            # Doji (Indecision)
            elif body_ratio < 0.10 and upper_wick_ratio > 0.3 and lower_wick_ratio > 0.3:
                pattern_type = "NEUTRAL"
                pattern_name = "Doji (Indecision)"
                direction_bias = "NEUTRAL"
                candle_quality = 40.0

            # Momentum / Marubozu (Continuation)
            elif body_ratio >= 0.75 and is_bullish_candle:
                pattern_type = "CONTINUATION"
                pattern_name = "Bullish Momentum Candle"
                direction_bias = "BULLISH"
                candle_quality = 65.0 + body_ratio * 20.0

            elif body_ratio >= 0.75 and not is_bullish_candle:
                pattern_type = "CONTINUATION"
                pattern_name = "Bearish Momentum Candle"
                direction_bias = "BEARISH"
                candle_quality = 65.0 + body_ratio * 20.0

            # Inside Bar (Compression / Continuation Setup)
            elif high0 <= high1 and low0 >= low1:
                pattern_type = "CONTINUATION"
                pattern_name = "Inside Bar (Compression)"
                direction_bias = "NEUTRAL"
                candle_quality = 55.0

            # ── Liquidity Sweep Detection ────────────────────────────────────
            atr_val = float(c0.get("atr", 1.0))
            # A wick that exceeds the prior candle's high/low by 0.5x ATR then closes back = sweep
            prior_high = max(high1, float(c2.get("high", high1)))
            prior_low  = min(low1, float(c2.get("low", low1)))

            bullish_sweep = (low0 < prior_low - atr_val * 0.2) and (close0 > open1)
            bearish_sweep = (high0 > prior_high + atr_val * 0.2) and (close0 < open1)

            liquidity_sweep = bool(bullish_sweep or bearish_sweep)
            if liquidity_sweep:
                if bearish_sweep:
                    pattern_name = "Bearish Liquidity Sweep"
                    direction_bias = "BEARISH"
                    pattern_type = "LIQUIDITY_SWEEP"
                else:
                    pattern_name = "Bullish Liquidity Sweep"
                    direction_bias = "BULLISH"
                    pattern_type = "LIQUIDITY_SWEEP"
                candle_quality = max(candle_quality, 72.0)

            candle_quality = float(np.clip(candle_quality, 0.0, 100.0))

            return {
                "pattern_type":     pattern_type,
                "pattern_name":     pattern_name,
                "direction_bias":   direction_bias,
                "candle_quality":   round(candle_quality, 1),
                "upper_wick_ratio": round(upper_wick_ratio, 3),
                "lower_wick_ratio": round(lower_wick_ratio, 3),
                "body_ratio":       round(body_ratio, 3),
                "liquidity_sweep":  liquidity_sweep,
            }

        except Exception:
            return self._empty()

    def _empty(self) -> dict:
        return {
            "pattern_type":     "NEUTRAL",
            "pattern_name":     "No Pattern",
            "direction_bias":   "NEUTRAL",
            "candle_quality":   0.0,
            "upper_wick_ratio": 0.0,
            "lower_wick_ratio": 0.0,
            "body_ratio":       0.0,
            "liquidity_sweep":  False,
        }
