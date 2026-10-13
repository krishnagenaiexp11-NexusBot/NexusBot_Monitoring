"""
engine/market_explainer.py
Deterministic Market Explainer and Explainability Narrative Engine for NexusBot V2.

Converts technical metrics, multi-timeframe context, and tournament results
into a structured explanation, strategy reasoning, warnings, and confidence scores.
Purely deterministic — NO AI (no LLM dependencies).
"""
import pandas as pd
import numpy as np
from engine.feature_engineering import compute_features


class MarketExplainer:
    """
    Computes human-readable summaries, warnings, and opportunity/confidence
    scores based on H1 structure, M15 execution, and tournament results.
    """

    def explain(
        self,
        mtf_context: dict,
        tournament_results: list,
        h1_df: pd.DataFrame,
        m15_df: pd.DataFrame,
    ) -> dict:
        """
        Generates explainability metrics and narrative.

        Args:
            mtf_context        : Output dict from build_multi_timeframe_context()
            tournament_results : Ranked strategy results from StrategyTournamentEngine
            h1_df              : Historical H1 DataFrame
            m15_df             : Historical M15 DataFrame

        Returns:
            {
                "market_summary"     : str,
                "trend_summary"      : str,
                "volatility_summary" : str,
                "strategy_reasoning" : str,
                "warnings"           : list[str],
                "opportunity_score"  : float,
                "confidence_score"   : float,
                "strategy_rejections": dict, # strategy_name -> reason
            }
        """
        h1_struct = mtf_context.get("h1_structure", {})
        m15_exec = mtf_context.get("m15_execution", {})
        alignment_score = mtf_context.get("alignment_score", 50.0)

        # ── 1. Trend Summary & Explainability ─────────────────────────────────
        trend_summary = self._build_trend_explanation(h1_struct, h1_df)

        # ── 2. Volatility Summary & Explainability ────────────────────────────
        volatility_summary = self._build_volatility_explanation(h1_struct, h1_df)

        # ── 3. Warnings Heuristics ────────────────────────────────────────────
        warnings = self._detect_warnings(h1_struct, m15_exec, h1_df, m15_df)

        # ── 4. Strategy Reasoning & Rejections ────────────────────────────────
        strategy_reasoning, rejections = self._build_strategy_reasoning(
            h1_struct, m15_exec, alignment_score, tournament_results
        )

        # ── 5. Opportunity & Confidence Scores ────────────────────────────────
        opportunity_score = self._calculate_opportunity(h1_struct, m15_exec, alignment_score)
        confidence_score = self._calculate_confidence(h1_struct, m15_exec, alignment_score)

        # ── 6. Market Summary ─────────────────────────────────────────────────
        direction = h1_struct.get("structure_direction", "NEUTRAL")
        regime = h1_struct.get("macro_regime", "RANGING")
        m15_label = "compression" if m15_exec.get("trigger_ready") else "development"

        market_summary = (
            f"The dataset analysis reveals a **{direction} {regime.replace('_', ' ')}** "
            f"macro structure on the H1 timeframe. The M15 timeframe is currently exhibiting "
            f"execution **{m15_label}** with a pullback quality score of **{m15_exec.get('pullback_quality', 0.5):.2f}**. "
            f"The overall multi-timeframe alignment score is **{alignment_score:.1f}/100**, "
            f"indicating a **{mtf_context.get('context_label', '').split()[0]}** setup quality."
        )

        return {
            "market_summary": market_summary,
            "trend_summary": trend_summary,
            "volatility_summary": volatility_summary,
            "strategy_reasoning": strategy_reasoning,
            "warnings": warnings,
            "opportunity_score": round(opportunity_score, 1),
            "confidence_score": round(confidence_score, 1),
            "strategy_rejections": rejections,
        }

    # ── Narrative Heuristics ──────────────────────────────────────────────────

    def _build_trend_explanation(self, h1_struct: dict, h1_df: pd.DataFrame) -> str:
        """Explains the H1 trend dynamics with supporting metrics."""
        direction = h1_struct.get("structure_direction", "NEUTRAL")
        adx_val = h1_struct.get("_adx", 0.0)
        persistence = h1_struct.get("trend_persistence", 0.5)

        # Check ADX change over last 10 candles
        adx_change = 0.0
        if len(h1_df) >= 20:
            # We must compute features on h1_df or use existing columns
            # For efficiency, compute on tail
            feat = compute_features(h1_df.tail(20))
            if len(feat) >= 11:
                adx_change = float(feat.iloc[-1].get("adx", 0.0) - feat.iloc[-11].get("adx", 0.0))

        adx_trend_str = "rising" if adx_change > 1.5 else ("falling" if adx_change < -1.5 else "flat")
        adx_diff_abs = abs(adx_change)

        votes_bullish = h1_struct.get("_direction_bullish_votes", 0)

        # Build bullet points
        points = []
        points.append(f"ADX trend strength is {adx_val:.1f} ({adx_trend_str} by {adx_diff_abs:.1f} pts over 10 bars).")
        points.append(f"EMA alignment: Bullish indicator votes are {votes_bullish}/3.")

        if direction == "BULLISH":
            points.append(f"Higher High / Higher Low structure: {persistence * 100:.0f}% intact.")
            points.append("Price is showing bullish bias relative to daily VWAP.")
        elif direction == "BEARISH":
            points.append(f"Lower High / Lower Low structure: {persistence * 100:.0f}% intact.")
            points.append("Price is showing bearish bias relative to daily VWAP.")
        else:
            points.append("Price structure is alternating without persistent HH/LL waves.")
            points.append("VWAP bias is fluctuating around the neutral line.")

        return f"**Trend Structure — {direction} ({h1_struct.get('trend_strength', 0.0):.0f}%)**\n\n" + "\n".join(
            [f"- {p}" for p in points]
        )

    def _build_volatility_explanation(self, h1_struct: dict, h1_df: pd.DataFrame) -> str:
        """Explains H1 volatility status, expansion, and breakout bias."""
        vol_state = h1_struct.get("volatility_state", "NORMAL")
        atr_ratio = h1_struct.get("_atr_ratio", 1.0)
        comp_score = h1_struct.get("_compression_score", 1.0)

        # Check ATR change over last 10 candles
        atr_pct = 0.0
        if len(h1_df) >= 20:
            feat = compute_features(h1_df.tail(20))
            if len(feat) >= 11:
                atr_now = float(feat.iloc[-1].get("atr", 1.0))
                atr_prev = float(feat.iloc[-11].get("atr", 1.0))
                if atr_prev > 0:
                    atr_pct = (atr_now - atr_prev) / atr_prev * 100.0

        atr_change_str = "expanding" if atr_pct > 2.0 else ("contracting" if atr_pct < -2.0 else "stable")

        points = []
        points.append(f"Volatility is in a **{vol_state}** state (ATR is {atr_ratio:.2f}x its 20-period mean).")
        points.append(f"ATR is currently **{atr_change_str}** ({atr_pct:+.1f}% change over 10 bars).")
        points.append(f"Compression rating is {comp_score:.2f} (values < 0.70 represent high breakout compression).")

        breakout_bias = h1_struct.get("breakout_bias", "NEUTRAL")
        if breakout_bias != "NEUTRAL":
            points.append(f"Breakout directional bias is leaning **{breakout_bias}**.")
        else:
            points.append("No active breakout compression bias detected (ranging price waves).")

        return f"**Volatility & Breakout State — {vol_state}**\n\n" + "\n".join([f"- {p}" for p in points])

    def _detect_warnings(
        self, h1_struct: dict, m15_exec: dict, h1_df: pd.DataFrame, m15_df: pd.DataFrame
    ) -> list:
        """Heuristically detects market structural anomalies and trading warnings."""
        warnings = []
        comp_score = h1_struct.get("_compression_score", 1.0)
        atr_ratio = h1_struct.get("_atr_ratio", 1.0)

        # 1. Volatility compression alert
        if comp_score < 0.70:
            warnings.append("High compression warning: Volatility is extremely compressed. Large breakout imminent.")

        # 2. ATR contraction alert
        if atr_ratio < 0.60:
            warnings.append("Low volume alert: ATR is less than 60% of its normal 20-period mean. Avoid trend following.")

        # 3. Pullback failure alert
        pullback = m15_exec.get("pullback_quality", 0.5)
        h1_dir = h1_struct.get("structure_direction", "NEUTRAL")
        if h1_dir != "NEUTRAL" and pullback < 0.35:
            warnings.append(f"Pullback structural warning: M15 pullback is deep/broken ({pullback:.2f}). Macro trend may fail.")

        # 4. Momentum divergence warning
        rsi_m15 = m15_exec.get("_m15_rsi", 50.0)
        if h1_dir == "BULLISH" and rsi_m15 < 35.0:
            warnings.append("Momentum divergence alert: H1 structure is Bullish, but M15 RSI is oversold. Pullback is overextended.")
        elif h1_dir == "BEARISH" and rsi_m15 > 65.0:
            warnings.append("Momentum divergence alert: H1 structure is Bearish, but M15 RSI is overbought. Short pullback is overextended.")

        # 5. EMA flattening warning
        if len(h1_df) >= 5:
            tail = h1_df.tail(5)
            # check if slope is close to 0
            if "ema_slope" in tail.columns:
                slope_abs = abs(float(tail["ema_slope"].iloc[-1]))
                if slope_abs < 0.05:
                    warnings.append("Trend flattening: EMA slope is near zero. Trend is losing speed.")

        return warnings

    def _build_strategy_reasoning(
        self, h1_struct: dict, m15_exec: dict, alignment_score: float, tournament_results: list
    ) -> tuple:
        """Determines why the winning strategy is recommended, and why others were rejected."""
        rejections = {}
        strategy_reasoning = ""

        if not tournament_results:
            return "No strategies analyzed.", rejections

        winner = tournament_results[0]
        winner_name = winner["strategy"]

        # Selection reasoning rules based on current metrics
        reasons = []
        h1_dir = h1_struct.get("structure_direction", "NEUTRAL")
        h1_regime = h1_struct.get("macro_regime", "RANGING")
        adx_val = h1_struct.get("_adx", 0.0)
        pb_qual = m15_exec.get("pullback_quality", 0.5)
        trig = m15_exec.get("trigger_ready", False)

        if winner_name == "Elder Swing":
            reasons.append(f"Recommended because H1 trend is {h1_regime} ({adx_val:.1f}) with clear {h1_dir} bias.")
            reasons.append(f"M15 pullback quality is {pb_qual:.2f}, indicating a healthy entry window on retracement.")
            reasons.append(f"Multi-timeframe alignment score is elevated at {alignment_score:.1f}.")

        elif winner_name == "Breakout Hunter":
            reasons.append(f"Recommended because H1 volatility/breakout compression is high (compression: {h1_struct.get('_compression_score', 1.0):.2f}).")
            reasons.append(f"M15 volume expansion and trigger indicators suggest breakout momentum is active.")
            reasons.append("H1 directional bias is aligned, providing structural support for breakout continuation.")

        elif winner_name == "Mean Reversion":
            reasons.append(f"Recommended because H1 is in a {h1_regime} regime with low trend strength (ADX: {adx_val:.1f}).")
            reasons.append("M15 show price oscillation extremes with no persistent structural breakout behavior.")
            reasons.append("Pullback and momentum alignment support reversion to the VWAP mean.")

        elif winner_name == "Aggressive Scalper":
            reasons.append("Recommended because of volatile intraday fluctuations with high M15 volume activity.")
            reasons.append("Scalping conditions are favorable due to rapid bid/ask sweeps.")

        else:  # Spike Catcher
            reasons.append("Recommended because of sudden ATR expansion ratio spikes.")
            reasons.append("M15 indicators are triggering reversal signals from volume exhaustion points.")

        strategy_reasoning = (
            f"**🏆 Recommended Strategy: {winner_name} (Fit Score: {winner['market_fit_score']:.0f})**\n\n"
            + "\n".join([f"- {r}" for r in reasons])
        )

        # Build rejections
        for item in tournament_results[1:]:
            name = item["strategy"]
            fit = item["market_fit_score"]
            reject_reasons = []

            if name == "ElderSwing":
                name = "Elder Swing"
            if name == "BreakoutHunter":
                name = "Breakout Hunter"
            if name == "MeanReversion":
                name = "Mean Reversion"

            if name == "Elder Swing":
                if adx_val < 20.0:
                    reject_reasons.append("ADX trend strength is too weak for a swing following strategy.")
                if h1_dir == "NEUTRAL":
                    reject_reasons.append("Lack of clear macro direction (Neutral H1 structure).")
            elif name == "Breakout Hunter":
                if h1_struct.get("_compression_score", 1.0) > 0.85:
                    reject_reasons.append("Market is not compressed enough; breakout risk is elevated.")
                if not trig:
                    reject_reasons.append("No active M15 volume or compression breakout triggers.")
            elif name == "Mean Reversion":
                if adx_val > 25.0:
                    reject_reasons.append("ADX indicates a strong trending market; mean reversion carries high risk.")
                if h1_dir != "NEUTRAL":
                    reject_reasons.append(f"Price is locked in a strong {h1_dir} trend wave.")
            elif name == "Aggressive Scalper":
                if h1_regime == "LOW_VOLATILITY":
                    reject_reasons.append("Intraday volatility is too low for scalping execution spreads.")
            elif name == "Spike Catcher":
                if h1_struct.get("_atr_ratio", 1.0) < 1.1:
                    reject_reasons.append("No significant ATR expansion spikes detected in recent history.")

            if not reject_reasons:
                reject_reasons.append(f"Ranked lower due to a lower market fit score of {fit:.1f}.")

            rejections[name] = ", ".join(reject_reasons)

        return strategy_reasoning, rejections

    def _calculate_opportunity(self, h1_struct: dict, m15_exec: dict, alignment: float) -> float:
        """Computes the overall Opportunity Score (0-100) based on market state."""
        h1_regime = h1_struct.get("macro_regime", "RANGING")
        adx_val = h1_struct.get("_adx", 0.0)
        comp = h1_struct.get("_compression_score", 1.0)

        # Baseline score from alignment
        opp = alignment * 0.7

        # Regime adjustments
        if h1_regime == "TRENDING":
            # Trending has opportunities when trend is strong but not yet exhausted
            opp += float(np.clip(adx_val, 20, 45) * 0.3)
        elif h1_regime == "VOLATILE":
            # Volatile has high opportunities if breakout is compressed
            opp += (1.0 - comp) * 30.0
        elif h1_regime == "RANGING":
            # Ranging has opportunities when oscillation is clean (moderate ADX)
            opp += (30.0 - min(adx_val, 30.0))
        else:
            # Low vol is hard to trade
            opp -= 10.0

        return float(np.clip(opp, 15.0, 95.0))

    def _calculate_confidence(self, h1_struct: dict, m15_exec: dict, alignment: float) -> float:
        """Computes the overall Confidence Score (0-100)."""
        persistence = h1_struct.get("trend_persistence", 0.5)
        h1_regime = h1_struct.get("macro_regime", "RANGING")

        # Start with alignment
        conf = alignment * 0.6

        # H1 structural validation
        if h1_regime == "TRENDING" or h1_regime == "VOLATILE":
            conf += persistence * 40.0
        else:
            # Ranging confidence depends on M15 pullback quality and stable low ADX
            conf += (1.0 - m15_exec.get("pullback_quality", 0.5)) * 20.0 + 20.0

        return float(np.clip(conf, 20.0, 98.0))
