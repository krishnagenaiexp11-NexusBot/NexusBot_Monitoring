"""
deployment/live_state_manager.py
Tracks active positions, deployed strategies, current regime, drawdown, and state transitions.
"""
from engine.event_bus import EventBus
import time


class LiveStateManager:
    """
    Manages live state, safety limits, trade statistics, and the engine state machine.
    """

    def __init__(self):
        self.active_positions = []
        self.active_strategies = []
        self.previous_regime = "NEUTRAL"
        self.current_regime = "NEUTRAL"
        self.regime_history = []
        self.deployment_mode = "ADVISORY"  # ADVISORY | SEMI_AUTO | LIVE
        self.active_trading_mode = "Aggressive Scalper"  # Active trading mode name
        self.emergency_shutdown = False
        self.consecutive_losses = 0
        self.daily_drawdown = 0.0          # In percentage terms

        # V3 additions
        self.engine_state = "IDLE"         # IDLE | ANALYZING | WATCHING | ARMED | EXECUTING | MANAGING | LOCKED | EMERGENCY
        self.event_bus = EventBus(max_events=200)
        self.latest_tournament = []
        self.active_candidates = []
        self.active_trade_plan = None
        self.selected_strategy_name = None
        self.selected_strategy_context = {}
        self.selected_trade_plan_key = None
        self.macro_context = {}
        self.runtime_snapshot = {}
        self.trading_watchlist = []
        self.watchlist_timeframe = "M5"
        self.live_trade_state = "SCANNING"
        
        # Loop schedules (stored as timestamps)
        self.last_heartbeat_time = 0.0
        self.last_analytical_time = 0.0
        self.last_health_time = 0.0
        self.last_processed_candle = None  # Tracks timestamp of last processed candle
        self.live_execution_is_fresh_candle = False
        self.last_live_execution_candle = None
        self.last_analysis_timeframe = "M5"
        self.last_analysis_symbol = "UNKNOWN"
        self.last_deployment_candle_key = None
        self.last_plan_candle = None
        self.last_macro_candle = None
        self.last_plan_execution_key = None

        # Telemetry
        self.last_price = 0.0
        self.last_spread = 0.0
        self.last_volatility = "NORMAL"

        # Live execution verification telemetry. This is intentionally separate
        # from strategy scoring so UI can prove whether broker execution occurred.
        self.execution_verification = {
            "intent_created": False,
            "strategy_candidate_built": False,
            "risk_gates_passed": False,
            "broker_order_sent": False,
            "broker_ticket_returned": False,
            "broker_order_confirmed": False,
            "broker_order_failed": False,
            "broker_position_confirmed": False,
            "runtime_position_synced": False,
            "last_intent_id": None,
            "last_order_request": None,
            "last_order_result": None,
            "last_broker_ticket": None,
            "last_confirmed_position": None,
            "auto_live_local_only": False,
            "last_warning": None,
            "events": [],
        }

        # V3 Hardening additions
        self.market_phase = "ACCUMULATION"           # ACCUMULATION | EXPANSION | TREND | EXHAUSTION | REVERSAL
        self.market_personality = "SMOOTH_TREND"     # SMOOTH_TREND | VIOLENT_EXPANSION | CHOPPY | TRAP_HEAVY | LIQUIDITY_DRIVEN | EXHAUSTED
        self.stress_level = "LOW"                    # LOW | MODERATE | HIGH | EXTREME
        self.regime_collapse_prob = 0.0
        self.fatigue_scores = {}                     # strategy_name -> fatigue_score (0.0 to 100.0)
        self.h1_df_ref = None                        # Reference to H1 DataFrame for volatility checks

        # Safety boundaries
        self.max_consecutive_losses = 3
        self.max_daily_drawdown_pct = 5.0  # 5% max daily drawdown limit

        # Log initialization
        self.event_bus.emit("LiveStateManager initialized. Default State: IDLE", "INFO")

    def reset_execution_verification(self, intent_id: str | None = None) -> None:
        self.execution_verification.update({
            "intent_created": bool(intent_id),
            "strategy_candidate_built": False,
            "risk_gates_passed": False,
            "broker_order_sent": False,
            "broker_ticket_returned": False,
            "broker_order_confirmed": False,
            "broker_order_failed": False,
            "broker_position_confirmed": False,
            "runtime_position_synced": False,
            "last_intent_id": intent_id,
            "last_order_request": None,
            "last_order_result": None,
            "last_broker_ticket": None,
            "last_confirmed_position": None,
            "auto_live_local_only": False,
            "last_warning": None,
            "events": [],
        })

    def mark_execution_verification(self, key: str, value=True, **fields) -> None:
        if key:
            self.execution_verification[key] = value
        self.execution_verification.update(fields)
        self.execution_verification["events"].append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "key": key,
            "value": value,
            "fields": fields,
        })
        if len(self.execution_verification["events"]) > 25:
            self.execution_verification["events"] = self.execution_verification["events"][-25:]

    def add_to_watchlist(self, symbol: str, timeframe: str = "M5") -> None:
        symbol = str(symbol or "").strip().upper()
        timeframe = str(timeframe or "M5").strip().upper()
        if not symbol:
            return
        self.watchlist_timeframe = timeframe
        if not any(item.get("symbol") == symbol for item in self.trading_watchlist):
            self.trading_watchlist.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "status": "WATCHING",
                "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            self.event_bus.emit(f"Added {symbol} {timeframe} to trading watchlist.", "INFO")

    def remove_from_watchlist(self, symbol: str) -> None:
        symbol = str(symbol or "").strip().upper()
        before = len(self.trading_watchlist)
        self.trading_watchlist = [item for item in self.trading_watchlist if item.get("symbol") != symbol]
        if len(self.trading_watchlist) != before:
            self.event_bus.emit(f"Removed {symbol} from trading watchlist.", "INFO")

    def set_live_trade_state(self, state: str) -> None:
        valid_states = {
            "SCANNING",
            "SETUP_FORMING",
            "ENTRY_ZONE",
            "TRIGGER_READY",
            "EXECUTE",
            "IN_TRADE",
            "EXIT_PENDING",
            "CLOSED",
        }
        if state not in valid_states:
            raise ValueError(f"Invalid live trade state: {state}")
        old_state = self.live_trade_state
        self.live_trade_state = state
        if old_state != state:
            self.event_bus.emit(f"Live trade state changed: {old_state} -> {state}", "INFO")

    def set_active_trade_plan(self, plan: dict | None) -> None:
        self.active_trade_plan = plan
        if plan:
            self.set_live_trade_state(str(plan.get("status") or "SETUP_FORMING"))
            zone_low = plan.get("entry_zone_low")
            zone_high = plan.get("entry_zone_high")
            try:
                zone_text = f"{float(zone_low):.5f}-{float(zone_high):.5f}"
            except Exception:
                zone_text = "N/A"
            self.event_bus.emit(
                f"Trade plan ready: {plan.get('strategy')} {plan.get('direction')} "
                f"{plan.get('symbol')} zone {zone_text}",
                "INFO",
            )
        else:
            self.set_live_trade_state("SCANNING")

    def set_macro_context(self, context: dict) -> None:
        self.macro_context = context or {}
        self.event_bus.emit(
            f"Macro context refreshed: {self.macro_context.get('regime', 'UNKNOWN')} "
            f"{self.macro_context.get('macro_direction', 'NEUTRAL')}",
            "INFO",
        )

    def set_runtime_snapshot(self, snapshot: dict) -> None:
        self.runtime_snapshot = snapshot or {}

    def set_engine_state(self, state: str) -> None:
        """Sets engine state deterministically with validation."""
        valid_states = {"IDLE", "ANALYZING", "WATCHING", "ARMED", "EXECUTING", "MANAGING", "LOCKED", "EMERGENCY", "PAUSED", "SAFE"}
        if state not in valid_states:
            raise ValueError(f"Invalid engine state: {state}")
        
        # Don't transition if already in EMERGENCY unless explicitly reset/cleared via IDLE
        if self.engine_state == "EMERGENCY" and state != "IDLE":
            self.event_bus.emit(f"Ignored state transition to {state}: EMERGENCY lockout is active.", "WARNING")
            return
            
        old_state = self.engine_state
        self.engine_state = state
        if old_state != state:
            self.event_bus.emit(f"Engine state changed: {old_state} -> {state}", "INFO")

    def add_position(self, position: dict) -> None:
        """Adds a position to the active list."""
        self.active_positions.append(position)
        self.event_bus.emit(f"Position added: #{position.get('ticket')} - {position.get('strategy')} {position.get('direction')} {position.get('lot') or position.get('qty', 0.01)} lots", "INFO")
        self.set_engine_state("EXECUTING")

    def remove_position(self, ticket: int) -> dict | None:
        """Removes and returns a position from the active list by ticket ID."""
        for idx, pos in enumerate(self.active_positions):
            if pos.get("ticket") == ticket:
                removed = self.active_positions.pop(idx)
                self.event_bus.emit(f"Position removed: #{ticket} - {removed.get('strategy')} {removed.get('direction')} PnL: ${removed.get('live_pnl', 0.0):.2f}", "INFO")
                if not self.active_positions:
                    if self.engine_state == "EXECUTING":
                        self.set_engine_state("WATCHING")
                return removed
        return None

    def record_trade_outcome(self, profit: float, initial_balance: float = 10000.0) -> None:
        """Updates consecutive losses and daily drawdown based on trade outcome."""
        if profit < 0:
            self.consecutive_losses += 1
            self.daily_drawdown += abs(profit) / initial_balance * 100.0
            self.event_bus.emit(f"Trade Loss recorded: ${profit:.2f}. Drawdown: {self.daily_drawdown:.2f}%. Consecutive Losses: {self.consecutive_losses}", "WARNING")
        else:
            self.consecutive_losses = 0
            self.event_bus.emit(f"Trade Profit recorded: +${profit:.2f}.", "INFO")

        # Trigger emergency shutdown if safety thresholds are breached
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.emergency_shutdown = True
            self.set_engine_state("EMERGENCY")
            self.event_bus.emit(f"EMERGENCY LOCK: Exceeded max consecutive losses ({self.consecutive_losses}/{self.max_consecutive_losses})", "CRITICAL")
        
        if self.daily_drawdown >= self.max_daily_drawdown_pct:
            self.emergency_shutdown = True
            self.set_engine_state("EMERGENCY")
            self.event_bus.emit(f"EMERGENCY LOCK: Exceeded max daily drawdown ({self.daily_drawdown:.2f}%/{self.max_daily_drawdown_pct}%)", "CRITICAL")

    def reset_daily_stats(self) -> None:
        """Resets daily drawdown and consecutive losses."""
        self.daily_drawdown = 0.0
        self.consecutive_losses = 0
        self.emergency_shutdown = False
        self.regime_history = []
        self.fatigue_scores = {}
        self.event_bus.emit("Daily stats, fatigue metrics, and safety locks reset.", "INFO")
        self.set_engine_state("IDLE")

    def update_regime(self, regime: str) -> None:
        """Updates the current regime and logs history for stability checking."""
        if regime != self.current_regime:
            self.previous_regime = self.current_regime
            self.current_regime = regime
            self.event_bus.emit(f"Regime transition detected: {self.previous_regime} -> {self.current_regime}", "INFO")

        self.regime_history.append(regime)
        if len(self.regime_history) > 10:
            self.regime_history.pop(0)

    def check_regime_instability(self) -> bool:
        """Returns True if the regime is changing too rapidly (>= 3 shifts in last 10 updates)."""
        if len(self.regime_history) < 4:
            return False
        changes = 0
        for i in range(1, len(self.regime_history)):
            if self.regime_history[i] != self.regime_history[i-1]:
                changes += 1
        
        is_unstable = changes >= 3
        if is_unstable and self.engine_state not in ("LOCKED", "EMERGENCY"):
            self.set_engine_state("LOCKED")
            self.event_bus.emit(f"Regime instability lock triggered ({changes} shifts in last 10 updates)", "WARNING")
        return is_unstable

    def check_emergency_lock(self) -> bool:
        """Returns True if emergency shutdown is active."""
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.emergency_shutdown = True
            self.set_engine_state("EMERGENCY")
        if self.daily_drawdown >= self.max_daily_drawdown_pct:
            self.emergency_shutdown = True
            self.set_engine_state("EMERGENCY")
        return self.emergency_shutdown
