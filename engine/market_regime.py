"""
engine/market_regime.py
Deterministic market regime detection engine for NexusBot V2.

Input : OHLCV DataFrame (ideally H1 for macro context)
Output: Regime dictionary describing current market state.
"""
import numpy as np
import pandas as pd

from engine.feature_engineering import compute_features


REGIME_TRENDING = "TRENDING"
REGIME_RANGING = "RANGING"
REGIME_VOLATILE = "VOLATILE"
REGIME_LOW_VOLATILITY = "LOW_VOLATILITY"
REGIME_COMPRESSED = "COMPRESSED"
REGIME_EXHAUSTED = "EXHAUSTED"
REGIME_SESSION_VOLATILITY = "SESSION_VOLATILITY"
REGIME_REVERSAL = "REVERSAL"
REGIME_TRAP_ENVIRONMENT = "TRAP_ENVIRONMENT"
REGIME_HIGH_LIQUIDITY_HUNT = "HIGH_LIQUIDITY_HUNT"
REGIME_PANIC = "PANIC"
REGIME_ABSORPTION = "ABSORPTION"

DIR_BULLISH = "BULLISH"
DIR_BEARISH = "BEARISH"
DIR_NEUTRAL = "NEUTRAL"


class MarketRegimeEngine:
    """
    Classifies the current market regime from a feature-engineered DataFrame.

    Algorithm:
      1. Volatility layer    - ATR/ATR_mean ratio
      2. Trend strength      - ADX
      3. Direction           - EMA alignment + VWAP bias
      4. Persistence         - HH/HL or LH/LL structure
      5. Breakout probability- Compression score inversion
    """

    ADX_STRONG_TREND = 25.0
    ADX_WEAK_TREND = 18.0
    ATR_VOLATILE_RATIO = 1.40
    ATR_COMPRESS_RATIO = 0.70
    ATR_PANIC_RATIO = 2.20
    EXHAUSTION_PERSISTENCE = 0.75
    REVERSAL_SLOPE_THRESHOLD = 0.02
    SESSION_VOLATILITY_SCORE = 75.0
    ABSORPTION_BODY_RATIO = 0.35
    SWEEP_RISK_THRESHOLD = 65.0
    TRAP_RISK_THRESHOLD = 55.0

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def detect(self, df: pd.DataFrame) -> dict:
        """
        Runs regime detection on the provided DataFrame.

        Returns a backward-compatible regime payload with additive V3 fields.
        """
        if df is None or df.empty or len(df) < 50:
            return self._empty_regime()

        try:
            feat = compute_features(df)
            row = feat.iloc[-1]

            adx_val = float(row.get("adx", 0.0) or 0.0)
            atr_val = float(row.get("atr", 0.0) or 0.0)
            atr_mean_val = float(row.get("atr_mean", atr_val) or atr_val)
            ema_fast = float(row.get("ema_fast", 0.0) or 0.0)
            ema_slow = float(row.get("ema_slow", 0.0) or 0.0)
            vwap_val = float(row.get("vwap", 0.0) or 0.0)
            close_val = float(row.get("close", 0.0) or 0.0)
            comp_score = float(row.get("compression_score", 1.0) or 1.0)
            vol_score = float(row.get("volatility_score", 50.0) or 50.0)
            ema_slope_val = float(row.get("ema_slope", 0.0) or 0.0)

            atr_ratio = atr_val / max(atr_mean_val, 1e-9)

            if atr_ratio > self.ATR_VOLATILE_RATIO and adx_val > self.ADX_WEAK_TREND:
                regime = REGIME_VOLATILE
            elif atr_ratio < self.ATR_COMPRESS_RATIO:
                regime = REGIME_LOW_VOLATILITY
            elif adx_val >= self.ADX_STRONG_TREND:
                regime = REGIME_TRENDING
            else:
                regime = REGIME_RANGING

            ema_bullish = ema_fast > ema_slow
            vwap_bullish = close_val > vwap_val if vwap_val > 0 else None
            slope_positive = ema_slope_val > 0

            bullish_votes = sum([
                ema_bullish,
                vwap_bullish is True,
                slope_positive,
            ])
            bearish_votes = sum([
                not ema_bullish,
                vwap_bullish is False,
                not slope_positive,
            ])

            if bullish_votes >= 2:
                direction = DIR_BULLISH
            elif bearish_votes >= 2:
                direction = DIR_BEARISH
            else:
                direction = DIR_NEUTRAL

            trend_strength = float(np.clip(adx_val, 0, 100))
            trend_persistence = self._calculate_persistence(feat, direction)

            breakout_probability = float(np.clip(1.0 - comp_score + 0.2, 0.0, 1.0))
            if regime == REGIME_VOLATILE:
                breakout_probability = min(breakout_probability + 0.3, 1.0)

            volatility_state = self._classify_volatility_state(atr_ratio=atr_ratio, vol_score=vol_score)
            structure_state = self._classify_structure_state(
                feat=feat,
                direction=direction,
                trend_persistence=trend_persistence,
                ema_slope_val=ema_slope_val,
            )
            liquidity_state = self._classify_liquidity_state(feat=feat)
            regime_flags = self._build_regime_flags(
                regime=regime,
                direction=direction,
                atr_ratio=atr_ratio,
                trend_persistence=trend_persistence,
                ema_slope_val=ema_slope_val,
                comp_score=comp_score,
                volatility_state=volatility_state,
                liquidity_state=liquidity_state,
                structure_state=structure_state,
                feat=feat,
            )
            market_state = self._select_market_state(base_regime=regime, flags=regime_flags)

            return {
                "regime": regime,
                "market_state": market_state,
                "direction": direction,
                "trend_strength": round(trend_strength, 2),
                "volatility_score": round(float(np.clip(vol_score, 0, 100)), 2),
                "breakout_probability": round(breakout_probability, 3),
                "trend_persistence": round(trend_persistence, 3),
                "regime_flags": regime_flags,
                "liquidity_state": liquidity_state,
                "volatility_state": volatility_state,
                "structure_state": structure_state,
                "_adx": round(adx_val, 2),
                "_atr_ratio": round(atr_ratio, 3),
                "_compression_score": round(comp_score, 3),
                "_direction_bullish_votes": bullish_votes,
            }

        except Exception as exc:
            return {**self._empty_regime(), "_error": str(exc)}

    def _calculate_persistence(self, feat: pd.DataFrame, direction: str) -> float:
        tail = feat.tail(20)
        if tail.empty:
            return 0.5
        if direction == DIR_BULLISH:
            count = int(tail["hh"].sum())
        elif direction == DIR_BEARISH:
            count = int(tail["ll"].sum())
        else:
            count = int((tail["hh"] | tail["ll"]).sum())
        return float(np.clip(count / 20.0, 0.0, 1.0))

    def _classify_volatility_state(self, atr_ratio: float, vol_score: float) -> dict:
        if atr_ratio >= self.ATR_PANIC_RATIO:
            label = REGIME_PANIC
        elif atr_ratio >= self.ATR_VOLATILE_RATIO:
            label = REGIME_SESSION_VOLATILITY if vol_score >= self.SESSION_VOLATILITY_SCORE else REGIME_VOLATILE
        elif atr_ratio <= self.ATR_COMPRESS_RATIO:
            label = REGIME_COMPRESSED
        else:
            label = REGIME_LOW_VOLATILITY if vol_score <= 35.0 else "NORMAL"
        return {
            "label": label,
            "atr_ratio": round(float(atr_ratio), 3),
            "volatility_score": round(float(np.clip(vol_score, 0, 100)), 2),
        }

    def _classify_structure_state(
        self,
        feat: pd.DataFrame,
        direction: str,
        trend_persistence: float,
        ema_slope_val: float,
    ) -> dict:
        slope_abs = abs(float(ema_slope_val))
        if direction == DIR_NEUTRAL:
            label = "BALANCED"
        elif trend_persistence >= self.EXHAUSTION_PERSISTENCE and slope_abs < self.REVERSAL_SLOPE_THRESHOLD:
            label = REGIME_EXHAUSTED
        elif trend_persistence <= 0.30 and slope_abs >= self.REVERSAL_SLOPE_THRESHOLD:
            label = REGIME_REVERSAL
        else:
            label = "CONTINUATION"

        tail = feat.tail(5)
        hh_count = int(tail["hh"].sum()) if "hh" in tail else 0
        ll_count = int(tail["ll"].sum()) if "ll" in tail else 0
        return {
            "label": label,
            "direction": direction,
            "trend_persistence": round(float(trend_persistence), 3),
            "ema_slope": round(float(ema_slope_val), 4),
            "recent_hh_count": hh_count,
            "recent_ll_count": ll_count,
        }

    def _classify_liquidity_state(self, feat: pd.DataFrame) -> dict:
        tail = feat.tail(6).copy()
        if tail.empty:
            return {"label": "NORMAL", "sweep_risk": 0.0, "absorption_score": 0.0, "volume_ratio": 1.0}

        rng = (tail["high"] - tail["low"]).replace(0, np.nan)
        body = (tail["close"] - tail["open"]).abs()
        upper_wick = tail["high"] - tail[["close", "open"]].max(axis=1)
        lower_wick = tail[["close", "open"]].min(axis=1) - tail["low"]
        wick_ratio = ((upper_wick + lower_wick) / rng).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        body_ratio = (body / rng).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        volume_ratio = self._safe_volume_ratio(tail)

        sweep_risk = float(np.clip(wick_ratio.tail(3).mean() * 100.0, 0.0, 100.0))
        absorption_score = float(
            np.clip(((1.0 - body_ratio.tail(3).mean()) * max(volume_ratio, 1.0)) * 50.0, 0.0, 100.0)
        )

        if absorption_score >= 65.0 and body_ratio.tail(3).mean() <= self.ABSORPTION_BODY_RATIO:
            label = REGIME_ABSORPTION
        elif sweep_risk >= self.SWEEP_RISK_THRESHOLD and volume_ratio >= 1.10:
            label = REGIME_HIGH_LIQUIDITY_HUNT
        elif sweep_risk >= self.TRAP_RISK_THRESHOLD:
            label = REGIME_TRAP_ENVIRONMENT
        else:
            label = "NORMAL"

        return {
            "label": label,
            "sweep_risk": round(sweep_risk, 2),
            "absorption_score": round(absorption_score, 2),
            "volume_ratio": round(float(volume_ratio), 3),
        }

    def _build_regime_flags(
        self,
        regime: str,
        direction: str,
        atr_ratio: float,
        trend_persistence: float,
        ema_slope_val: float,
        comp_score: float,
        volatility_state: dict,
        liquidity_state: dict,
        structure_state: dict,
        feat: pd.DataFrame,
    ) -> list:
        flags = {regime}
        flags.add(volatility_state.get("label", "NORMAL"))
        flags.add(liquidity_state.get("label", "NORMAL"))
        flags.add(structure_state.get("label", "BALANCED"))

        if comp_score >= 0.70 or volatility_state.get("label") == REGIME_COMPRESSED:
            flags.add(REGIME_COMPRESSED)
        if atr_ratio >= self.ATR_PANIC_RATIO:
            flags.add(REGIME_PANIC)
        if structure_state.get("label") == REGIME_EXHAUSTED:
            flags.add(REGIME_EXHAUSTED)
        if structure_state.get("label") == REGIME_REVERSAL:
            flags.add(REGIME_REVERSAL)
        if liquidity_state.get("label") == REGIME_TRAP_ENVIRONMENT:
            flags.add(REGIME_TRAP_ENVIRONMENT)
        if liquidity_state.get("label") == REGIME_HIGH_LIQUIDITY_HUNT:
            flags.add(REGIME_HIGH_LIQUIDITY_HUNT)
        if liquidity_state.get("label") == REGIME_ABSORPTION:
            flags.add(REGIME_ABSORPTION)
        if volatility_state.get("label") == REGIME_SESSION_VOLATILITY:
            flags.add(REGIME_SESSION_VOLATILITY)

        tail = feat.tail(4)
        if not tail.empty:
            close_delta = float(tail["close"].iloc[-1] - tail["close"].iloc[0])
            atr_tail_mean = float(tail["atr"].mean()) if "atr" in tail else 0.0
            if direction == DIR_BULLISH and close_delta < 0 and abs(ema_slope_val) >= self.REVERSAL_SLOPE_THRESHOLD:
                flags.add(REGIME_REVERSAL)
            elif direction == DIR_BEARISH and close_delta > 0 and abs(ema_slope_val) >= self.REVERSAL_SLOPE_THRESHOLD:
                flags.add(REGIME_REVERSAL)
            if trend_persistence >= self.EXHAUSTION_PERSISTENCE and abs(close_delta) < atr_tail_mean:
                flags.add(REGIME_EXHAUSTED)

        return sorted(flag for flag in flags if flag not in {"NORMAL", "BALANCED", "CONTINUATION"})

    @staticmethod
    def _select_market_state(base_regime: str, flags: list) -> str:
        priority = [
            REGIME_PANIC,
            REGIME_ABSORPTION,
            REGIME_HIGH_LIQUIDITY_HUNT,
            REGIME_TRAP_ENVIRONMENT,
            REGIME_REVERSAL,
            REGIME_EXHAUSTED,
            REGIME_SESSION_VOLATILITY,
            REGIME_COMPRESSED,
            REGIME_VOLATILE,
            REGIME_TRENDING,
            REGIME_RANGING,
            REGIME_LOW_VOLATILITY,
        ]
        for label in priority:
            if label in flags:
                return label
        return base_regime

    @staticmethod
    def _safe_volume_ratio(df: pd.DataFrame) -> float:
        if "volume" not in df.columns or len(df) < 2:
            return 1.0
        base = float(df["volume"].iloc[:-1].mean() or 0.0)
        if base <= 0:
            return 1.0
        return float(df["volume"].iloc[-1] / base)

    @staticmethod
    def _empty_regime() -> dict:
        return {
            "regime": REGIME_RANGING,
            "market_state": REGIME_RANGING,
            "direction": DIR_NEUTRAL,
            "trend_strength": 0.0,
            "volatility_score": 50.0,
            "breakout_probability": 0.5,
            "trend_persistence": 0.5,
            "regime_flags": [REGIME_RANGING],
            "liquidity_state": {
                "label": "NORMAL",
                "sweep_risk": 0.0,
                "absorption_score": 0.0,
                "volume_ratio": 1.0,
            },
            "volatility_state": {
                "label": REGIME_LOW_VOLATILITY,
                "atr_ratio": 1.0,
                "volatility_score": 50.0,
            },
            "structure_state": {
                "label": "BALANCED",
                "direction": DIR_NEUTRAL,
                "trend_persistence": 0.5,
                "ema_slope": 0.0,
                "recent_hh_count": 0,
                "recent_ll_count": 0,
            },
        }
