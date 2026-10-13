"""
deployment/event_runtime.py
Asynchronous thread-safe command and event queue manager for NexusBot V3.
"""
import queue
import threading
import logging
from typing import Dict, Any, Callable

logger = logging.getLogger("EventRuntime")


class EventRuntime:
    """
    Manages the queue of user actions/commands dispatched from the Streamlit UI.
    Processes commands asynchronously in a background thread to decouple presentation from execution.
    """

    def __init__(self, runtime=None):
        self.runtime = runtime  # Reference to parent EngineRuntime
        self.cmd_queue = queue.Queue()
        self.thread = None
        self._stop_event = threading.Event()
        self.handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._register_default_handlers()

    def start(self) -> None:
        """Starts the command dispatch loop thread."""
        if self.thread and self.thread.is_alive():
            return
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, name="NexusBotEventLoop", daemon=True)
        self.thread.start()
        logger.info("Event Runtime thread started.")

    def stop(self) -> None:
        """Stops the command dispatch loop thread."""
        self._stop_event.set()
        # Put dummy item to unblock queue.get()
        self.cmd_queue.put(("STOP", {}))
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("Event Runtime thread stopped.")

    def dispatch(self, cmd_name: str, params: Dict[str, Any] | None = None) -> None:
        """Puts a command into the dispatch queue."""
        if params is None:
            params = {}
        self.cmd_queue.put((cmd_name, params))
        logger.info(f"Dispatched command: {cmd_name} with params: {params}")

    def register_handler(self, cmd_name: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a custom handler for a command."""
        self.handlers[cmd_name] = handler

    def _register_default_handlers(self) -> None:
        self.register_handler("SET_MODE", self._handle_set_mode)
        self.register_handler("SET_PROFILE", self._handle_set_profile)
        self.register_handler("SET_SYMBOL", self._handle_set_symbol)
        self.register_handler("RESET_LOCKS", self._handle_reset_locks)
        self.register_handler("RUN_PIPELINE", self._handle_run_pipeline)
        self.register_handler("PLACE_ORDER", self._handle_place_order)
        self.register_handler("CLOSE_POSITION", self._handle_close_position)
        self.register_handler("EMERGENCY_FLATTEN", self._handle_emergency_flatten)
        self.register_handler("REPLAY_TOGGLE", self._handle_replay_toggle)
        self.register_handler("REPLAY_STEP", self._handle_replay_step)
        self.register_handler("REPLAY_SEEK", self._handle_replay_seek)
        self.register_handler("REPLAY_SET_SPEED", self._handle_replay_set_speed)
        self.register_handler("REPLAY_RESET", self._handle_replay_reset)
        self.register_handler("SET_AI_PROVIDER", self._handle_set_ai_provider)
        self.register_handler("GENERATE_NARRATIVE", self._handle_generate_narrative)
        self.register_handler("SET_TRADING_MODE", self._handle_set_trading_mode)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                cmd_name, params = self.cmd_queue.get(timeout=1.0)
                if cmd_name == "STOP":
                    self.cmd_queue.task_done()
                    break

                handler = self.handlers.get(cmd_name)
                if handler:
                    try:
                        logger.info(f"Executing command: {cmd_name}")
                        handler(params)
                    except Exception as e:
                        logger.error(f"Error executing handler for {cmd_name}: {e}", exc_info=True)
                        if self.runtime:
                            self.runtime.state_manager.event_bus.emit(
                                f"Command {cmd_name} failed: {e}", "CRITICAL"
                            )
                else:
                    logger.warning(f"No handler registered for command: {cmd_name}")

                self.cmd_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in Event loop: {e}", exc_info=True)

    # ── Command Handlers ──────────────────────────────────────────────────────

    def _handle_set_mode(self, params: Dict[str, Any]) -> None:
        mode = params.get("mode", "ADVISORY")
        if self.runtime:
            self.runtime.state_manager.deployment_mode = mode
            self.runtime.state_manager.event_bus.emit(f"Execution mode updated to: {mode}", "INFO")

    def _handle_set_profile(self, params: Dict[str, Any]) -> None:
        profile_name = params.get("profile_name", "Momentum Moderate")
        if self.runtime:
            from deployment.deployment_profile import get_preset
            profile = get_preset(profile_name)
            self.runtime.engine.set_profile(profile)
            self.runtime.state_manager.event_bus.emit(f"Active profile updated to: {profile_name}", "INFO")

    def _handle_set_symbol(self, params: Dict[str, Any]) -> None:
        symbol = params.get("symbol", "UNKNOWN")
        if self.runtime:
            self.runtime.set_symbol(symbol)

    def _handle_reset_locks(self, params: Dict[str, Any]) -> None:
        if self.runtime:
            self.runtime.state_manager.reset_daily_stats()
            self.runtime.resume()

    def _handle_run_pipeline(self, params: Dict[str, Any]) -> None:
        if self.runtime and self.runtime.orchestration:
            self.runtime.orchestration.trigger_evaluation()

    def _handle_place_order(self, params: Dict[str, Any]) -> None:
        if not self.runtime:
            return
        direction = params.get("direction", "BUY")
        lot = params.get("lot", 0.01)
        sl = params.get("sl", 0.0)
        tp = params.get("tp", 0.0)
        comment = params.get("comment", "Manual Place")
        symbol = str(params.get("symbol") or self.runtime.symbol).strip().upper()

        self.runtime.state_manager.event_bus.emit(
            f"Dispatching order request: {direction} {lot} lots of {symbol}", "INFO"
        )
        res = self.runtime.mt5.place_live_order(
            symbol=symbol, direction=direction, lot=lot, sl=sl, tp=tp, comment=comment
        )
        if res.get("ticket", -1) > 0:
            self.runtime.state_manager.event_bus.emit(
                f"Order execution confirmed: Ticket #{res['ticket']}", "INFO"
            )
        else:
            self.runtime.state_manager.event_bus.emit(
                f"Order execution failed: {res.get('error') or res.get('comment')}", "CRITICAL"
            )

    def _handle_close_position(self, params: Dict[str, Any]) -> None:
        if not self.runtime:
            return
        ticket = params.get("ticket")
        if not ticket:
            return
        # Find position to get direction and volume
        pos = next((p for p in self.runtime.state_manager.active_positions if p["ticket"] == ticket), None)
        if not pos:
            self.runtime.state_manager.event_bus.emit(f"Close failed: Ticket #{ticket} not found.", "WARNING")
            return

        direction = pos.get("direction", "BUY")
        lot = pos.get("lot") or pos.get("qty", 0.01)
        symbol = pos.get("symbol", self.runtime.symbol)

        self.runtime.state_manager.event_bus.emit(f"Dispatching close request for Position #{ticket}", "INFO")
        res = self.runtime.mt5.close_live_position(
            symbol=symbol, ticket=ticket, direction=direction, lot=lot
        )
        if res.get("error") is None:
            # Remove from local active positions
            removed = self.runtime.state_manager.remove_position(ticket)
            if removed:
                # Add profit to balance
                pnl = pos.get("live_pnl", 0.0)
                self.runtime.engine.balance += pnl
                self.runtime.state_manager.record_trade_outcome(pnl)
            self.runtime.state_manager.event_bus.emit(f"Position #{ticket} closed successfully.", "INFO")
        else:
            self.runtime.state_manager.event_bus.emit(f"Close #{ticket} failed: {res['error']}", "CRITICAL")

    def _handle_emergency_flatten(self, params: Dict[str, Any]) -> None:
        if not self.runtime:
            return
        self.runtime.state_manager.event_bus.emit("🚨 Emergency Flatten command triggered by operator.", "CRITICAL")
        
        # Flatten MT5 positions
        for pos in list(self.runtime.state_manager.active_positions):
            ticket = pos["ticket"]
            direction = pos["direction"]
            lot = pos.get("lot") or pos.get("qty", 0.01)
            symbol = pos.get("symbol", self.runtime.symbol)
            res = self.runtime.mt5.close_live_position(symbol=symbol, ticket=ticket, direction=direction, lot=lot)
            if res.get("error") is None:
                self.runtime.state_manager.remove_position(ticket)
                self.runtime.engine.balance += pos.get("live_pnl", 0.0)
                self.runtime.state_manager.record_trade_outcome(pos.get("live_pnl", 0.0))
        
        self.runtime.state_manager.set_engine_state("EMERGENCY")

    def _handle_replay_toggle(self, params: Dict[str, Any]) -> None:
        active = params.get("active", False)
        if self.runtime:
            # Toggle replay state
            self.runtime.update_replay_mode(active)

    def _handle_replay_step(self, params: Dict[str, Any]) -> None:
        if self.runtime and self.runtime.orchestration:
            self.runtime.orchestration.step_replay()

    def _handle_replay_seek(self, params: Dict[str, Any]) -> None:
        pointer = params.get("pointer", 200)
        if self.runtime and self.runtime.orchestration:
            self.runtime.orchestration.seek_replay(pointer)

    def _handle_replay_set_speed(self, params: Dict[str, Any]) -> None:
        speed = params.get("speed", 1.0)
        if self.runtime and self.runtime.orchestration:
            self.runtime.orchestration.set_replay_speed(speed)

    def _handle_replay_reset(self, params: Dict[str, Any]) -> None:
        if self.runtime and self.runtime.orchestration:
            self.runtime.orchestration.reset_replay()

    def _handle_set_ai_provider(self, params: Dict[str, Any]) -> None:
        if self.runtime:
            provider = params.get("provider", "Deterministic Heuristic")
            api_key = params.get("api_key", "")
            model = params.get("model", "")
            base_url = params.get("base_url", "")
            temp = params.get("temperature", 0.2)
            max_tokens = params.get("max_tokens", 1000)
            
            # Save in snapshot
            ai_config = {
                "provider": provider,
                "api_key": api_key,
                "model": model,
                "base_url": base_url,
                "temperature": temp,
                "max_tokens": max_tokens
            }
            # We can test connection here and update status
            from providers.provider_manager import get_provider_manager
            pm = get_provider_manager()
            pm.configure(ai_config)
            
            connected = pm.test_connection()
            status = "CONNECTED" if connected else "FAILED"
            
            self.runtime.snapshot_store.update_snapshot(
                ai_narrative={
                    "status": status,
                    "provider": provider,
                    "model": model
                }
            )
            self.runtime.state_manager.event_bus.emit(f"AI Provider switched to {provider}. Connection: {status}", "INFO")

    def _handle_generate_narrative(self, params: Dict[str, Any]) -> None:
        if not self.runtime:
            return
        self.runtime.state_manager.event_bus.emit("Querying AI Provider for narrative briefing...", "INFO")
        
        # Pull orchestration context
        orch_ctx = self.runtime.latest_orch_ctx
        if not orch_ctx:
            self.runtime.state_manager.event_bus.emit("Narrative generation failed: No orchestration context available.", "WARNING")
            return
            
        from providers.provider_manager import get_provider_manager
        pm = get_provider_manager()
        
        try:
            briefing = pm.generate_briefing(orch_ctx)
            if briefing:
                self.runtime.state_manager.event_bus.emit("AI Narrative Briefing generated successfully.", "INFO")
                # Store in snapshot
                curr_narr = self.runtime.snapshot_store.get_snapshot().ai_narrative.copy()
                curr_narr.update(briefing)
                self.runtime.snapshot_store.update_snapshot(ai_narrative=curr_narr)
            else:
                self.runtime.state_manager.event_bus.emit("AI Provider failed to return a briefing. Check API settings.", "ERROR")
        except Exception as e:
            logger.error(f"Error generating AI narrative: {e}", exc_info=True)
            self.runtime.state_manager.event_bus.emit(f"Narrative generation error: {e}", "ERROR")

    def _handle_set_trading_mode(self, params: Dict[str, Any]) -> None:
        if not self.runtime:
            return
        mode_name = params.get("mode", "Aggressive Scalper")
        self.runtime.set_trading_mode(mode_name)
