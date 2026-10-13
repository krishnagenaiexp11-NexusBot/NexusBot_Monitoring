"""
engine/signal_quality.py
Signal Quality Assessment Engine for NexusBot V3.

Evaluates the quality, cleanliness, and reliability of the current
trading signal by checking for confluence, noise levels, and divergence.
Fully deterministic — no AI.
"""
import numpy as np
import pandas as pd
from engine.feature_engineering import compute_features


class SignalQualityEngine:
    """
    Measures signal health by combining:
    - Confluence count (how many indicators agree)
    - Noise level (ATR relative to price move)
    - Divergence flags (RSI vs price direction)
    - EMA confluence quality
    - Volume participation quality
    """

    def analyze(self, df: pd.DataFrame, direction: str = "NEUTRAL") -> dict:
        """
        Assesses signal quality on the provided DataFrame (base timeframe).

        Args:
            df        : Feature-engineered OHLCV DataFrame.
            direction : Expected trade direction (BULLISH/BEARISH/NEUTRAL).

        Returns:
            {
                "confluence_count"  : int  (0-6, higher = more aligned signals),
                "noise_level"       : float (0-100, lower = cleaner signal),
                "rsi_divergence"    : bool  (price moving opposite to RSI),
                "ema_confluence"    : bool  (fast above slow, slope matching direction),
                "volume_quality"    : "STRONG | MODERATE | WEAK",
                "signal_quality_score": float (0-100)
            }
        """
        if df is None or df.empty or len(df) < 15:
            return self._empty()

        try:
            feat = df if "ema_fast" in df.columns else compute_features(df)
            row = feat.iloc[-1]
            tail = feat.tail(10)

            # ── 1. Confluence Count ──────────────────────────────────────────────
            is_bullish = direction == "BULLISH"
            is_bearish = direction == "BEARISH"
            confluence = 0

            ema_fast = float(row.get("ema_fast", 0.0))
            ema_slow = float(row.get("ema_slow", 0.0))
            ema_slope_val = float(row.get("ema_slope", 0.0))
            rsi_val = float(row.get("rsi", 50.0))
            close_val = float(row.get("close", 0.0))
            vwap_val = float(row.get("vwap", 0.0))
            momentum_val = float(row.get("momentum", 0.0))
            volume_ratio_val = float(row.get("volume_ratio", 1.0))
            adx_val = float(row.get("adx", 0.0))

            # EMA alignment
            if is_bullish and ema_fast > ema_slow and ema_slope_val > 0:
                confluence += 1
            elif is_bearish and ema_fast < ema_slow and ema_slope_val < 0:
                confluence += 1

            # RSI alignment (not overextended, trending in direction)
            if is_bullish and 45.0 <= rsi_val <= 70.0:
                confluence += 1
            elif is_bearish and 30.0 <= rsi_val <= 55.0:
                confluence += 1

            # VWAP bias alignment
            if vwap_val > 0:
                if is_bullish and close_val > vwap_val:
                    confluence += 1
                elif is_bearish and close_val < vwap_val:
                    confluence += 1

            # Momentum alignment
            if is_bullish and momentum_val > 0:
                confluence += 1
            elif is_bearish and momentum_val < 0:
                confluence += 1

            # Volume participation
            if volume_ratio_val >= 1.10:
                confluence += 1

            # ADX trend present
            if adx_val >= 20.0:
                confluence += 1

            confluence_count = min(confluence, 6)

            # ── 2. Noise Level ───────────────────────────────────────────────────
            # Noise = ATR relative to overall price range (last 10 bars)
            atr_val = float(row.get("atr", 0.0))
            price_range_10 = float(tail["close"].max() - tail["close"].min())
            if price_range_10 > 0:
                noise_ratio = atr_val / price_range_10
                noise_level = float(np.clip(noise_ratio * 100.0, 0.0, 100.0))
            else:
                noise_level = 50.0

            # ── 3. RSI Divergence ─────────────────────────────────────────────────
            # Price trending up but RSI trending down (bearish divergence) or vice versa
            price_diff = float(tail["close"].diff(5).iloc[-1]) if len(tail) >= 6 else 0.0
            rsi_diff = float(tail["rsi"].diff(5).iloc[-1]) if "rsi" in tail.columns and len(tail) >= 6 else 0.0
            rsi_divergence = bool(
                (price_diff > 0 and rsi_diff < -2.0) or
                (price_diff < 0 and rsi_diff > 2.0)
            )

            # ── 4. EMA Confluence ─────────────────────────────────────────────────
            if is_bullish:
                ema_confluence = bool(ema_fast > ema_slow and ema_slope_val > 0)
            elif is_bearish:
                ema_confluence = bool(ema_fast < ema_slow and ema_slope_val < 0)
            else:
                ema_confluence = False

            # ── 5. Volume Quality ─────────────────────────────────────────────────
            if volume_ratio_val >= 1.30:
                volume_quality = "STRONG"
            elif volume_ratio_val >= 1.05:
                volume_quality = "MODERATE"
            else:
                volume_quality = "WEAK"

            # ── 6. Signal Quality Score ───────────────────────────────────────────
            score = (confluence_count / 6.0) * 50.0       # up to 50 points
            score += (1.0 - noise_level / 100.0) * 20.0   # up to 20 points
            if ema_confluence:
                score += 15.0
            if not rsi_divergence:
                score += 10.0
            if volume_quality == "STRONG":
                score += 5.0
            elif volume_quality == "MODERATE":
                score += 2.0

            signal_quality_score = float(np.clip(score, 0.0, 100.0))

            return {
                "confluence_count": confluence_count,
                "noise_level": round(noise_level, 1),
                "rsi_divergence": rsi_divergence,
                "ema_confluence": ema_confluence,
                "volume_quality": volume_quality,
                "signal_quality_score": round(signal_quality_score, 1),
            }

        except Exception:
            return self._empty()

    def _empty(self) -> dict:
        return {
            "confluence_count": 0,
            "noise_level": 50.0,
            "rsi_divergence": False,
            "ema_confluence": False,
            "volume_quality": "WEAK",
            "signal_quality_score": 0.0,
        }
