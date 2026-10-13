"""
deployment/auto_trade_engine.py
Automated trade deployment orchestrator for NexusBot V3.
"""
import logging
import math
import time
import pandas as pd
import numpy as np
from engine.strategy_registry import get_strategy_by_name, AVAILABLE_STRATEGIES
from engine.strategy_tournament import StrategyTournamentEngine
from engine.tournament_models import TournamentInput
from engine.execution_engine import ExecutionEngine
from engine.trade_manager import TradeManager
from deployment.deployment_profile import AutoTradeDeploymentProfile, get_preset
from deployment.execution_intent import ExecutionIntent
from deployment.live_state_manager import LiveStateManager

# V3 Execution Hardening Imports
from deployment.execution_quality import ExecutionQualityEngine
from deployment.market_stress import MarketStressIndex
from deployment.deployment_governor import DeploymentGovernor
from deployment.capital_efficiency import CapitalEfficiencyEngine
from storage.decision_trace import DecisionTraceEngine

logger = logging.getLogger("AutoTradeEngine")


class AutoTradeEngine:
    """
    Orchestrates live market evaluation, tournament verification, risk checks,
    and automatic deployment of trade intents.
    """

    def __init__(self, state_manager: LiveStateManager | None = None):
        self.state = state_manager or LiveStateManager()
        self.tournament_engine = StrategyTournamentEngine()
        self.execution_engine = ExecutionEngine()
        self.trade_manager = TradeManager()
        self.profile = get_preset("Momentum Moderate")
        self.balance = 10000.0
        self.governor = DeploymentGovernor(max_concurrent=2, max_drawdown_limit=5.0)
        self.execution_broker = None

    def set_execution_broker(self, broker_runtime) -> None:
        """Injects the live broker runtime used by automatic LIVE deployment."""
        self.execution_broker = broker_runtime

    def set_profile(self, profile: AutoTradeDeploymentProfile) -> None:
        """Sets the active deployment profile."""
        self.profile = profile
        self.governor.max_concurrent = profile.max_positions
        self.state.event_bus.emit(f"Active profile set to: {profile.name}", "INFO")

    def heartbeat_update(self, symbol: str, current_price: float, current_spread: float, current_volatility: str) -> dict:
        """
        Lightweight heartbeat update (Loop 1).
        Updates current prices, spreads, active positions PnLs, checks risk state, and candidate validity.
        """
        self.state.last_price = current_price
        self.state.last_spread = current_spread
        self.state.last_volatility = current_volatility
        
        # Check emergency locks
        if self.state.check_emergency_lock():
            flattens = []
            for pos in list(self.state.active_positions):
                candle_dict = {
                    "timestamp": pd.Timestamp.utcnow(),
                    "close": current_price,
                    "high": current_price,
                    "low": current_price,
                    "open": current_price,
                }
                closed = self.trade_manager.close_position(pos, candle_dict, current_price, "emergency_flattening")
                self.state.remove_position(pos["ticket"])
                self.balance += closed["profit"]
                self.state.record_trade_outcome(closed["profit"])
                flattens.append(closed)
            self.state.set_engine_state("EMERGENCY")
            return {
                "status": "EMERGENCY",
                "message": "Emergency shutdown active. All active positions flattened.",
                "flattens": flattens
            }

        # Update active positions live PnL and check exit hits (SL/TP)
        exits_processed = []
        for pos in list(self.state.active_positions):
            # Calculate live PnL
            direction_factor = 1.0 if pos["direction"] == "BUY" else -1.0
            pnl = (current_price - pos["entry_price"]) * pos["lot"] * direction_factor
            pos["live_pnl"] = pnl
            
            # Check exit hits
            exit_hit = False
            exit_price = current_price
            exit_reason = ""
            
            if pos["direction"] == "BUY" and pos.get("sl") and current_price <= pos["sl"]:
                exit_hit = True
                exit_price = pos["sl"]
                exit_reason = "SL_HIT"
            elif pos["direction"] == "SELL" and pos.get("sl") and current_price >= pos["sl"]:
                exit_hit = True
                exit_price = pos["sl"]
                exit_reason = "SL_HIT"
                
            if pos["direction"] == "BUY" and pos.get("tp") and current_price >= pos["tp"]:
                exit_hit = True
                exit_price = pos["tp"]
                exit_reason = "TP_HIT"
            elif pos["direction"] == "SELL" and pos.get("tp") and current_price <= pos["tp"]:
                exit_hit = True
                exit_price = pos["tp"]
                exit_reason = "TP_HIT"
                
            if exit_hit:
                candle_dict = {
                    "timestamp": pd.Timestamp.utcnow(),
                    "close": exit_price,
                    "high": exit_price,
                    "low": exit_price,
                    "open": exit_price,
                }
                closed_pos = self.trade_manager.close_position(pos, candle_dict, exit_price, exit_reason)
                self.state.remove_position(pos["ticket"])
                self.balance += closed_pos["profit"]
                self.state.record_trade_outcome(closed_pos["profit"])
                exits_processed.append(closed_pos)

        # Check candidate validity against spread
        if current_spread > self.profile.max_spread:
            self.state.active_candidates = []
            if self.state.engine_state not in ("LOCKED", "EMERGENCY"):
                self.state.set_engine_state("LOCKED")
                self.state.event_bus.emit(f"Spread ({current_spread:.1f}) exceeds limit ({self.profile.max_spread}). Engine locked.", "WARNING")

        return {
            "status": self.state.engine_state,
            "price": current_price,
            "spread": current_spread,
            "volatility": current_volatility,
            "exits": exits_processed
        }

    def run_health_supervision(self) -> dict:
        """
        Health supervision checks (Loop 3).
        Checks strategy health, drawdown levels, and safety locks.
        Never executes trades directly.
        """
        # Drawdown safety
        if self.state.daily_drawdown >= self.state.max_daily_drawdown_pct:
            self.state.set_engine_state("EMERGENCY")
            self.state.event_bus.emit("Loop 3 Health Check: Critical drawdown limits exceeded.", "CRITICAL")
            
        # Volatility/regime check
        if self.state.last_volatility == "PANIC" or self.state.check_regime_instability():
            if self.state.engine_state not in ("LOCKED", "EMERGENCY"):
                self.state.set_engine_state("LOCKED")
                self.state.event_bus.emit("Loop 3 Health Check: Critical market instability detected. Engine locked.", "WARNING")

        # Exposure limit verification
        if len(self.state.active_positions) >= self.profile.max_positions:
            self.state.event_bus.emit("Loop 3 Health Check: Portfolio at maximum position exposure capacity.", "INFO")

        return {
            "status": self.state.engine_state,
            "daily_drawdown": self.state.daily_drawdown,
            "consecutive_losses": self.state.consecutive_losses,
            "positions_count": len(self.state.active_positions)
        }

    def evaluate_candle(self, symbol: str, timeframe: str, df: pd.DataFrame, tournament_input: TournamentInput) -> dict:
        """
        Runs the full execution deployment loop on the latest candle (Loop 2).
        """
        if df is None or df.empty:
            return {"status": "ERROR", "message": "Input DataFrame is empty."}

        row = df.iloc[-1]
        candle_dict = row.to_dict()
        self.state.last_processed_candle = row.get("timestamp")

        # Step 1: Emergency Flattening and Lockdown Gate
        if self.state.check_emergency_lock():
            # Flatten all active positions
            flattens = []
            for pos in list(self.state.active_positions):
                if self.state.deployment_mode == "LIVE" and self.execution_broker is not None:
                    res = self.execution_broker.close_live_position(
                        symbol=pos.get("symbol") or symbol,
                        ticket=int(pos.get("ticket")),
                        direction=pos.get("direction", "BUY"),
                        lot=float(pos.get("lot") or pos.get("qty") or 0.01),
                    )
                    flattens.append(res)
                    if res.get("status") == "CLOSED":
                        self.state.remove_position(pos["ticket"])
                    else:
                        self.state.event_bus.emit(
                            f"Emergency broker close failed for #{pos.get('ticket')}: {res.get('error')}",
                            "CRITICAL",
                        )
                else:
                    closed = self.trade_manager.close_position(pos, candle_dict, candle_dict["close"], "emergency_flattening")
                    self.state.remove_position(pos["ticket"])
                    self.balance += closed["profit"]
                    self.state.record_trade_outcome(closed["profit"])
                    flattens.append(closed)
            self.state.set_engine_state("EMERGENCY")
            return {
                "status": "LOCKOUT",
                "message": "Emergency shutdown active. All active positions flattened.",
                "flattens": flattens
            }

        # Step 2: Manage open positions (trailing, break-even, exits)
        exits_processed = []
        if self.state.deployment_mode == "LIVE":
            # LIVE broker positions are managed and closed by MT5. The local list is
            # a synchronized view; deleting rows here would create false closes.
            exits_processed = []
        else:
            for pos in list(self.state.active_positions):
                strategy_obj = get_strategy_by_name(pos["strategy"])
                updated_pos = self.trade_manager.manage(pos, candle_dict, strategy_obj, 0)
                
                exit_hit, exit_price, exit_reason = self.trade_manager.hit_exit(updated_pos, candle_dict, strategy_obj)
                if exit_hit:
                    closed_pos = self.trade_manager.close_position(updated_pos, candle_dict, exit_price, exit_reason, strategy_obj)
                    self.state.remove_position(pos["ticket"])
                    self.balance += closed_pos["profit"]
                    self.state.record_trade_outcome(closed_pos["profit"], initial_balance=10000.0)
                    exits_processed.append(closed_pos)
                    
                    # V3 Strategy Fatigue tracking: increment fatigue score on loss
                    if closed_pos["profit"] < 0:
                        strat_name = pos["strategy"]
                        self.state.fatigue_scores[strat_name] = self.state.fatigue_scores.get(strat_name, 0.0) + 25.0
                        self.state.event_bus.emit(f"Strategy {strat_name} fatigue increased due to loss.", "WARNING")
                else:
                    # Update position state
                    for idx, p in enumerate(self.state.active_positions):
                        if p["ticket"] == pos["ticket"]:
                            self.state.active_positions[idx] = updated_pos

        # Decay strategy fatigue scores slowly over time
        for name in list(self.state.fatigue_scores.keys()):
            self.state.fatigue_scores[name] = max(0.0, self.state.fatigue_scores[name] - 5.0)

        # Step 3: Session & Volatility checks
        current_session = tournament_input.session_context.get("current_session", "ASIAN")
        if current_session not in self.profile.allowed_sessions:
            return {
                "status": "INACTIVE_SESSION",
                "message": f"Session '{current_session}' not allowed in profile.",
                "exits": exits_processed
            }

        # Volatility Circuit Breaker
        h1_struct = tournament_input.mtf_context.get("h1_structure", {})
        atr_ratio = float(h1_struct.get("_atr_ratio", 1.0))
        if atr_ratio > 2.0:
            if self.state.engine_state not in ("LOCKED", "EMERGENCY"):
                self.state.set_engine_state("LOCKED")
                self.state.event_bus.emit(f"Volatility spike ({atr_ratio:.2f}x mean) triggered circuit breaker.", "WARNING")
            return {
                "status": "VOLATILITY_CIRCUIT_BREAKER",
                "message": f"ATR ratio ({atr_ratio:.2f}) indicates abnormal volatility spike.",
                "exits": exits_processed
            }

        # Spread Circuit Breaker
        spread = float(self.state.last_spread or self.profile.max_spread - 2.0)
        if spread > self.profile.max_spread:
            if self.state.engine_state not in ("LOCKED", "EMERGENCY"):
                self.state.set_engine_state("LOCKED")
                self.state.event_bus.emit(f"Spread ({spread:.1f}) exceeds limit ({self.profile.max_spread}). Engine locked.", "WARNING")
            return {
                "status": "HIGH_SPREAD",
                "message": f"Spread ({spread}) exceeds profile limit ({self.profile.max_spread}).",
                "exits": exits_processed
            }

        # Step 4: Regime stability check
        regime = h1_struct.get("macro_regime", "RANGING")
        self.state.update_regime(regime)
        if self.state.check_regime_instability():
            return {
                "status": "REGIME_INSTABILITY_LOCKOUT",
                "message": "Market regime changing too rapidly. Trading locked.",
                "exits": exits_processed
            }

        # Step 5: Compute Regime Collapse Probability
        changes = 0
        if len(self.state.regime_history) >= 4:
            for i in range(1, len(self.state.regime_history)):
                if self.state.regime_history[i] != self.state.regime_history[i-1]:
                    changes += 1
        self.state.regime_collapse_prob = min(1.0, changes * 0.25)

        # Step 6: Resolve Market Personality
        if atr_ratio > 2.0:
            self.state.market_personality = "VIOLENT_EXPANSION"
        elif self.state.regime_collapse_prob > 0.5:
            self.state.market_personality = "CHOPPY"
        elif regime == "TRENDING" and atr_ratio <= 1.2:
            self.state.market_personality = "SMOOTH_TREND"
        elif regime == "RANGING" and atr_ratio < 0.8:
            self.state.market_personality = "EXHAUSTED"
        else:
            self.state.market_personality = "LIQUIDITY_DRIVEN"

        # Step 7: Microstructure & Execution Quality check
        eq_res = ExecutionQualityEngine.evaluate_quality(spread, self.profile.max_spread, atr_ratio)
        
        # Step 8: Market Stress Index calculation
        conflict_cnt = getattr(tournament_input.contradiction_state, "conflict_count", 0) if tournament_input.contradiction_state else 0
        stress_res = MarketStressIndex.calculate_stress(
            volatility_ratio=atr_ratio,
            spread_pts=spread,
            max_spread=self.profile.max_spread,
            conflict_count=conflict_cnt
        )
        self.state.stress_level = stress_res["stress_level"]

        # Step 9: Strategy tournament
        # Check for Intelligence Freeze during active execution
        is_frozen = (self.state.engine_state in ("ARMED", "EXECUTING")) and len(self.state.active_positions) > 0
        if is_frozen and self.state.latest_tournament:
            self.state.event_bus.emit("Strategy tournament is frozen during active execution.", "INFO")
            ranked_results = self.state.latest_tournament
        else:
            ranked_results = self.tournament_engine.rank(tournament_input)
            if not ranked_results:
                return {
                    "status": "NO_RANKINGS",
                    "message": "Tournament returned no strategy rankings.",
                    "exits": exits_processed
                }
            
            # Apply V3 Post-processing corrections
            for item in ranked_results:
                name = item["strategy"]
                score = item["market_fit_score"]
                
                # 1. Fatigue deduction
                fatigue = self.state.fatigue_scores.get(name, 0.0)
                score -= fatigue
                
                # 2. Session Personality weighting
                if name == "Compression Breakout" and current_session in ("LONDON", "NY_OVERLAP"):
                    score += 10.0
                elif name == "Mean Reversion" and current_session == "ASIAN":
                    score += 10.0
                elif name == "Liquidity Sweep Reversal" and current_session in ("NEW_YORK", "NY_OVERLAP"):
                    score += 10.0
                    
                # 3. Regime Collapse reduction
                if self.state.regime_collapse_prob > 0.5 and name in ("Momentum Continuation", "Elder Swing"):
                    score -= 15.0
                    
                # Update item
                item["market_fit_score"] = max(0.0, min(100.0, score))
                
                # Apply confidence saturation
                raw_conf = float(item.get("market_fit_score", 50.0))
                saturated_conf = 100.0 * (1.0 - math.exp(-0.025 * raw_conf))
                item["confidence"] = max(0.0, min(100.0, saturated_conf))

            # Re-sort tournament rankings based on modified scores
            ranked_results.sort(key=lambda x: x["market_fit_score"], reverse=True)
            self.state.latest_tournament = ranked_results

        # Filter rankings by active trading mode's eligible strategies
        from deployment.trading_modes import get_mode
        active_mode = get_mode(getattr(self.state, "active_trading_mode", "Aggressive Scalper"))
        eligible = {s.lower() for s in active_mode.eligible_strategies}
        mode_rankings = [
            r for r in ranked_results
            if str(r.get("strategy") or r.get("name") or "").strip().lower() in eligible
        ]
        if not mode_rankings:
            mode_rankings = ranked_results  # fallback to full list if no match

        winner_name = mode_rankings[0]["strategy"]

        # Step 10: Get target strategy candidate
        strategy_name = self.profile.name  # Target profile/strategy name
        # Default fallback to tournament winner if not a custom profile
        if not any(s.get_strategy_name() == strategy_name for s in AVAILABLE_STRATEGIES):
            strategy_name = winner_name

        strategy_obj = get_strategy_by_name(strategy_name)

        if not strategy_obj.validate_context(tournament_input):
            return {
                "status": "ELIMINATED",
                "message": f"Strategy '{strategy_name}' failed context eligibility check.",
                "exits": exits_processed
            }

        candidate = strategy_obj.build_execution_candidate(tournament_input)
        if not candidate:
            self.state.active_candidates = []
            return {
                "status": "NO_CANDIDATE",
                "message": f"Strategy '{strategy_name}' did not produce an execution candidate.",
                "exits": exits_processed
            }
        if hasattr(self.state, "mark_execution_verification"):
            if hasattr(self.state, "reset_execution_verification"):
                self.state.reset_execution_verification()
            self.state.mark_execution_verification("strategy_candidate_built", True)

        # Apply V3 Post-processing to Candidate
        winner_item = next((item for item in ranked_results if item["strategy"] == strategy_name), ranked_results[0])
        candidate["confidence"] = winner_item["confidence"]
        
        # Build Trade Thesis
        entry_price = float(row.get("close", 0.0))
        atr = float(row.get("atr", 1.0))
        direction = candidate["direction"]
        if direction == "BULLISH":
            direction = "BUY"
        elif direction == "BEARISH":
            direction = "SELL"
            
        sl, tp = strategy_obj.calculate_sl_tp(entry_price, atr, direction)
        
        # Trade Thesis definition
        thesis = {
            "entry_thesis": f"Micro-timing trade setup for {strategy_name} in session {current_session}.",
            "invalidation_conditions": f"Price breaches SL at {sl:.5f}.",
            "confirmation_conditions": f"Breakout confirms direction {direction}.",
            "expected_lifecycle": "FRESH",
            "expected_volatility": atr_ratio,
            "expected_holding_duration": 12
        }
        candidate["trade_thesis"] = thesis

        candidate_payload = dict(candidate)
        candidate_payload.setdefault("strategy", strategy_name)
        candidate_payload["direction"] = direction
        candidate_payload["sl"] = sl
        candidate_payload["tp"] = tp
        candidate_payload["entry_price"] = entry_price
        self.state.active_candidates = [candidate_payload]

        confidence = candidate["confidence"]

        # Step 11: Gating parameters
        if confidence < self.profile.minimum_confidence:
            return {
                "status": "LOW_CONFIDENCE",
                "message": f"Candidate confidence ({confidence:.1f}) below profile minimum ({self.profile.minimum_confidence:.1f}).",
                "exits": exits_processed
            }

        if len(self.state.active_positions) >= self.profile.max_positions:
            return {
                "status": "MAX_POSITIONS_REACHED",
                "message": f"Active positions count ({len(self.state.active_positions)}) at profile limit ({self.profile.max_positions}).",
                "exits": exits_processed
            }

        # Duplicate Trade Suppression
        for pos in self.state.active_positions:
            if pos["strategy"] == strategy_name and pos["direction"] == direction:
                return {
                    "status": "DUPLICATE_SUPPRESSED",
                    "message": f"Duplicate active trade detected for strategy '{strategy_name}'.",
                    "exits": exits_processed
                }

        # Step 12: Governance & Capital Sizing check
        gov_res = self.governor.evaluate_deployment(
            active_positions_count=len(self.state.active_positions),
            daily_drawdown_pct=self.state.daily_drawdown,
            stress_level=self.state.stress_level,
            confidence=confidence,
            session=current_session,
            base_risk_per_trade=self.profile.risk_per_trade
        )
        
        # Capital Sizing Engine integration
        sizing_res = CapitalEfficiencyEngine.calculate_sizing(
            balance=self.balance,
            entry_price=entry_price,
            stop_loss=sl,
            confidence=confidence,
            quality_score=eq_res["execution_quality_score"],
            stress_level=self.state.stress_level,
            governor_risk_pct=gov_res["final_risk_percent"]
        )
        if self.state.active_candidates:
            self.state.active_candidates[0]["qty"] = sizing_res["lots"]
            self.state.active_candidates[0]["lot"] = sizing_res["lots"]

        final_permission = gov_res["deployment_permitted"] and eq_res["deployment_permission"]
        if hasattr(self.state, "mark_execution_verification"):
            self.state.mark_execution_verification("risk_gates_passed", bool(final_permission))

        # Log trace logic
        trace_file = DecisionTraceEngine.log_trace(
            symbol=symbol,
            timeframe=timeframe,
            market_state={"regime": regime, "atr_ratio": atr_ratio, "phase": self.state.market_phase},
            personality=self.state.market_personality,
            stress_level=self.state.stress_level,
            rankings=self.state.latest_tournament,
            confidence_model={"raw_confidence": float(winner_item.get("market_fit_score", 50.0)), "saturated_confidence": confidence},
            risk_governance={"risk_scaling": gov_res["risk_scaling"], "risk_percent": gov_res["final_risk_percent"], "lots": sizing_res["lots"]},
            permission=final_permission,
            final_decision="EXECUTE" if final_permission else "SUPPRESS"
        )

        # Step 13: No-Trade Environment State routing
        if not final_permission:
            self.state.active_candidates = []
            return {
                "status": "NO_DEPLOYMENT_ENVIRONMENT",
                "message": f"Deployment blocked. Reason: {gov_res['reason'] if not gov_res['deployment_permitted'] else 'Microstructure quality too low'}",
                "exits": exits_processed,
                "trace": trace_file
            }

        if self.state.deployment_mode == "LIVE" and not bool(getattr(self.state, "live_execution_is_fresh_candle", False)):
            warning = (
                "LIVE auto execution is waiting for a fresh closed MT5 candle. "
                "Historical/downloaded candle evaluation will not be sent to broker."
            )
            if hasattr(self.state, "mark_execution_verification"):
                self.state.mark_execution_verification(
                    "broker_order_sent",
                    False,
                    last_warning=warning,
                )
            self.state.event_bus.emit(warning, "WARNING")
            return {
                "status": "LIVE_WAITING_FOR_NEW_CANDLE",
                "message": warning,
                "exits": exits_processed,
                "trace": trace_file
            }

        candle_ts = candle_dict.get("timestamp")
        candle_key = f"{symbol}|{timeframe}|{candle_ts}|{strategy_name}|{direction}"
        if self.state.deployment_mode == "LIVE" and getattr(self.state, "last_deployment_candle_key", None) == candle_key:
            return {
                "status": "DUPLICATE_CANDLE_SUPPRESSED",
                "message": "Automatic LIVE deployment already attempted for this closed candle.",
                "exits": exits_processed,
                "trace": trace_file,
            }

        # Step 14: Deployment routing
        if self.state.deployment_mode in ("LIVE", "SEMI_AUTO"):
            if self.state.engine_state == "IDLE":
                self.state.set_engine_state("ARMED")
            
            if self.state.engine_state in ("PAUSED", "LOCKED", "EMERGENCY"):
                return {
                    "status": "EXECUTION_SUPPRESSED",
                    "message": f"Execution intent generated but blocked by engine state: {self.state.engine_state}",
                    "exits": exits_processed
                }

        intent = ExecutionIntent(
            symbol=symbol,
            direction=direction,
            execution_type="MARKET",
            strategy=strategy_name,
            risk_profile=self.profile.name,
            confidence=confidence,
            sl=sl,
            tp=tp,
            risk_per_trade=gov_res["final_risk_percent"],
            qty=sizing_res["lots"]
        )
        intent_id = f"{symbol}-{strategy_name}-{int(time.time() * 1000)}"
        if hasattr(self.state, "reset_execution_verification"):
            self.state.reset_execution_verification(intent_id=intent_id)
            self.state.mark_execution_verification("strategy_candidate_built", True)
            self.state.mark_execution_verification("risk_gates_passed", bool(final_permission))
            self.state.mark_execution_verification("intent_created", True, last_intent_id=intent_id)

        if self.state.deployment_mode == "LIVE":
            self.state.last_deployment_candle_key = candle_key
            broker = self.execution_broker
            if broker is None or not hasattr(broker, "place_live_order"):
                warning = "LIVE broker runtime is not attached. Broker order not sent."
                if hasattr(self.state, "mark_execution_verification"):
                    self.state.mark_execution_verification(
                        "broker_order_failed",
                        True,
                        last_warning=warning,
                    )
                self.state.event_bus.emit(warning, "CRITICAL")
                return {
                    "status": "LIVE_BROKER_UNAVAILABLE",
                    "message": warning,
                    "intent": intent.to_dict(),
                    "exits": exits_processed
                }

            order_request = {
                "symbol": intent.symbol,
                "direction": intent.direction,
                "lot": intent.qty,
                "sl": intent.sl,
                "tp": intent.tp,
                "comment": f"NXB {intent.strategy}",
            }
            if hasattr(self.state, "mark_execution_verification"):
                self.state.mark_execution_verification(
                    "broker_order_sent",
                    True,
                    last_order_request=order_request,
                )
            self.state.event_bus.emit(
                f"Auto LIVE broker order sent: {intent.direction} {intent.qty} {intent.symbol}",
                "INFO",
            )

            order_result = broker.place_live_order(**order_request)
            ticket = int(order_result.get("ticket", -1) or -1)
            broker_confirmed = ticket > 0 and order_result.get("status") == "PLACED"

            if not broker_confirmed:
                if hasattr(self.state, "mark_execution_verification"):
                    self.state.mark_execution_verification(
                        "broker_order_failed",
                        True,
                        last_order_result=order_result,
                        last_broker_ticket=None,
                    )
                self.state.event_bus.emit(
                    f"Auto LIVE broker order failed: {order_result.get('error') or order_result.get('comment')}",
                    "CRITICAL",
                )
                return {
                    "status": "LIVE_BROKER_ORDER_FAILED",
                    "message": order_result.get("error") or order_result.get("comment") or "Broker order failed.",
                    "intent": intent.to_dict(),
                    "order_result": order_result,
                    "exits": exits_processed
                }

            if hasattr(self.state, "mark_execution_verification"):
                self.state.mark_execution_verification(
                    "broker_order_confirmed",
                    True,
                    broker_ticket_returned=True,
                    last_order_result=order_result,
                    last_broker_ticket=ticket,
                )
            self.state.event_bus.emit(
                f"Auto LIVE broker order confirmed: Ticket #{ticket}. Awaiting broker position sync.",
                "INFO",
            )
            self.state.set_engine_state("EXECUTING")
            return {
                "status": "LIVE_BROKER_ORDER_CONFIRMED",
                "intent": intent.to_dict(),
                "order_result": order_result,
                "exits": exits_processed
            }

        elif self.state.deployment_mode == "SEMI_AUTO":
            return {
                "status": "AWAITING_CONFIRMATION",
                "intent": intent.to_dict(),
                "exits": exits_processed
            }

        else:  # ADVISORY
            return {
                "status": "ADVISORY_SUGGESTION",
                "intent": intent.to_dict(),
                "exits": exits_processed
            }
