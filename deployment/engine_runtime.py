"""
deployment/engine_runtime.py
Main coordinate engine runtime managing threads, loop heartbeats, and lifecycles.
"""
import logging
import threading
import pandas as pd
from typing import Dict, Any

from deployment.snapshot_store import SnapshotStore
from deployment.live_state_snapshot import LiveStateSnapshot
from deployment.live_state_manager import LiveStateManager
from deployment.auto_trade_engine import AutoTradeEngine
from deployment.trading_modes import get_mode, DEFAULT_MODE_NAME

from deployment.mt5_runtime import MT5Runtime
from deployment.orchestration_runtime import OrchestrationRuntime
from deployment.event_runtime import EventRuntime

logger = logging.getLogger("EngineRuntime")


class EngineRuntime:
    """
    Coordinates mt5_runtime, orchestration_runtime, and event_runtime.
    States: STOPPED | STARTING | RUNNING | PAUSED | RECOVERING | CRASHED
    """

    def __init__(self):
        self.state = "STOPPED"
        self.error_log = []
        self.lock = threading.Lock()
        
        # Telemetry symbol
        self.symbol = "UNKNOWN"
        
        # Primary state snapshot stores
        self.state_manager = LiveStateManager()
        self.engine = AutoTradeEngine(self.state_manager)
        self.snapshot_store = SnapshotStore()
        
        # Child runtimes
        self.mt5 = MT5Runtime(self.snapshot_store, self.state_manager)
        self.mt5.execution_engine = self.engine
        self.engine.set_execution_broker(self.mt5)
        self.orchestration = OrchestrationRuntime(self.snapshot_store, self.state_manager, self.engine)
        self.event = EventRuntime(self)
        
        # Apply default trading mode
        self._apply_trading_mode(DEFAULT_MODE_NAME)
        
        # Keep properties to avoid breaking legacy code
        self.latest_orch_ctx = None
        self.recommended_strategy = None
        self.optimization_result = None
        self.optimization_results = None

    @property
    def uploaded_df(self) -> pd.DataFrame:
        return self.orchestration.bundle.get("h1", pd.DataFrame()) # fallback to h1 df for display

    @property
    def h1_df(self) -> pd.DataFrame:
        return self.orchestration.bundle.get("h1", pd.DataFrame())

    @property
    def m15_df(self) -> pd.DataFrame:
        return self.orchestration.bundle.get("m15", pd.DataFrame())

    def start(self) -> str:
        """Starts all child runtimes and shifts state to RUNNING."""
        with self.lock:
            if self.state in ("RUNNING", "STARTING"):
                return self.state
            
            logger.info("Initializing child runtimes...")
            self.state = "STARTING"
            
            # Start event dispatcher, mt5 syncer, and analytical pipeline loop
            self.event.start()
            self.mt5.start()
            self.orchestration.start()
            
            self.state = "RUNNING"
            self.state_manager.event_bus.emit("Engine Runtime background systems started.", "INFO")
            return self.state

    def stop(self) -> str:
        """Stops all child threads safely."""
        with self.lock:
            if self.state in ("STOPPED", "STOPPING"):
                return self.state
            
            logger.info("Shutting down background system loops...")
            self.state = "STOPPING"
            
            self.mt5.stop()
            self.orchestration.stop()
            self.event.stop()
            
            self.state = "STOPPED"
            self.state_manager.event_bus.emit("Engine Runtime background systems stopped.", "INFO")
            return self.state

    def pause(self) -> str:
        """Pauses processing."""
        with self.lock:
            if self.state == "RUNNING":
                self.state = "PAUSED"
                self.state_manager.set_engine_state("PAUSED")
                self.state_manager.event_bus.emit("Engine Runtime paused.", "WARNING")
        return self.state

    def resume(self) -> str:
        """Resumes background processing."""
        with self.lock:
            if self.state == "PAUSED":
                self.state = "RUNNING"
                self.state_manager.set_engine_state("IDLE")
                self.state_manager.event_bus.emit("Engine Runtime resumed.", "INFO")
        return self.state

    def trigger_crash(self, reason: str) -> str:
        """Puts system into a crash lock state."""
        logger.critical(f"System crash detected: {reason}")
        with self.lock:
            self.state = "CRASHED"
            self.state_manager.set_engine_state("EMERGENCY")
            self.error_log.append(reason)
            self.stop()
        return self.state

    def recover(self) -> str:
        """Recovers system from CRASHED state."""
        with self.lock:
            if self.state != "CRASHED":
                return self.state
            logger.info("Recovering system states...")
            self.state_manager.reset_daily_stats()
            self.state = "STOPPED"
        return self.state

    def set_symbol(self, symbol: str) -> None:
        """Updates active symbol across sub-systems."""
        with self.lock:
            self.symbol = symbol
            self.orchestration.symbol = symbol
            if hasattr(self.mt5, "set_symbol"):
                self.mt5.set_symbol(symbol)
            self.state_manager.event_bus.emit(f"Active asset updated to: {symbol}", "INFO")

    def set_timeframe(self, timeframe: str) -> None:
        """Updates the selected execution timeframe across sub-systems."""
        timeframe = str(timeframe or "M5").strip().upper()
        if timeframe not in {"M1", "M5", "M15", "H1", "H4", "D1"}:
            timeframe = "M5"
        self.state_manager.watchlist_timeframe = timeframe
        if hasattr(self.orchestration, "set_timeframe"):
            self.orchestration.set_timeframe(timeframe)

    def set_trading_mode(self, mode_name: str) -> None:
        """Switches the active trading mode across all sub-systems."""
        self._apply_trading_mode(mode_name)
        self.state_manager.event_bus.emit(f"Trading mode switched to: {mode_name}", "INFO")

    def _apply_trading_mode(self, mode_name: str) -> None:
        """Internal: applies a trading mode's settings to engine and state."""
        from deployment.deployment_profile import AutoTradeDeploymentProfile
        mode = get_mode(mode_name)
        self.state_manager.active_trading_mode = mode.name
        profile = AutoTradeDeploymentProfile(
            name=mode.name,
            minimum_confidence=mode.default_confidence,
            max_spread=mode.max_spread,
            max_positions=mode.max_positions,
            allowed_sessions=list(mode.allowed_sessions),
            risk_per_trade=mode.risk_per_trade,
        )
        self.engine.set_profile(profile)
        self.set_timeframe(mode.timeframe)

    def run_pipeline_eval(self, bundle: dict) -> None:
        """Compatibility method mapping CSV uploads and downloads to the pipeline."""
        symbol = bundle.get("symbol", self.symbol)
        self.orchestration.set_dataset_bundle(bundle, symbol)

    def update_replay_mode(self, active: bool) -> None:
        """Toggles replay mode."""
        self.orchestration.update_replay_mode(active)


# Global singleton instance factory
_global_runtime = None
_runtime_lock = threading.Lock()

def get_global_runtime() -> EngineRuntime:
    global _global_runtime
    with _runtime_lock:
        if _global_runtime is None:
            _global_runtime = EngineRuntime()
        return _global_runtime
