"""
engine/mtf_context.py
Multi-Timeframe Context Engine for NexusBot V2.

Builds hierarchical market context between H1 structure and M15 execution conditions.
All logic is fully deterministic (no AI).
"""
import numpy as np
import pandas as pd

from engine.feature_engineering import compute_features


class MTFContextEngine:
    """
    Analyzes H1 macro structure and M15 execution dynamics to compute
    alignment, execution quality, and entry confidence.
    """

    def analyze(self, h1_df: pd.DataFrame, m15_df: pd.DataFrame) -> dict:
        """
        Builds the hierarchical multi-timeframe context.

        Args:
            h1_df  : H1 OHLCV DataFrame (historical series)
            m15_df : M15 OHLCV DataFrame (historical series)

        Returns:
            A structured dictionary containing H1 structure, M15 execution,
            and alignment scores.
        """
        if h1_df is None or h1_df.empty or len(h1_df) < 30:
            h1_struct = self._empty_h1_structure()
        else:
            h1_struct = self._analyze_h1_structure(h1_df)

        if m15_df is None or m15_df.empty or len(m15_df) < 20:
            m15_exec = self._empty_m15_execution()
        else:
            m15_exec = self._analyze_m15_execution(m15_df, h1_struct)

        # ── Alignment Score (0-100) ───────────────────────────────────────────
        alignment_score = self._calculate_alignment(h1_struct, m15_exec)

        return {
            "h1_structure": h1_struct,
            "m15_execution": m15_exec,
            "alignment_score": round(alignment_score, 1),
            "context_label": self._build_context_label(h1_struct, alignment_score),
        }

    # ── Internal Analysis Layers ──────────────────────────────────────────────

    def _analyze_h1_structure(self, h1_df: pd.DataFrame) -> dict:
        """Analyzes H1 structure for macro trend, volatility, and bias."""
        feat = h1_df if "ema_fast" in h1_df.columns else compute_features(h1_df)
        row = feat.iloc[-1]
        tail = feat.tail(20)

        # 1. Structure Direction (EMA alignment + VWAP bias + EMA Slope)
        close_val = float(row.get("close", 0.0))
        vwap_val = float(row.get("vwap", 0.0))
        ema_fast = float(row.get("ema_fast", 0.0))
        ema_slow = float(row.get("ema_slow", 0.0))
        ema_slope_val = float(row.get("ema_slope", 0.0))

        ema_bullish = ema_fast > ema_slow
        vwap_bullish = close_val > vwap_val if vwap_val > 0 else True
        slope_positive = ema_slope_val > 0

        bullish_votes = sum([ema_bullish, vwap_bullish, slope_positive])
        bearish_votes = sum([not ema_bullish, not vwap_bullish, not slope_positive])

        if bullish_votes >= 2:
            direction = "BULLISH"
        elif bearish_votes >= 2:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        # 2. Trend Strength (ADX)
        adx_val = float(row.get("adx", 0.0) or 0.0)
        trend_strength = float(np.clip(adx_val, 0.0, 100.0))

        # 3. Trend Persistence (HH/LL over last 20 H1 bars)
        if direction == "BULLISH":
            persistence_count = int(tail["hh"].sum())
        elif direction == "BEARISH":
            persistence_count = int(tail["ll"].sum())
        else:
            persistence_count = int((tail["hh"] | tail["ll"]).sum())
        trend_persistence = float(np.clip(persistence_count / 20.0, 0.0, 1.0))

        # 4. Volatility State (ATR vs ATR mean ratio)
        atr_val = float(row.get("atr", 0.0) or 1.0)
        atr_mean_val = float(row.get("atr_mean", atr_val) or atr_val)
        atr_ratio = atr_val / max(atr_mean_val, 1e-9)

        if atr_ratio > 1.4:
            volatility_state = "HIGH"
        elif atr_ratio < 0.7:
            volatility_state = "LOW"
        else:
            volatility_state = "NORMAL"

        # 5. Macro Regime
        if atr_ratio > 1.4 and adx_val > 18.0:
            macro_regime = "VOLATILE"
        elif atr_ratio < 0.7:
            macro_regime = "LOW_VOLATILITY"
        elif adx_val >= 25.0:
            macro_regime = "TRENDING"
        else:
            macro_regime = "RANGING"

        # 6. Breakout Bias (Based on compression and momentum bias)
        comp_score = float(row.get("compression_score", 1.0) or 1.0)
        if comp_score < 0.8:
            breakout_bias = "BULLISH" if close_val > vwap_val else "BEARISH"
        else:
            breakout_bias = "NEUTRAL"

        return {
            "structure_direction": direction,
            "trend_strength": round(trend_strength, 1),
            "trend_persistence": round(trend_persistence, 2),
            "volatility_state": volatility_state,
            "macro_regime": macro_regime,
            "breakout_bias": breakout_bias,
            "_adx": round(adx_val, 2),
            "_atr_ratio": round(atr_ratio, 3),
            "_compression_score": round(comp_score, 3),
            "_direction_bullish_votes": int(bullish_votes),
        }

    def _analyze_m15_execution(self, m15_df: pd.DataFrame, h1_struct: dict) -> dict:
        """Analyzes M15 execution layer for pullback, momentum, and readiness."""
        feat = m15_df if "ema_fast" in m15_df.columns else compute_features(m15_df)
        row = feat.iloc[-1]
        tail = feat.tail(10)

        # 1. Pullback Quality
        # Orderly pullback means price retraces toward EMA slow without breaking structure
        h1_dir = h1_struct.get("structure_direction", "NEUTRAL")
        close_val = float(row.get("close", 0.0))
        ema_slow = float(row.get("ema_slow", 0.0))
        atr_val = float(row.get("atr", 0.0) or 1.0)

        if h1_dir == "BULLISH":
            # Pullback is high quality if close is above ema_slow but within 1.5 ATRs of it (re-testing EMA slow)
            dist = close_val - ema_slow
            if dist > 0:
                pullback_quality = float(np.clip(1.0 - (dist / (atr_val * 2.0)), 0.3, 1.0))
            else:
                pullback_quality = 0.3  # broken below EMA slow
            # Penalize for recent lower lows (breaks structural support)
            if tail["ll"].sum() > 2:
                pullback_quality = max(0.1, pullback_quality - 0.3)
        elif h1_dir == "BEARISH":
            dist = ema_slow - close_val
            if dist > 0:
                pullback_quality = float(np.clip(1.0 - (dist / (atr_val * 2.0)), 0.3, 1.0))
            else:
                pullback_quality = 0.3  # broken above EMA slow
            if tail["hh"].sum() > 2:
                pullback_quality = max(0.1, pullback_quality - 0.3)
        else:
            pullback_quality = 0.5  # Neutral macro has no pullbacks

        # 2. Momentum Alignment (M15 RSI & EMA slope vs H1 direction)
        rsi_val = float(row.get("rsi", 50.0) or 50.0)
        ema_slope_val = float(row.get("ema_slope", 0.0) or 0.0)

        if h1_dir == "BULLISH":
            rsi_align = np.clip((rsi_val - 40.0) / 30.0, 0.0, 1.0)
            slope_align = 1.0 if ema_slope_val > 0 else 0.2
            momentum_alignment = (rsi_align + slope_align) / 2.0
        elif h1_dir == "BEARISH":
            rsi_align = np.clip((60.0 - rsi_val) / 30.0, 0.0, 1.0)
            slope_align = 1.0 if ema_slope_val < 0 else 0.2
            momentum_alignment = (rsi_align + slope_align) / 2.0
        else:
            # For ranging, alignment is higher when RSI is mean-reverting (near extremes but turning back)
            dist_50 = abs(rsi_val - 50.0)
            momentum_alignment = float(np.clip(dist_50 / 25.0, 0.2, 0.8))

        # 3. Trigger Ready (M15 compression score and recent volume expansion)
        comp_score = float(row.get("compression_score", 1.0) or 1.0)
        vol_ratio = float(row.get("volume_ratio", 1.0) or 1.0)

        # Trigger ready if compressed (< 0.8) and volume expands (> 1.25)
        trigger_ready = bool(comp_score < 0.8 and vol_ratio > 1.25)

        # 4. Entry Confidence (0-100)
        # Combines pullback, momentum alignment, and compression state
        if h1_dir in ("BULLISH", "BEARISH"):
            entry_conf = (pullback_quality * 40.0) + (momentum_alignment * 40.0)
            if trigger_ready:
                entry_conf += 20.0
            else:
                # Add partial compression credit
                entry_conf += (1.0 - comp_score) * 20.0
        else:
            # Ranging entry confidence
            entry_conf = (momentum_alignment * 60.0) + (1.0 - abs(comp_score - 1.0)) * 40.0

        entry_confidence = float(np.clip(entry_conf, 10.0, 95.0))

        # 5. Execution Quality (0-100)
        exec_qual = (pullback_quality * 35.0) + (momentum_alignment * 35.0) + (vol_ratio / 2.0 * 30.0)
        execution_quality = float(np.clip(exec_qual, 15.0, 98.0))

        return {
            "execution_quality": round(execution_quality, 1),
            "pullback_quality": round(pullback_quality, 2),
            "momentum_alignment": round(momentum_alignment, 2),
            "trigger_ready": trigger_ready,
            "entry_confidence": round(entry_confidence, 1),
            "_m15_rsi": round(rsi_val, 1),
            "_m15_vol_ratio": round(vol_ratio, 2),
            "_m15_compression": round(comp_score, 2),
        }

    # ── Alignment Computation & Labeling ──────────────────────────────────────

    def _calculate_alignment(self, h1_struct: dict, m15_exec: dict) -> float:
        """Computes the MTF alignment score (0-100) between H1 and M15."""
        h1_dir = h1_struct.get("structure_direction", "NEUTRAL")
        h1_regime = h1_struct.get("macro_regime", "RANGING")
        h1_strength = h1_struct.get("trend_strength", 50.0)

        m15_align = m15_exec.get("momentum_alignment", 0.5)
        m15_pullback = m15_exec.get("pullback_quality", 0.5)
        m15_conf = m15_exec.get("entry_confidence", 50.0)

        if h1_regime == "TRENDING":
            # Trending needs macro direction aligned with M15 pullback and momentum
            score = (h1_strength * 0.3) + (m15_pullback * 35.0) + (m15_align * 35.0)
        elif h1_regime == "VOLATILE":
            # Volatile needs strong breakout triggers and alignment
            score = (m15_conf * 0.5) + (m15_align * 50.0)
        elif h1_regime == "RANGING":
            # Ranging favors mean reversion (low ADX trend strength is good)
            score = (100.0 - h1_strength) * 0.4 + m15_align * 60.0
        else:  # LOW_VOLATILITY
            score = 30.0 + m15_align * 30.0

        # Adjust score if directions are completely opposed (e.g. H1 Bullish, M15 Bearish momentum)
        if h1_dir == "BULLISH" and m15_exec.get("_m15_rsi", 50) < 40:
            score *= 0.6
        elif h1_dir == "BEARISH" and m15_exec.get("_m15_rsi", 50) > 60:
            score *= 0.6

        return float(np.clip(score, 10.0, 100.0))

    def _build_context_label(self, h1_struct: dict, alignment_score: float) -> str:
        """Generates a human-readable context label for the UI."""
        direction = h1_struct.get("structure_direction", "NEUTRAL")
        regime = h1_struct.get("macro_regime", "RANGING")

        if alignment_score >= 75:
            qual = "Strong"
        elif alignment_score >= 45:
            qual = "Moderate"
        else:
            qual = "Weak"

        return f"{qual} {direction.title()} {regime.replace('_', ' ').title()}"

    # ── Fallback / Empty States ───────────────────────────────────────────────

    def _empty_h1_structure(self) -> dict:
        return {
            "structure_direction": "NEUTRAL",
            "trend_strength": 0.0,
            "trend_persistence": 0.0,
            "volatility_state": "NORMAL",
            "macro_regime": "RANGING",
            "breakout_bias": "NEUTRAL",
            "_adx": 0.0,
            "_atr_ratio": 1.0,
            "_compression_score": 1.0,
        }

    def _empty_m15_execution(self) -> dict:
        return {
            "execution_quality": 50.0,
            "pullback_quality": 0.5,
            "momentum_alignment": 0.5,
            "trigger_ready": False,
            "entry_confidence": 50.0,
            "_m15_rsi": 50.0,
            "_m15_vol_ratio": 1.0,
            "_m15_compression": 1.0,
        }
