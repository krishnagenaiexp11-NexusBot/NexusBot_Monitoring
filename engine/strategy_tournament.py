"""
engine/strategy_tournament.py
Strategy Tournament Engine for NexusBot V3.
"""
import numpy as np
from engine.strategy_registry import AVAILABLE_STRATEGIES
from engine.tournament_models import TournamentInput


H4_MACRO_WEIGHT = 0.20
H1_CONTEXT_WEIGHT = 0.25
M15_EXECUTION_WEIGHT = 0.20
M5_TIMING_WEIGHT = 0.15
CANDLESTICK_WEIGHT = 0.10
SESSION_WEIGHT = 0.10


STRATEGY_DNA = {
    "Elder Swing": ["Trend following", "Swing", "EMA Confluence", "Multitimeframe"],
    "Breakout Hunter": ["Momentum", "Expansion", "London Session", "Volatility Breakout"],
    "Mean Reversion": ["Counter-trend", "Mean Reversion", "Overbought/Oversold", "Low Volatility"],
    "Aggressive Scalper": ["Scalping", "M5 Micro Timing", "High Liquidity", "Fast Execution"],
    "Spike Catcher": ["Mean Reversion", "Momentum Exhaustion", "Volatility Sweep", "News Spike"],
    "Exhaustion Reversal": ["Counter-trend", "Exhaustion", "Decaying Persistence", "Volatility Rejection"],
    "Trap Reversal": ["Reversal", "False Breakout", "Liquidity Sweep", "Trap Environment"],
    "FVG Reaction": ["Continuation", "Imbalance Fill", "Fair Value Gap", "Volatility Expansion"],
    "Dead Cat Bounce": ["Counter-trend", "Panic Rebound", "Capitulation Liquidity", "ATR Expansion"],
    "Absorption": ["Institutional", "Volume Block", "Volatility Compression", "Absorption Zone"],
}


