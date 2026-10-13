"""
engine/signal_saturation.py
Signal Saturation Engine for NexusBot V3.

Identifies correlated signal clusters and prevents confirmation bias
from stacking metrics that measure the same underlying phenomenon.

Groups:
  VOLATILITY_EXPANSION_CLUSTER : ATR expansion, BB width, volatility score
  MOMENTUM_STRENGTH_CLUSTER    : RSI increase, momentum, positive EMA slope
  COMPRESSION_CLUSTER          : compression rating, ATR contraction, inside bars

Computes effective_signal_count and saturation_penalty.
Fully deterministic — no AI.
"""
import numpy as np


class SignalSaturationEngine:
    """
    Prevents metric inflation by collapsing correlated signal groups.

    For each cluster, the maximum of 1 effective signal is counted.
    Additional signals in the same cluster are "redundant" and add to saturation.
    """

    def analyze(
        self,
        signal_quality: dict,
        h4_structure: dict,
        regime_transition: dict,
        m5_execution: dict,
    ) -> dict:
        """
        Computes effective signal count and saturation penalty.

        Args:
            signal_quality    : From SignalQualityEngine
            h4_structure      : From H4StructureEngine
            regime_transition : From RegimeTransitionEngine
            m5_execution      : From M5ExecutionEngine

        Returns:
            {
                "effective_signal_count" : int (1-6),
                "raw_signal_count"       : int,
                "saturation_penalty"     : float (0-20),
                "cluster_activations"    : dict,
                "saturation_level"       : "NORMAL | MODERATE | HIGH"
            }
        """
        sq = signal_quality or {}
        h4 = h4_structure or {}
        trans = regime_transition or {}
        m5 = m5_execution or {}

        # ── Extract indicators ────────────────────────────────────────────────
        confluence = int(sq.get("confluence_count", 0))
        noise_level = float(sq.get("noise_level", 50.0))
        vol_quality = sq.get("volume_quality", "MODERATE")
        ema_confluence = bool(sq.get("ema_confluence", False))
        rsi_div = bool(sq.get("rsi_divergence", False))

        macro_str = float(h4.get("macro_strength", 0.0))
        exhaustion = float(h4.get("exhaustion_risk", 50.0))

        expansion_ph = bool(trans.get("expansion_phase", False))
        compression_ph = bool(trans.get("compression_phase", False))
        vol_score_trans = float(trans.get("breakout_loading", 0.0))

        m5_timing = float(m5.get("m5_timing_score", 50.0))
        vol_confirm = bool(m5.get("volume_confirmation", False))
        mom_aligned = bool(m5.get("momentum_aligned", False))

        # ── Cluster Definitions ───────────────────────────────────────────────
        # VOLATILITY_EXPANSION_CLUSTER
        vol_cluster_signals = [
            expansion_ph,                       # ATR expansion
            vol_score_trans > 50.0,             # Breakout loading (volatility related)
            noise_level > 60.0,                 # High noise (ATR-derived)
        ]
        vol_cluster_active = sum(vol_cluster_signals)

        # MOMENTUM_STRENGTH_CLUSTER
        mom_cluster_signals = [
            ema_confluence,                     # EMA alignment (momentum-based)
            mom_aligned,                        # M5 momentum aligned
            macro_str >= 25.0,                  # ADX strong (momentum proxy)
        ]
        mom_cluster_active = sum(mom_cluster_signals)

        # COMPRESSION_CLUSTER
        comp_cluster_signals = [
            compression_ph,                     # Compression phase
            vol_quality == "WEAK",              # Volume contraction
            not expansion_ph and macro_str < 18.0,  # Low ATR + weak ADX
        ]
        comp_cluster_active = sum(comp_cluster_signals)

        # CONFIRMATION_CLUSTER (stacking same-type confirmations)
        conf_cluster_signals = [
            confluence >= 4,                    # High confluence count
            not rsi_div,                        # RSI not diverging
            vol_confirm,                        # Volume confirming
        ]
        conf_cluster_active = sum(conf_cluster_signals)

        cluster_activations = {
            "volatility_expansion": vol_cluster_active,
            "momentum_strength":    mom_cluster_active,
            "compression":          comp_cluster_active,
            "confirmation_stack":   conf_cluster_active,
        }

        # ── Raw vs Effective Signal Count ─────────────────────────────────────
        # Raw = sum of all active signals across clusters
        raw_signal_count = (
            vol_cluster_active +
            mom_cluster_active +
            comp_cluster_active +
            conf_cluster_active
        )

        # Effective = only 1 per cluster counts (collapse redundancy)
        effective_signal_count = sum([
            1 if vol_cluster_active > 0 else 0,
            1 if mom_cluster_active > 0 else 0,
            1 if comp_cluster_active > 0 else 0,
            1 if conf_cluster_active > 0 else 0,
        ])

        # M5 timing and H4 macro as standalone independent signals
        if m5_timing > 60.0:
            effective_signal_count = min(effective_signal_count + 1, 6)
        if macro_str >= 25.0 and exhaustion < 50.0:
            effective_signal_count = min(effective_signal_count + 1, 6)

        # ── Saturation Penalty ─────────────────────────────────────────────────
        # If raw >> effective, signals are correlated/redundant
        redundant_signals = max(0, raw_signal_count - effective_signal_count)
        saturation_penalty = min(redundant_signals * 4.0, 20.0)

        # ── Saturation Level ───────────────────────────────────────────────────
        if redundant_signals <= 1:
            saturation_level = "NORMAL"
        elif redundant_signals <= 3:
            saturation_level = "MODERATE"
        else:
            saturation_level = "HIGH"

        return {
            "effective_signal_count": effective_signal_count,
            "raw_signal_count": raw_signal_count,
            "saturation_penalty": round(saturation_penalty, 1),
            "cluster_activations": cluster_activations,
            "saturation_level": saturation_level,
        }
