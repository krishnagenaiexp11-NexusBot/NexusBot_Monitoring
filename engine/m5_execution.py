"""
engine/m5_execution.py
M5 Precision Timing Engine for NexusBot V3.

Analyzes the M5 timeframe to identify micro-entry windows, candle momentum
alignment, spread quality, and volume confirmation for precise execution timing.
All logic is fully deterministic — no AI.
"""
import numpy as np
import pandas as pd
from engine.feature_engineering import compute_features


class M5ExecutionEngine:
    """
    Analyzes M5 OHLCV data to produce precision timing context:
    - Micro momentum direction
    - Entry window quality
    - Candle body ratio
    - Volume confirmation
    - Spread proxy quality
    """

    def analyze(self, m5_df: pd.DataFrame, h1_direction: str = "NEUTRAL") -> dict:
        """
        Runs M5 precision timing analysis.

        Args:
            m5_df        : M5 OHLCV DataFrame (feature-engineered or raw).
            h1_direction : Macro direction string from H1 structure (BULLISH/BEARISH/NEUTRAL).

        Returns:
            {
                "micro_direction"     : "BULLISH | BEARISH | NEUTRAL",
                "momentum_aligned"    : bool,
                "entry_window_quality": float (0-100),
                "candle_body_ratio"   : float (0-1),
                "volume_confirmation" : bool,
                "spread_quality"      : "TIGHT | NORMAL | WIDE",
                "m5_timing_score"     : float (0-100)
            }
        """
        if m5_df is None or m5_df.empty or len(m5_df) < 10:
            return self._empty()

        try:
            df = m5_df if "ema_fast" in m5_df.columns else compute_features(m5_df)
            row = df.iloc[-1]

            # ── 1. Micro Direction (EMA alignment) ─────────────────────────────
            ema_fast = float(row.get("ema_fast", 0.0))
            ema_slow = float(row.get("ema_slow", 0.0))
            ema_slope_val = float(row.get("ema_slope", 0.0))

            if ema_fast > ema_slow and ema_slope_val > 0:
                micro_direction = "BULLISH"
            elif ema_fast < ema_slow and ema_slope_val < 0:
                micro_direction = "BEARISH"
            else:
                micro_direction = "NEUTRAL"

            # ── 2. H1 alignment check ───────────────────────────────────────────
            momentum_aligned = (micro_direction == h1_direction) and (micro_direction != "NEUTRAL")

            # ── 3. Candle Body Ratio (body/range) ──────────────────────────────
            open_val = float(row.get("open", 0.0))
            close_val = float(row.get("close", 0.0))
            high_val = float(row.get("high", 0.0))
            low_val = float(row.get("low", 0.0))
            candle_range = max(high_val - low_val, 1e-9)
            body = abs(close_val - open_val)
            candle_body_ratio = float(np.clip(body / candle_range, 0.0, 1.0))

            # ── 4. Volume Confirmation ──────────────────────────────────────────
            volume_ratio_val = float(row.get("volume_ratio", 1.0))
            volume_confirmation = volume_ratio_val >= 1.05

            # ── 5. Spread Quality (ATR proxy) ───────────────────────────────────
            atr_val = float(row.get("atr", 0.0))
            atr_mean_val = float(row.get("atr_mean", 1.0))
            atr_ratio = atr_val / max(atr_mean_val, 1e-9)

            if atr_ratio < 0.6:
                spread_quality = "TIGHT"
            elif atr_ratio > 1.6:
                spread_quality = "WIDE"
            else:
                spread_quality = "NORMAL"

            # ── 6. Entry Window Quality Score (0-100) ──────────────────────────
            score = 40.0  # base

            # Body confirmation
            score += candle_body_ratio * 20.0

            # Volume bonus
            if volume_confirmation:
                score += 15.0

            # Alignment with H1
            if momentum_aligned:
                score += 20.0

            # Spread quality bonus
            if spread_quality == "TIGHT":
                score += 5.0
            elif spread_quality == "WIDE":
                score -= 15.0

            # RSI not overextended
            rsi_val = float(row.get("rsi", 50.0))
            if 35.0 <= rsi_val <= 65.0:
                score += 10.0
            elif rsi_val > 75.0 or rsi_val < 25.0:
                score -= 10.0

            entry_window_quality = float(np.clip(score, 0.0, 100.0))

            # ── 7. M5 Timing Score (comprehensive) ─────────────────────────────
            m5_timing_score = entry_window_quality

            return {
                "micro_direction": micro_direction,
                "momentum_aligned": momentum_aligned,
                "entry_window_quality": round(entry_window_quality, 1),
                "candle_body_ratio": round(candle_body_ratio, 3),
                "volume_confirmation": volume_confirmation,
                "spread_quality": spread_quality,
                "m5_timing_score": round(m5_timing_score, 1),
            }

        except Exception:
            return self._empty()

    def _empty(self) -> dict:
        return {
            "micro_direction": "NEUTRAL",
            "momentum_aligned": False,
            "entry_window_quality": 0.0,
            "candle_body_ratio": 0.0,
            "volume_confirmation": False,
            "spread_quality": "NORMAL",
            "m5_timing_score": 0.0,
        }