class StrategyTournamentEngine:
    """
    Strategy ranking engine using the typed TournamentInput contract.
    """

    def _validate_inputs(self, tournament_input: TournamentInput):
        if not isinstance(tournament_input, TournamentInput):
            raise ValueError(
                f"Invalid input type: expected TournamentInput, got {type(tournament_input).__name__}."
            )
        if tournament_input.h4_structure is None or not isinstance(tournament_input.h4_structure, dict):
            raise ValueError("TournamentInput missing h4_structure context.")
        if not tournament_input.execution_readiness or not isinstance(tournament_input.execution_readiness, dict):
            raise ValueError("TournamentInput missing execution_readiness context.")
        if not tournament_input.mtf_context or not isinstance(tournament_input.mtf_context, dict):
            raise ValueError("TournamentInput missing mtf_context.")
        if tournament_input.candlestick_intelligence is None or not isinstance(tournament_input.candlestick_intelligence, dict):
            raise ValueError("TournamentInput candlestick_intelligence is None.")
        if not tournament_input.candlestick_intelligence:
            raise ValueError("TournamentInput candlestick_intelligence is empty.")
        if "macro_strength" not in tournament_input.h4_structure:
            raise ValueError("TournamentInput h4_structure missing trend strength 'macro_strength' key.")
        if "execution_state" not in tournament_input.execution_readiness:
            raise ValueError("TournamentInput execution_readiness missing deployment state 'execution_state' key.")

    def rank(self, tournament_input: TournamentInput, eligible_strategies: list | None = None) -> list:
        """
        Runs the institutional tournament and returns ranked results.

        Backward compatibility:
          - If `eligible_strategies` is omitted or empty, the full registry is ranked.
          - Output payload shape remains unchanged.
        """
        self._validate_inputs(tournament_input)

        h4 = tournament_input.h4_structure
        mtf = tournament_input.mtf_context
        m5 = tournament_input.m5_execution
        session = tournament_input.session_context
        candle = tournament_input.candlestick_intelligence
        readiness = tournament_input.execution_readiness

        contra = tournament_input.contradiction_state or {}
        risk = tournament_input.institutional_risk or {}
        conf = tournament_input.confidence_hierarchy or {}
        sat = tournament_input.signal_saturation or {}

        exhaustion_risk = float(h4.get("exhaustion_risk", 50.0))
        trend_age = int(h4.get("trend_age", 0))
        liquidity = session.get("session_liquidity", "MEDIUM")
        is_overlap = bool(session.get("is_overlap", False))
        m5_timing = float(m5.get("m5_timing_score", 50.0))

        h1_struct = mtf.get("h1_structure", {})
        current_regime = h1_struct.get("macro_regime", "RANGING")
        current_market_state = h1_struct.get("market_state", current_regime)
        regime_dict = {"regime": current_regime, "market_state": current_market_state}

        strategy_pool = eligible_strategies or AVAILABLE_STRATEGIES
        results = []

        for strategy in strategy_pool:
            strategy_name = strategy.get_strategy_name()
            if hasattr(strategy, "get_confidence_breakdown"):
                base_score = float(strategy.score_market_fit(tournament_input))
            else:
                base_score = float(strategy.score_market_fit(regime_dict))
            supported = self._is_supported(strategy, current_regime=current_regime, current_market_state=current_market_state)

            h4_score = 50.0
            macro_dir = h4.get("macro_direction", "NEUTRAL")
            macro_str = float(h4.get("macro_strength", 0.0))
            if macro_dir != "NEUTRAL":
                h4_score += 20.0
            else:
                h4_score -= 10.0
            h4_score += (macro_str / 40.0) * 20.0
            h4_score -= (exhaustion_risk - 50.0) * 0.4

            is_trend_strategy = strategy_name in ["Elder Swing", "Breakout Hunter"]
            if is_trend_strategy:
                if macro_dir in ["BULLISH", "BEARISH"] and macro_str > 20.0:
                    h4_score += 15.0
                elif macro_dir == "NEUTRAL":
                    h4_score -= 20.0
            else:
                if macro_dir == "NEUTRAL" or macro_str < 15.0:
                    h4_score += 15.0
                else:
                    h4_score -= 20.0
            h4_score = float(np.clip(h4_score, 0.0, 100.0))

            alignment_score = float(mtf.get("alignment_score", 50.0))
            confluence_count = int(readiness.get("confluence_count", 0))
            if confluence_count == 0:
                confluence_count = int(session.get("is_overlap", False)) * 2 + 2

            h1_score = alignment_score
            h1_score += (confluence_count / 6.0) * 40.0
            if supported:
                h1_score += 10.0
            else:
                h1_score -= 20.0
            h1_score = float(np.clip(h1_score, 0.0, 100.0))

            m15_struct = mtf.get("m15_execution", {})
            pullback_quality = float(m15_struct.get("pullback_quality", 0.5))
            trigger_ready = bool(m15_struct.get("trigger_ready", False))

            m15_score = pullback_quality * 50.0 + (50.0 if trigger_ready else 10.0)
            if is_trend_strategy and pullback_quality > 0.6:
                m15_score += 15.0
            elif not is_trend_strategy and pullback_quality < 0.4:
                m15_score += 10.0
            m15_score = float(np.clip(m15_score, 0.0, 100.0))

            m5_score = m5_timing
            if strategy_name == "Aggressive Scalper":
                m5_score = m5_timing * 1.2
            m5_score = float(np.clip(m5_score, 0.0, 100.0))

            candle_quality = float(candle.get("candle_quality", 50.0))
            candle_bias = candle.get("direction_bias", "NEUTRAL")
            candle_score = candle_quality
            if is_trend_strategy:
                if candle_bias == macro_dir and macro_dir != "NEUTRAL":
                    candle_score += 20.0
                elif candle_bias != macro_dir and macro_dir != "NEUTRAL" and candle_bias != "NEUTRAL":
                    candle_score -= 20.0
            else:
                if candle_bias != macro_dir and macro_dir != "NEUTRAL":
                    candle_score += 15.0
            candle_score = float(np.clip(candle_score, 0.0, 100.0))

            session_score = 0.0
            if liquidity == "HIGH":
                session_score += 70.0
            elif liquidity == "MEDIUM":
                session_score += 40.0
            else:
                session_score += 10.0
            if is_overlap:
                session_score += 30.0
            if strategy_name == "Aggressive Scalper":
                if liquidity == "HIGH" or is_overlap:
                    session_score += 10.0
                else:
                    session_score -= 20.0
            session_score = float(np.clip(session_score, 0.0, 100.0))

            weighted_score = (
                h4_score * H4_MACRO_WEIGHT
                + h1_score * H1_CONTEXT_WEIGHT
                + m15_score * M15_EXECUTION_WEIGHT
                + m5_score * M5_TIMING_WEIGHT
                + candle_score * CANDLESTICK_WEIGHT
                + session_score * SESSION_WEIGHT
            )

            contradiction_penalty = float(contra.get("deployment_penalty", 0.0))
            saturation_penalty = float(sat.get("saturation_penalty", 0.0))
            fatigue_penalty = max(0.0, (exhaustion_risk - 50.0) * 0.25)
            late_entry_penalty = max(0.0, (trend_age - 20) * 0.3) if trend_age > 20 else 0.0
            liquidity_penalty = 8.0 if liquidity == "LOW" else (3.0 if liquidity == "MEDIUM" else 0.0)
            sess_vol = float(session.get("session_volatility", 0.1))
            volatility_penalty = 10.0 if sess_vol < 0.02 else 0.0
            candle_penalty = max(0.0, (60.0 - candle_quality) * 0.2) if candle_quality < 60.0 else 0.0
            confidence_score = float(conf.get("weighted_confidence_score", 100.0))
            confidence_penalty = max(0.0, (70.0 - confidence_score) * 0.25) if confidence_score < 70.0 else 0.0

            total_penalty = (
                contradiction_penalty
                + saturation_penalty
                + fatigue_penalty
                + late_entry_penalty
                + liquidity_penalty
                + volatility_penalty
                + candle_penalty
                + confidence_penalty
            )
            if not supported:
                total_penalty += 30.0

            fit_score = base_score * 0.3 + weighted_score * 0.7 - total_penalty
            fit_score = float(np.clip(fit_score, 0.0, 100.0))

            timing_quality = m5_timing
            candlestick_alignment = candle_score
            structural_risk = float(risk.get("risk_score", exhaustion_risk))

            if fit_score >= 80.0 and structural_risk < 45.0:
                deployment_bias = "READY"
            elif fit_score < 50.0 or structural_risk >= 70.0:
                deployment_bias = "AVOID"
            else:
                deployment_bias = "WATCHLIST"

            dna_tags = STRATEGY_DNA.get(strategy_name, ["Quantitative", "Orchestrated", "Nexus V3"])

            results.append({
                "strategy": strategy_name,
                "strategy_name": strategy_name,
                "market_fit_score": round(fit_score, 1),
                "fit_score": round(fit_score, 1),
                "supported": supported,
                "supported_regimes": strategy.get_supported_regimes(),
                "regime_match": supported,
                "deployment_bias": deployment_bias,
                "fatigue_penalty": round(fatigue_penalty + late_entry_penalty, 1),
                "timing_quality": round(timing_quality, 1),
                "candlestick_alignment": round(candlestick_alignment, 1),
                "structural_risk": round(structural_risk, 1),
                "contradiction_penalty": round(contradiction_penalty, 1),
                "saturation_penalty": round(saturation_penalty, 1),
                "dna_tags": dna_tags,
                "confidence_breakdown": strategy.get_confidence_breakdown(tournament_input) if hasattr(strategy, "get_confidence_breakdown") else None,
                "score_breakdown": {
                    "base": round(base_score, 1),
                    "h4_bonus": round(h4_score * H4_MACRO_WEIGHT, 1),
                    "h1_bonus": round(h1_score * H1_CONTEXT_WEIGHT, 1),
                    "m15_bonus": round(m15_score * M15_EXECUTION_WEIGHT, 1),
                    "m5_bonus": round(m5_score * M5_TIMING_WEIGHT, 1),
                    "session_bonus": round(session_score * SESSION_WEIGHT, 1),
                    "candle_bonus": round(candle_score * CANDLESTICK_WEIGHT, 1),
                    "fatigue_pen": -round(fatigue_penalty + late_entry_penalty, 1),
                    "lateness_pen": -round(late_entry_penalty, 1),
                    "noise_pen": -round(candle_penalty, 1),
                    "liquidity_pen": -round(liquidity_penalty, 1),
                },
                "_strategy_obj": strategy,
            })

        results.sort(key=lambda x: x["market_fit_score"], reverse=True)
        for idx, item in enumerate(results, 1):
            item["rank"] = idx
        return results

    @staticmethod
    def _is_supported(strategy, current_regime: str, current_market_state: str) -> bool:
        supported_states = []
        if hasattr(strategy, "get_supported_market_states"):
            try:
                supported_states = list(strategy.get_supported_market_states() or [])
            except Exception:
                supported_states = []
        supported_regimes = list(strategy.get_supported_regimes() or [])
        allowed = {str(item).upper() for item in supported_states + supported_regimes}
        return (
            str(current_regime).upper() in allowed
            or str(current_market_state).upper() in allowed
        )

    @staticmethod
    def get_recommended(results: list) -> dict | None:
        if not results:
            return None
        return results[0]

    @staticmethod
    def strip_internal_fields(results: list) -> list:
        clean = []
        for item in results:
            clean.append({k: v for k, v in item.items() if not k.startswith("_")})
        return clean
