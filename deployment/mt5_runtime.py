"""
deployment/mt5_runtime.py
Dedicated MetaTrader 5 polling and synchronization runtime thread for NexusBot V3.
"""
import time
import threading
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from runtime.mt5_connector import MT5Connector

try:
    import MetaTrader5 as mt5_lib
except ImportError:
    mt5_lib = None

logger = logging.getLogger("MT5Runtime")


def _timestamp_seconds(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


class MT5Runtime:
    """
    Handles live MT5 connection state, fast polling loops, and execution routing.
    Synchronizes open positions, pending orders, and account metrics back to SnapshotStore.
    """

    def __init__(self, snapshot_store, state_manager):
        self.snapshot_store = snapshot_store
        self.state_manager = state_manager
        
        self.connector = MT5Connector()
        self.thread = None
        self._stop_event = threading.Event()
        self.lock = threading.Lock()
        self.active_symbol = "UNKNOWN"
        self.connection_status: Dict[str, Any] = {
            "connected": False,
            "terminal": "N/A",
            "broker": "N/A",
            "server": "N/A",
            "is_simulated": False,
            "last_error": None,
        }
        
        # In-memory backup of simulated positions when MT5 is simulated
        self.simulated_positions: List[Dict[str, Any]] = []
        self.simulated_orders: List[Dict[str, Any]] = []

    def start(self) -> None:
        """Starts background MT5 poller loop."""
        if self.thread and self.thread.is_alive():
            return
        
        logger.info("Initializing MT5 Connection...")
        conn_res = self.connector.initialize()
        self.connection_status = conn_res
        logger.info(f"MT5 Init Status: {conn_res}")
        
        # Load any existing positions from state manager for initial simulation sync
        self.simulated_positions = list(self.state_manager.active_positions)

        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, name="NexusBotMT5Poller", daemon=True)
        self.thread.start()
        logger.info("MT5 Runtime background thread started.")

    def set_symbol(self, symbol: str) -> None:
        """Updates the active MT5 symbol and selects it when a live terminal is available."""
        with self.lock:
            self.active_symbol = symbol or "UNKNOWN"
            try:
                self.connector.ensure_symbol(self.active_symbol)
            except Exception as exc:
                self.connection_status["last_error"] = str(exc)
                logger.warning(f"MT5 symbol selection failed for {self.active_symbol}: {exc}")

    def stop(self) -> None:
        """Stops background MT5 poller loop."""
        self._stop_event.set()
        if self.thread:
            self.thread.join(timeout=2.0)
        self.connector.shutdown()
        logger.info("MT5 Runtime background thread stopped.")

    def _position_record(self, position) -> Dict[str, Any]:
        """Convert an MT5 position object into the runtime position contract."""
        direction = "BUY" if position.type == mt5_lib.POSITION_TYPE_BUY else "SELL"
        comment = position.comment or ""
        strategy_name = "External"
        if position.magic == 20250001:
            strategy_name = comment.replace("NXB ", "").strip() or "Tournament Winner"
        return {
            "ticket": int(position.ticket),
            "symbol": position.symbol,
            "strategy": strategy_name,
            "direction": direction,
            "entry_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(position.time)),
            "entry_price": float(position.price_open),
            "sl": float(position.sl),
            "tp": float(position.tp),
            "lot": float(position.volume),
            "qty": float(position.volume),
            "live_pnl": float(position.profit),
            "profit": float(position.profit),
            "confidence": 75.0,
            "regime_at_entry": self.state_manager.current_regime,
            "mt5_status": "LIVE",
        }

    def _confirm_new_live_position(self, order_request: dict, order_result: dict) -> dict | None:
        """Immediately locate a just-filled broker position before the next poll cycle."""
        if self.connector.is_simulated or mt5_lib is None or order_result.get("status") != "PLACED":
            return None

        expected_tickets = {
            int(value)
            for value in (
                order_result.get("ticket"),
                order_result.get("order_ticket"),
                order_result.get("deal_ticket"),
            )
            if int(value or 0) > 0
        }
        expected_symbol = str(order_result.get("symbol") or order_request.get("symbol") or "").upper()
        expected_direction = str(order_request.get("direction") or "").upper()
        expected_volume = float(order_result.get("volume") or order_request.get("lot") or 0.0)

        for _ in range(3):
            positions = mt5_lib.positions_get()
            if positions:
                records = [self._position_record(position) for position in positions]
                confirmed = next(
                    (record for record in records if int(record["ticket"]) in expected_tickets),
                    None,
                )
                if confirmed is None:
                    candidates = [
                        record for record in records
                        if (
                            str(record.get("symbol") or "").upper() == expected_symbol
                            and record.get("direction") == expected_direction
                            and (
                                expected_volume <= 0
                                or abs(float(record.get("lot") or 0.0) - expected_volume) < 1e-8
                            )
                        )
                    ]
                    if candidates:
                        confirmed = max(
                            candidates,
                            key=lambda record: _timestamp_seconds(record.get("entry_time")),
                        )
                if confirmed:
                    if not any(
                        int(position.get("ticket", -1)) == int(confirmed["ticket"])
                        for position in self.state_manager.active_positions
                    ):
                        self.state_manager.add_position(confirmed)
                    return confirmed
            time.sleep(0.1)
        return None

    def place_live_order(
        self,
        symbol: str,
        direction: str,
        lot: float,
        sl: float = 0.0,
        tp: float = 0.0,
        comment: str = "NexusBot"
    ) -> dict:
        """Routes live order requests directly to the connector."""
        with self.lock:
            order_request = {
                "symbol": symbol,
                "direction": direction,
                "lot": lot,
                "sl": sl,
                "tp": tp,
                "comment": comment,
            }
            is_broker_live = not bool(getattr(self.connector, "is_simulated", False))
            if hasattr(self.state_manager, "mark_execution_verification"):
                self.state_manager.execution_verification.update({
                    "broker_order_sent": is_broker_live,
                    "broker_ticket_returned": False,
                    "broker_order_confirmed": False,
                    "broker_order_failed": False,
                    "broker_position_confirmed": False,
                    "runtime_position_synced": False,
                    "last_order_request": order_request,
                    "last_order_result": None,
                    "last_broker_ticket": None,
                    "last_confirmed_position": None,
                    "last_warning": None,
                })
                self.state_manager.mark_execution_verification(
                    "broker_order_sent",
                    is_broker_live,
                    last_order_request=order_request,
                )
            # Route to connector
            res = self.connector.place_order(
                symbol=symbol,
                direction=direction,
                lot=lot,
                sl=sl,
                tp=tp,
                comment=comment
            )
            ticket = int(res.get("ticket", -1) or -1)
            ticket_confirmed = (
                res.get("status") in ("PLACED", "SIMULATED")
                and res.get("error") is None
                and (ticket > 0 or res.get("status") == "PLACED")
            )
            if hasattr(self.state_manager, "mark_execution_verification"):
                self.state_manager.mark_execution_verification(
                    "broker_ticket_returned",
                    ticket_confirmed,
                    last_order_request=getattr(self.connector, "last_order_request", order_request),
                    last_order_result=res,
                    last_broker_ticket=ticket if ticket > 0 else None,
                )
                if ticket_confirmed:
                    self.state_manager.mark_execution_verification(
                        "broker_order_confirmed",
                        True,
                        broker_order_failed=False,
                        last_order_result=res,
                        last_broker_ticket=ticket if ticket > 0 else None,
                    )
                else:
                    self.state_manager.mark_execution_verification(
                        "broker_order_failed",
                        True,
                        last_order_result=res,
                        last_warning=res.get("error") or res.get("comment") or "Broker rejected the order.",
                    )

            if ticket_confirmed and is_broker_live:
                confirmed_position = self._confirm_new_live_position(order_request, res)
                if confirmed_position and hasattr(self.state_manager, "mark_execution_verification"):
                    self.state_manager.mark_execution_verification(
                        "broker_position_confirmed",
                        True,
                        last_broker_ticket=confirmed_position.get("ticket"),
                        last_confirmed_position=confirmed_position,
                    )
                    self.state_manager.mark_execution_verification(
                        "runtime_position_synced",
                        True,
                        last_confirmed_position=confirmed_position,
                    )
            
            # If simulated, update simulated positions
            if self.connector.is_simulated:
                new_pos = {
                    "ticket": ticket,
                    "symbol": symbol,
                    "strategy": "Manual" if "Manual" in comment else "Tournament Winner",
                    "direction": direction,
                    "entry_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "entry_price": self.state_manager.last_price or 2000.0,
                    "sl": sl,
                    "tp": tp,
                    "lot": lot,
                    "qty": lot,
                    "live_pnl": 0.0,
                    "profit": 0.0,
                    "confidence": 75.0,
                    "regime_at_entry": self.state_manager.current_regime,
                    "mt5_status": "SIMULATED"
                }
                self.simulated_positions.append(new_pos)
                self.state_manager.add_position(new_pos)
                if hasattr(self.state_manager, "mark_execution_verification"):
                    self.state_manager.mark_execution_verification(
                        "runtime_position_synced",
                        True,
                        last_confirmed_position=new_pos,
                    )
                
            return res

    def close_live_position(
        self,
        symbol: str,
        ticket: int,
        direction: str,
        lot: float
    ) -> dict:
        """Routes close orders and processes partial closes thread-safely."""
        with self.lock:
            if self.connector.is_simulated or mt5_lib is None:
                # Remove from simulated
                self.simulated_positions = [p for p in self.simulated_positions if p["ticket"] != ticket]
                logger.info(f"[SIM] Closed simulated position #{ticket}")
                return {"ticket": ticket, "status": "CLOSED", "retcode": 0, "error": None}
                
            # If live, send close request to MT5 API
            # Determine close order type
            order_type = mt5_lib.ORDER_TYPE_SELL if direction.upper() == "BUY" else mt5_lib.ORDER_TYPE_BUY
            tick = mt5_lib.symbol_info_tick(symbol)
            if tick is None:
                return {"ticket": ticket, "status": "FAILED", "error": f"Failed to get price for {symbol}"}
                
            price = tick.bid if direction.upper() == "BUY" else tick.ask
            
            request = {
                "action": mt5_lib.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(lot),
                "type": order_type,
                "position": int(ticket),
                "price": price,
                "deviation": 20,
                "comment": "Close Position",
                "type_time": mt5_lib.ORDER_TIME_GTC,
                "type_filling": mt5_lib.ORDER_FILLING_IOC
            }
            
            result = mt5_lib.order_send(request)
            
            # IOC fill fallback
            if result is not None and result.retcode == 10030:
                for fill in (mt5_lib.ORDER_FILLING_FOK, mt5_lib.ORDER_FILLING_RETURN):
                    request["type_filling"] = fill
                    result = mt5_lib.order_send(request)
                    if result is not None and result.retcode != 10030:
                        break
                        
            if result is None:
                err = f"Failed closing #{ticket}: order_send returned None"
                logger.error(err)
                return {"ticket": ticket, "status": "FAILED", "error": err}
                
            if result.retcode == mt5_lib.TRADE_RETCODE_DONE:
                logger.info(f"[LIVE] Ticket #{ticket} closed successfully.")
                return {"ticket": ticket, "status": "CLOSED", "retcode": result.retcode, "error": None}
            else:
                err = f"MT5 close error #{ticket}: retcode={result.retcode}, comment={result.comment}"
                logger.error(err)
                return {"ticket": ticket, "status": "FAILED", "error": err}

    def _evaluate_trade_plan_state(self, price: float, bid: float, ask: float, spread: float) -> None:
        """Precision entry state machine. Never runs analysis or tournament."""
        plan = getattr(self.state_manager, "active_trade_plan", None)
        if not plan:
            if not self.state_manager.active_positions and self.state_manager.live_trade_state != "SCANNING":
                self.state_manager.set_live_trade_state("SCANNING")
            return

        if self._matching_plan_positions(plan):
            plan["status"] = "IN_TRADE"
            self.state_manager.active_trade_plan = plan
            self.state_manager.set_live_trade_state("IN_TRADE")
            return

        try:
            expiration = plan.get("expiration_time")
            if expiration and time.time() > _timestamp_seconds(expiration):
                plan["status"] = "CLOSED"
                plan["close_reason"] = "PLAN_EXPIRED"
                self.state_manager.active_trade_plan = plan
                self.state_manager.set_live_trade_state("CLOSED")
                return
        except Exception:
            pass

        direction = str(plan.get("direction") or "BUY").upper()
        zone_low = float(plan.get("entry_zone_low") or 0.0)
        zone_high = float(plan.get("entry_zone_high") or 0.0)
        trigger = float(plan.get("entry_trigger") or 0.0)
        in_zone = zone_low <= float(price) <= zone_high if zone_low and zone_high else False
        trigger_ready = False
        if direction == "BUY":
            trigger_ready = bool(trigger and float(price) >= trigger)
        else:
            trigger_ready = bool(trigger and float(price) <= trigger)

        if in_zone:
            plan["entry_zone_seen"] = True

        if trigger_ready:
            plan["status"] = "TRIGGER_READY"
            self.state_manager.active_trade_plan = plan
            self.state_manager.set_live_trade_state("TRIGGER_READY")
            self._execute_ready_trade_plan(plan, price, spread)
        elif in_zone:
            plan["status"] = "ENTRY_ZONE"
            self.state_manager.active_trade_plan = plan
            self.state_manager.set_live_trade_state("ENTRY_ZONE")
        else:
            plan["status"] = "SETUP_FORMING"
            self.state_manager.active_trade_plan = plan
            self.state_manager.set_live_trade_state("SETUP_FORMING")

    def _matching_plan_positions(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return live positions that belong to the current plan symbol/strategy."""
        plan_symbol = str(plan.get("symbol") or self.active_symbol or "").strip().upper()
        plan_strategy = str(plan.get("strategy") or "").strip().lower()
        if not plan_symbol:
            return []
        matches = []
        for pos in self.state_manager.active_positions or []:
            pos_symbol = str(pos.get("symbol") or "").strip().upper()
            if pos_symbol != plan_symbol:
                continue
            pos_strategy = str(pos.get("strategy") or "").strip().lower()
            if not plan_strategy:
                continue
            if pos_strategy in {"manual", "external", "manual exhaustion", "tournament winner"}:
                continue
            if plan_strategy in pos_strategy or pos_strategy in plan_strategy:
                matches.append(pos)
        return matches

    def _execute_ready_trade_plan(self, plan: Dict[str, Any], price: float, spread: float) -> None:
        """Routes a ready plan to broker only when deployment mode and gates permit."""
        if self.state_manager.deployment_mode != "LIVE":
            return
        if not bool(plan.get("is_live_plan")):
            self.state_manager.event_bus.emit(
                "Plan trigger observed, but auto execution is waiting for a fresh live M5 plan.",
                "WARNING",
            )
            return

        if self.state_manager.engine_state in ("PAUSED", "LOCKED", "EMERGENCY"):
            return
        profile = getattr(getattr(self, "execution_engine", None), "profile", None)
        max_spread = float(getattr(profile, "max_spread", 25.0))
        min_confidence = float(getattr(profile, "minimum_confidence", 0.0))
        max_positions = int(getattr(profile, "max_positions", 1))
        if float(plan.get("trade_quality") or plan.get("confidence") or 0.0) < min_confidence:
            self.state_manager.event_bus.emit(
                f"Plan trigger blocked by quality {float(plan.get('trade_quality') or 0.0):.1f} < {min_confidence:.1f}.",
                "WARNING",
            )
            return
        if len(self.state_manager.active_positions) >= max_positions:
            self.state_manager.event_bus.emit("Plan trigger blocked: maximum position limit reached.", "WARNING")
            return
        if float(spread or 0.0) > float(max_spread):
            self.state_manager.event_bus.emit(f"Plan trigger blocked by spread {spread:.1f} > {max_spread:.1f}.", "WARNING")
            return

        exec_key = f"{plan.get('symbol')}|{plan.get('strategy')}|{plan.get('direction')}|{plan.get('candle_time')}"
        if getattr(self.state_manager, "last_plan_execution_key", None) == exec_key:
            return
        self.state_manager.last_plan_execution_key = exec_key
        self.state_manager.set_live_trade_state("EXECUTE")

        if hasattr(self.state_manager, "reset_execution_verification"):
            self.state_manager.reset_execution_verification(intent_id=exec_key)
            self.state_manager.mark_execution_verification("intent_created", True, last_intent_id=exec_key)
            self.state_manager.mark_execution_verification("strategy_candidate_built", True)
            self.state_manager.mark_execution_verification("risk_gates_passed", True)

        result = self.place_live_order(
            symbol=str(plan.get("symbol") or self.active_symbol),
            direction=str(plan.get("direction") or "BUY"),
            lot=float(plan.get("lot") or plan.get("qty") or 0.01),
            sl=float(plan.get("stop_loss") or plan.get("sl") or 0.0),
            tp=float(plan.get("take_profit") or plan.get("tp") or 0.0),
            comment=f"NXB {str(plan.get('strategy') or 'Plan')[:20]}",
        )
        plan["last_order_result"] = result
        if int(result.get("ticket", -1) or -1) > 0 and result.get("status") == "PLACED":
            plan["status"] = "IN_TRADE"
            self.state_manager.active_trade_plan = plan
            self.state_manager.set_live_trade_state("IN_TRADE")
        else:
            plan["status"] = "TRIGGER_READY"
            self.state_manager.active_trade_plan = plan
            self.state_manager.set_live_trade_state("TRIGGER_READY")


    def _run_loop(self) -> None:
        """Market monitor loop. Lightweight MT5 sync only; no analysis/tournament."""
        while not self._stop_event.is_set():
            try:
                # 1. Update Connection Info
                is_sim = self.connector.is_simulated
                
                # Fetch quote tick
                # Try to resolve actual symbol name from state manager
                from deployment.engine_runtime import get_global_runtime
                try:
                    runtime_symbol = get_global_runtime().symbol
                except Exception:
                    runtime_symbol = self.active_symbol or "UNKNOWN"
                runtime_symbol = runtime_symbol or self.active_symbol or "UNKNOWN"
                self.active_symbol = runtime_symbol

                price = 0.0
                spread = 0.0
                bid = 0.0
                ask = 0.0
                
                # Get Account metrics
                acc_info = self.connector.get_account_info()
                balance = acc_info.get("balance", 10000.0)
                equity = acc_info.get("equity", 10000.0)
                currency = acc_info.get("currency", "USD")
                leverage = acc_info.get("leverage", 100)

                active_positions = []
                pending_orders = []

                if not is_sim and mt5_lib is not None:
                    # --- Live API Polling ---
                    # Poll price & spread
                    try:
                        runtime_symbol = self.connector.ensure_symbol(runtime_symbol)
                    except Exception as exc:
                        self.connection_status["last_error"] = str(exc)
                        logger.warning(f"MT5 poll symbol selection failed: {exc}")
                    tick = mt5_lib.symbol_info_tick(runtime_symbol)
                    if tick:
                        bid = float(tick.bid)
                        ask = float(tick.ask)
                        price = float(ask + bid) / 2.0
                        spread = float(ask - bid)
                        info = mt5_lib.symbol_info(runtime_symbol)
                        if info and info.point:
                            spread = spread / info.point
                    else:
                        price = self.state_manager.last_price or 2000.0
                        spread = 15.0

                    # Sync positions (Existing MT5 positions MUST appear automatically!)
                    positions = mt5_lib.positions_get()
                    if positions is not None:
                        for p in positions:
                            active_positions.append(self._position_record(p))
                    expected_ticket = None
                    expected_request = {}
                    expected_result = {}
                    if hasattr(self.state_manager, "execution_verification"):
                        verification = self.state_manager.execution_verification
                        expected_ticket = verification.get("last_broker_ticket")
                        expected_request = verification.get("last_order_request") or {}
                        expected_result = verification.get("last_order_result") or {}
                    if expected_ticket or expected_result.get("status") == "PLACED":
                        confirmed = next(
                            (pos for pos in active_positions if int(pos.get("ticket", -1)) == int(expected_ticket)),
                            None,
                        ) if expected_ticket else None
                        if confirmed is None:
                            expected_symbol = str(
                                expected_result.get("symbol")
                                or expected_request.get("symbol")
                                or ""
                            ).strip().upper()
                            expected_direction = str(expected_request.get("direction") or "").strip().upper()
                            expected_volume = float(
                                expected_result.get("volume")
                                or expected_request.get("lot")
                                or 0.0
                            )
                            candidates = [
                                pos for pos in active_positions
                                if (
                                    (not expected_symbol or str(pos.get("symbol") or "").strip().upper() == expected_symbol)
                                    and (not expected_direction or pos.get("direction") == expected_direction)
                                    and (
                                        expected_volume <= 0
                                        or abs(float(pos.get("lot") or 0.0) - expected_volume) < 1e-8
                                    )
                                )
                            ]
                            if candidates:
                                confirmed = max(
                                    candidates,
                                    key=lambda pos: _timestamp_seconds(pos.get("entry_time")),
                                )
                        if confirmed and hasattr(self.state_manager, "mark_execution_verification"):
                            self.state_manager.mark_execution_verification(
                                "broker_position_confirmed",
                                True,
                                last_broker_ticket=confirmed.get("ticket"),
                                last_confirmed_position=confirmed,
                            )
                            self.state_manager.mark_execution_verification(
                                "runtime_position_synced",
                                True,
                                last_confirmed_position=confirmed,
                            )
                            
                    # Sync pending orders
                    orders = mt5_lib.orders_get()
                    if orders is not None:
                        for o in orders:
                            pending_orders.append({
                                "ticket": int(o.ticket),
                                "symbol": o.symbol,
                                "type": str(o.type),
                                "price": float(o.price_open),
                                "volume": float(o.volume),
                                "sl": float(o.sl),
                                "tp": float(o.tp)
                            })
                else:
                    # --- Simulation Mode Polling ---
                    import random
                    last_price = self.state_manager.last_price or 2000.0
                    price = last_price + random.uniform(-0.15, 0.15)
                    spread = 12.0 + random.uniform(-0.5, 0.5)
                    bid = price - (spread * 0.01 / 2.0)
                    ask = price + (spread * 0.01 / 2.0)
                    
                    # Update simulated positions live PnL and simulate exit breaches
                    still_active = []
                    for pos in self.simulated_positions:
                        direction_factor = 1.0 if pos["direction"] == "BUY" else -1.0
                        # PnL = (current_price - entry_price) * volume * multiplier
                        # Gold multiplier is typically 100
                        mult = 100.0 if "XAU" in pos.get("symbol", "") else 1.0
                        live_pnl = (price - pos["entry_price"]) * pos["lot"] * direction_factor * mult
                        pos["live_pnl"] = live_pnl
                        pos["profit"] = live_pnl
                        
                        # Check exit hit simulation
                        hit = False
                        if pos["direction"] == "BUY":
                            if pos["sl"] > 0 and price <= pos["sl"]:
                                hit = True
                            elif pos["tp"] > 0 and price >= pos["tp"]:
                                hit = True
                        else:
                            if pos["sl"] > 0 and price >= pos["sl"]:
                                hit = True
                            elif pos["tp"] > 0 and price <= pos["tp"]:
                                hit = True
                                
                        if not hit:
                            still_active.append(pos)
                        else:
                            balance += live_pnl
                            equity += live_pnl
                            self.state_manager.record_trade_outcome(live_pnl)
                            
                    self.simulated_positions = still_active
                    active_positions = list(self.simulated_positions)
                    
                    # Calculate total simulated PnL
                    total_sim_pnl = sum(p["live_pnl"] for p in active_positions)
                    equity = balance + total_sim_pnl

                # 2. Write synchronized metrics back to State Manager thread-safely
                self.state_manager.active_positions = active_positions
                self.state_manager.last_price = price
                self.state_manager.last_spread = spread
                runtime_snapshot = {
                    "current_price": price,
                    "bid": bid,
                    "ask": ask,
                    "spread": spread,
                    "symbol": runtime_symbol,
                    "positions": active_positions,
                    "orders": pending_orders,
                }
                self.state_manager.set_runtime_snapshot(runtime_snapshot)

                if price:
                    self._evaluate_trade_plan_state(price=price, bid=bid, ask=ask, spread=spread)
                
                # Check for emergency shutdown limits
                self.state_manager.check_emergency_lock()

                # Update live state snapshot fields
                self.snapshot_store.update_snapshot(
                    runtime_snapshot=runtime_snapshot,
                    active_positions=active_positions,
                    pending_orders=pending_orders,
                    active_trade_plan=self.state_manager.active_trade_plan or {},
                    macro_context=self.state_manager.macro_context,
                    live_trade_state=self.state_manager.live_trade_state,
                    live_metrics={
                        "balance": balance,
                        "equity": equity,
                        "leverage": leverage,
                        "currency": currency,
                        "daily_pnl": equity - 10000.0 # relative to initial $10k
                    },
                    market_state={
                        "regime": self.state_manager.current_regime,
                        "macro_direction": getattr(self.state_manager, "macro_direction", "NEUTRAL"),
                        "phase": self.state_manager.market_phase,
                        "stress_index": self.state_manager.stress_level,
                        "price": price,
                        "spread": spread,
                        "volatility": self.state_manager.last_volatility,
                        "collapse_prob": self.state_manager.regime_collapse_prob
                    }
                )

            except Exception as e:
                logger.error(f"Error in MT5 poller cycle: {e}", exc_info=True)
                
            # Market monitor loop cadence. Keep this lightweight; analysis is
            # candle-bound in OrchestrationRuntime.
            time.sleep(15.0)
