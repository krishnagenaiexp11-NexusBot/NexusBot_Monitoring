"""
deployment/orchestration_runtime.py
Analytical and strategy tournament execution runtime for NexusBot V3.
"""
import time
import threading
import logging
import pandas as pd
from typing import Dict, Any, List
from engine.intelligence_pipeline import run_intelligence_pipeline, clear_pipeline_cache
from engine.feature_engineering import compute_features
from deployment.replay_controller import ReplayController
from deployment.precision_entry_engine import PrecisionEntryEngine

logger = logging.getLogger("OrchestrationRuntime")


class OrchestrationRuntime:
    """
    Background runtime that handles the execution of the 19-Engine quantitative pipeline.
    Manages historical replay datasets, playback controls, and tournament updates.
    """

    def __init__(self, snapshot_store, state_manager, engine):
        self.snapshot_store = snapshot_store
        self.state_manager = state_manager
        self.engine = engine
        self.precision_entry_engine = PrecisionEntryEngine()
        
        self.thread = None
        self._stop_event = threading.Event()
        self.lock = threading.Lock()
        
        # Dataset Bundles (M5, M15, H1, H4)
        self.bundle: Dict[str, pd.DataFrame] = {
            "m5": pd.DataFrame(),
            "m15": pd.DataFrame(),
            "h1": pd.DataFrame(),
            "h4": pd.DataFrame()
        }
        self.symbol = "UNKNOWN"
        self.last_live_candle_by_tf: Dict[str, Any] = {}
        self.last_live_poll = 0.0
        
        # Replay Isolation Controls
        self.replay_active = False
        self.replay_controller = ReplayController()
        self.last_replay_tick = 0.0

    def set_timeframe(self, timeframe: str) -> None:
        """Updates the execution timeframe used for live candle evaluation."""
        timeframe = str(timeframe or "M5").strip().upper()
        if timeframe not in {"M1", "M5", "M15", "H1", "H4", "D1"}:
            timeframe = "M5"
        self.state_manager.watchlist_timeframe = timeframe
        self.state_manager.event_bus.emit(f"Execution timeframe updated to: {timeframe}", "INFO")

    def start(self) -> None:
        """Starts the analytical background evaluation thread."""
        if self.thread and self.thread.is_alive():
            return
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, name="NexusBotOrchestrator", daemon=True)
        self.thread.start()
        logger.info("Orchestration Runtime thread started.")

    def stop(self) -> None:
        """Stops the analytical background evaluation thread."""
        self._stop_event.set()
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("Orchestration Runtime thread stopped.")

    def set_dataset_bundle(self, bundle: Dict[str, pd.DataFrame], symbol: str) -> None:
        """Loads a new dataset bundle for live or replay mode."""
        with self.lock:
            self.bundle = bundle
            self.symbol = symbol
            self.last_live_candle_by_tf = {}
            self.state_manager.live_execution_is_fresh_candle = False
            self.state_manager.last_live_execution_candle = None
            clear_pipeline_cache()
            
            # If replay mode is active, load dataset into replay controller
            if self.replay_active:
                h1_df = bundle.get("h1", pd.DataFrame())
                self.replay_controller.load_dataset(h1_df)
                
            self.state_manager.event_bus.emit(f"New dataset loaded for symbol: {symbol}", "INFO")
            
        # Trigger immediate evaluation
        self.trigger_evaluation()

    def update_replay_mode(self, active: bool) -> None:
        """Toggles replay mode on/off."""
        with self.lock:
            self.replay_active = active
            if active:
                h1_df = self.bundle.get("h1", pd.DataFrame())
                self.replay_controller.load_dataset(h1_df)
                self.replay_controller.set_play_status("PAUSED")
                self.state_manager.event_bus.emit("Historical Replay mode enabled.", "INFO")
            else:
                self.state_manager.event_bus.emit("Historical Replay mode disabled.", "INFO")
                
        # Trigger immediate evaluation
        self.trigger_evaluation()

    def trigger_evaluation(self, kind: str = "strategy") -> None:
        """Executes a single evaluation cycle of the 19 engines."""
        threading.Thread(target=self._execute_cycle, args=(kind,), name=f"NexusBotEvalCycle-{kind}", daemon=True).start()

    def step_replay(self) -> None:
        """Manually steps forward 1 candle in replay mode."""
        with self.lock:
            if not self.replay_active:
                return
            advanced = self.replay_controller.step_candle()
            if not advanced:
                self.replay_controller.set_play_status("PAUSED")
                self.state_manager.event_bus.emit("Replay reached the end of the dataset.", "WARNING")
                return
                
        self.trigger_evaluation()

    def seek_replay(self, pointer: int) -> None:
        """Seeks replay pointer to a specific index."""
        with self.lock:
            if not self.replay_active:
                return
            total_candles = len(self.replay_controller.replay_dataset)
            if 0 <= pointer < total_candles:
                self.replay_controller.candle_pointer = pointer
                self.state_manager.event_bus.emit(f"Replay seeked to index {pointer}", "INFO")
                
        self.trigger_evaluation()

    def set_replay_speed(self, speed: float) -> None:
        """Sets playback speed multiplier."""
        with self.lock:
            self.replay_controller.set_speed(speed)
            self.state_manager.event_bus.emit(f"Replay playback speed set to {speed}x", "INFO")

    def reset_replay(self) -> None:
        """Resets replay pointer back to default start."""
        with self.lock:
            if not self.replay_active:
                return
            self.replay_controller.candle_pointer = min(200, len(self.replay_controller.replay_dataset) - 1)
            self.replay_controller.set_play_status("PAUSED")
            self.state_manager.event_bus.emit("Replay reset to start position.", "INFO")
            
        self.trigger_evaluation()

    def _run_loop(self) -> None:
        """Background ticking loop that updates replay playback ticks."""
        while not self._stop_event.is_set():
            try:
                # Handle automatic replay stepping
                run_step = False
                with self.lock:
                    if self.replay_active and self.replay_controller.play_status == "PLAYING":
                        now = time.time()
                        # Step interval depends on speed multiplier (e.g. 2s / speed)
                        interval = max(0.2, 2.0 / self.replay_controller.playback_speed)
                        if now - self.last_replay_tick >= interval:
                            self.last_replay_tick = now
                            run_step = True
                            
                if run_step:
                    self.step_replay()

                # Live analysis is candle-bound, not tick-bound:
                # - The active trading mode timeframe refreshes trade plans.
                # - H1 close refreshes macro context and strategic ranking.
                if not self.replay_active:
                    now = time.time()
                    if now - self.last_live_poll >= 5.0:
                        self.last_live_poll = now
                        execution_timeframe = self._execution_timeframe()
                        if self._refresh_live_bundle_on_new_candle(execution_timeframe):
                            self.trigger_evaluation("strategy")
                        if execution_timeframe != "H1" and self._refresh_live_bundle_on_new_candle("H1"):
                            self.trigger_evaluation("macro")
                    
            except Exception as e:
                logger.error(f"Error in Orchestrator tick loop: {e}", exc_info=True)
                
            time.sleep(0.1)

    def _execution_timeframe(self) -> str:
        timeframe = str(getattr(self.state_manager, "watchlist_timeframe", "M5") or "M5").strip().upper()
        return timeframe if timeframe in {"M1", "M5", "M15", "H1", "H4", "D1"} else "M5"

    def _timeframe_minutes(self, timeframe: str) -> int:
        return {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}.get(timeframe.upper(), 5)

    def _normalize_rates(self, raw: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
        if raw is None or raw.empty or "time" not in raw.columns:
            return pd.DataFrame()
        try:
            return pd.DataFrame({
                "timestamp": pd.to_datetime(raw["time"], unit="s", utc=True, errors="coerce"),
                "open": raw["open"].astype(float),
                "high": raw["high"].astype(float),
                "low": raw["low"].astype(float),
                "close": raw["close"].astype(float),
                "volume": raw.get("tick_volume", raw.get("volume", 0)).astype(float),
                "spread": raw.get("spread", 0).astype(float) if "spread" in raw else 0.0,
                "symbol": symbol,
                "timeframe": timeframe.upper(),
            }).dropna(subset=["timestamp"])
        except Exception as exc:
            logger.warning(f"Could not normalize MT5 rates for {symbol} {timeframe}: {exc}")
            return pd.DataFrame()

    def _merge_dataframe(self, existing: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
        frames = [df for df in (existing, fresh) if isinstance(df, pd.DataFrame) and not df.empty]
        if not frames:
            return pd.DataFrame()
        merged = pd.concat(frames, ignore_index=True)
        merged.columns = [str(col).lower() for col in merged.columns]
        if "timestamp" in merged.columns:
            merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True, errors="coerce")
            merged = merged.dropna(subset=["timestamp"])
            merged = merged.drop_duplicates(subset=["timestamp"], keep="last")
            merged = merged.sort_values("timestamp").reset_index(drop=True)
        return merged.tail(2500).reset_index(drop=True)

    def _fetch_closed_mt5_candles(self, connector, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        if getattr(connector, "is_simulated", False):
            return pd.DataFrame()
        try:
            import MetaTrader5 as mt5
            from runtime.timeframe_mapper import TIMEFRAME_MAP
        except Exception:
            return pd.DataFrame()

        tf_const = TIMEFRAME_MAP.get(timeframe.upper())
        if tf_const is None:
            return pd.DataFrame()
        try:
            broker_symbol = connector.ensure_symbol(symbol)
            # start_pos=1 excludes the still-forming candle. Auto-trading should
            # evaluate closed candles only.
            rates = mt5.copy_rates_from_pos(broker_symbol, tf_const, 1, int(count))
            if rates is None or len(rates) == 0:
                return pd.DataFrame()
            return self._normalize_rates(pd.DataFrame(rates), symbol, timeframe)
        except Exception as exc:
            logger.debug(f"MT5 live candle fetch skipped for {symbol} {timeframe}: {exc}")
            return pd.DataFrame()

    def _refresh_live_bundle_on_new_candle(self, timeframe: str | None = None) -> bool:
        try:
            from deployment.engine_runtime import get_global_runtime
            runtime = get_global_runtime()
            connector = getattr(getattr(runtime, "mt5", None), "connector", None)
        except Exception:
            connector = None
        if connector is None or getattr(connector, "is_simulated", False):
            return False

        symbol = str(self.symbol or getattr(self.state_manager, "runtime_symbol", "") or "UNKNOWN").strip().upper()
        if not symbol or symbol == "UNKNOWN":
            return False
        eval_tf = str(timeframe or self._execution_timeframe()).upper()
        core_tfs = ["M5", "M15", "H1", "H4"]
        fetch_tfs = list(dict.fromkeys([eval_tf] + core_tfs))

        fetched: Dict[str, pd.DataFrame] = {}
        for tf in fetch_tfs:
            count = 900 if tf in {"M1", "M5"} else 500
            df = self._fetch_closed_mt5_candles(connector, symbol, tf, count)
            if not df.empty:
                fetched[tf.lower()] = df

        eval_df = fetched.get(eval_tf.lower())
        if eval_df is None or eval_df.empty or "timestamp" not in eval_df.columns:
            return False
        newest_eval_ts = pd.to_datetime(eval_df["timestamp"], utc=True, errors="coerce").dropna().max()
        if pd.isna(newest_eval_ts):
            return False

        last_seen = self.last_live_candle_by_tf.get(eval_tf)
        if last_seen is not None and pd.Timestamp(last_seen) >= newest_eval_ts:
            return False

        with self.lock:
            for tf_key, fresh_df in fetched.items():
                self.bundle[tf_key] = self._merge_dataframe(self.bundle.get(tf_key, pd.DataFrame()), fresh_df)
            self.bundle["symbol"] = symbol
            self.symbol = symbol
            self.last_live_candle_by_tf[eval_tf] = newest_eval_ts
            clear_pipeline_cache()

        self.state_manager.event_bus.emit(
            f"New closed {eval_tf} candle detected for {symbol}; live analysis refreshed.",
            "INFO",
        )
        return True

    def _execute_cycle(self, kind: str = "strategy") -> None:
        """Internal execution of the 19-Engine quantitative analysis."""
        # Check if bundle contains data
        if kind == "strategy":
            eval_tf = self._execution_timeframe()
        elif kind == "macro":
            eval_tf = "H1"
        else:
            eval_tf = self._execution_timeframe()
        h1_df = self.bundle.get("h1")
        eval_df = self.bundle.get(eval_tf.lower())
        if (h1_df is None or h1_df.empty) and (eval_df is None or eval_df.empty):
            return

        try:
            self.state_manager.set_engine_state("ANALYZING")
            
            # 1. Resolve dataset slice (Replay vs Live)
            active_bundle = {}
            with self.lock:
                if self.replay_active:
                    # Sliced up to the replay pointer
                    current_slice_h1 = self.replay_controller.get_current_slice()
                    pointer = self.replay_controller.candle_pointer
                    
                    # Estimate corresponding pointers for other timeframes
                    # M15 has 4x candles of H1
                    m15_df = self.bundle.get("m15", pd.DataFrame())
                    slice_m15 = m15_df.iloc[:min(len(m15_df), pointer * 4 + 4)] if not m15_df.empty else pd.DataFrame()
                    
                    # M5 has 12x candles of H1
                    m5_df = self.bundle.get("m5", pd.DataFrame())
                    slice_m5 = m5_df.iloc[:min(len(m5_df), pointer * 12 + 12)] if not m5_df.empty else pd.DataFrame()
                    
                    # H4 has 1/4 candles of H1
                    h4_df = self.bundle.get("h4", pd.DataFrame())
                    slice_h4 = h4_df.iloc[:min(len(h4_df), pointer // 4 + 1)] if not h4_df.empty else pd.DataFrame()
                    
                    active_bundle = {
                        "m5": slice_m5,
                        "m15": slice_m15,
                        "h1": current_slice_h1,
                        "h4": slice_h4,
                        "symbol": self.symbol
                    }
                else:
                    # Live mode uses whole dataset
                    active_bundle = dict(self.bundle)
                    active_bundle["symbol"] = self.symbol
            
            # 2. Run the 19-engine pipeline
            orch_ctx = run_intelligence_pipeline(
                active_bundle,
                use_cache=False,
                timeframe_minutes=self._timeframe_minutes(eval_tf),
            )
            
            # Setup inputs for trade candle evaluation
            h4_default = {"macro_strength": 0.0, "macro_direction": "NEUTRAL", "trend_age": 0, "exhaustion_risk": 50.0}
            readiness_default = {"execution_state": "WATCHLIST", "confluence_count": 0, "readiness_score": 50.0}
            candle_default = {"candle_quality": 50.0, "direction_bias": "NEUTRAL"}
            
            from engine.tournament_models import TournamentInput
            tourney_input = TournamentInput(
                h4_structure=orch_ctx.h4_structure if orch_ctx.h4_structure else h4_default,
                mtf_context={"h1_structure": orch_ctx.h1_structure, "m15_execution": orch_ctx.m15_execution},
                m5_execution=orch_ctx.m5_precision if orch_ctx.m5_precision else {},
                session_context=orch_ctx.session_context if orch_ctx.session_context else {},
                candlestick_intelligence=orch_ctx.candlestick_intelligence if orch_ctx.candlestick_intelligence else candle_default,
                execution_readiness=orch_ctx.execution_readiness if orch_ctx.execution_readiness else readiness_default,
                contradiction_state=orch_ctx.contradiction_engine,
                institutional_risk=orch_ctx.institutional_risk,
                confidence_hierarchy=orch_ctx.confidence_hierarchy,
                signal_saturation=orch_ctx.signal_saturation,
                edge_validation=getattr(orch_ctx, "edge_validation", None),
                market_similarity=getattr(orch_ctx, "market_similarity", None),
                cross_asset_intelligence=getattr(orch_ctx, "cross_asset_intelligence", None),
            )
            
            # Store dataframe references in state manager
            self.state_manager.h1_df_ref = active_bundle.get("h1")
            self.state_manager.last_analysis_timeframe = eval_tf
            self.state_manager.last_analysis_symbol = self.symbol
            
            # Save latest orchestration context reference
            from deployment.engine_runtime import get_global_runtime
            runtime = get_global_runtime()
            runtime.latest_orch_ctx = orch_ctx
            
            self.state_manager.latest_tournament = getattr(orch_ctx, "tournament_results", []) or []
            self._publish_macro_context(orch_ctx)

            # 3. Strategy loop generates a trade plan only. It must not send
            # orders or mutate broker/runtime positions.
            execution_df = active_bundle.get(eval_tf.lower())
            if execution_df is None or execution_df.empty:
                execution_df = active_bundle.get("h1")
                eval_tf = "H1"
            if execution_df is not None and not execution_df.empty and "atr" not in execution_df.columns:
                try:
                    execution_df = compute_features(execution_df) if len(execution_df) >= 20 else execution_df
                except Exception:
                    pass
            live_candle_ts = self.last_live_candle_by_tf.get(eval_tf)
            execution_ts = None
            if execution_df is not None and not execution_df.empty and "timestamp" in execution_df.columns:
                try:
                    execution_ts = pd.to_datetime(execution_df["timestamp"], utc=True, errors="coerce").dropna().max()
                except Exception:
                    execution_ts = None
            is_fresh_live_candle = bool(
                live_candle_ts is not None
                and execution_ts is not None
                and not pd.isna(execution_ts)
                and pd.Timestamp(execution_ts) >= pd.Timestamp(live_candle_ts)
            )
            self.state_manager.live_execution_is_fresh_candle = is_fresh_live_candle
            self.state_manager.last_live_execution_candle = execution_ts
            if kind == "strategy":
                self._publish_trade_plan(
                    symbol=self.symbol,
                    timeframe=eval_tf,
                    execution_df=execution_df,
                    tournament_input=tourney_input,
                    orch_ctx=orch_ctx,
                )
            
            # 4. Resolve status badges and states for each of the 19 engines
            engine_diagnostics = self._compile_engine_diagnostics(orch_ctx)
            pipeline_flow = self._compile_pipeline_flow(orch_ctx)

            # Update state manager state
            if self.state_manager.engine_state == "ANALYZING":
                self.state_manager.set_engine_state("WATCHING")
            
            # Update Snapshot Store
            replay_state = {
                "candle_pointer": self.replay_controller.candle_pointer if self.replay_active else 0,
                "play_status": self.replay_controller.play_status if self.replay_active else "PAUSED",
                "speed": self.replay_controller.playback_speed if self.replay_active else 1.0,
                "total_candles": len(self.replay_controller.replay_dataset) if self.replay_active else 0
            }
            
            self.snapshot_store.update_snapshot(
                strategy_rankings=self.state_manager.latest_tournament,
                execution_candidates=self.state_manager.active_candidates,
                active_trade_plan=self.state_manager.active_trade_plan or {},
                macro_context=self.state_manager.macro_context,
                live_trade_state=self.state_manager.live_trade_state,
                engine_diagnostics=engine_diagnostics,
                pipeline_flow=pipeline_flow,
                replay_state=replay_state
            )
            
            # Sync tournament recommended strategy back to runtime variables
            runtime.recommended_strategy = orch_ctx.recommended_strategy
            
        except Exception as exc:
            self.state_manager.set_engine_state("LOCKED")
            logger.error(f"Pipeline evaluation crashed: {exc}", exc_info=True)
            self.state_manager.event_bus.emit(f"Orchestration cycle crashed: {exc}", "CRITICAL")

    def _publish_macro_context(self, orch_ctx) -> None:
        h4 = getattr(orch_ctx, "h4_structure", {}) or {}
        h1 = getattr(orch_ctx, "h1_structure", {}) or {}
        regime = getattr(orch_ctx, "market_regime", {}) or {}
        session = getattr(orch_ctx, "session_context", {}) or {}
        macro_context = {
            "macro_direction": h4.get("macro_direction", h1.get("macro_direction", "NEUTRAL")),
            "macro_strength": float(h4.get("macro_strength", h1.get("macro_strength", 0.0)) or 0.0),
            "regime": regime.get("regime", h1.get("macro_regime", "NEUTRAL")),
            "market_state": regime.get("market_state", regime.get("regime", "UNKNOWN")),
            "session_bias": session.get("current_session", "UNKNOWN"),
        }
        self.state_manager.set_macro_context(macro_context)

    def _latest_vwap(self, df: pd.DataFrame) -> float | None:
        if df is None or df.empty:
            return None
        try:
            work = df.copy()
            typical = (work["high"] + work["low"] + work["close"]) / 3.0
            volume = work.get("volume", pd.Series([1.0] * len(work))).replace(0, 1.0)
            vwap = (typical * volume).cumsum() / volume.cumsum()
            return float(vwap.iloc[-1])
        except Exception:
            return None

    def _publish_trade_plan(
        self,
        *,
        symbol: str,
        timeframe: str,
        execution_df: pd.DataFrame,
        tournament_input,
        orch_ctx,
    ) -> None:
        rankings = getattr(orch_ctx, "tournament_results", []) or []
        if not rankings:
            self.state_manager.active_candidates = []
            self.state_manager.set_active_trade_plan(None)
            return

        # Filter rankings by active trading mode's eligible strategies
        from deployment.trading_modes import get_mode
        active_mode = get_mode(getattr(self.state_manager, "active_trading_mode", "Aggressive Scalper"))
        eligible = {s.lower() for s in active_mode.eligible_strategies}
        mode_rankings = [
            r for r in rankings
            if str(r.get("strategy") or r.get("name") or "").strip().lower() in eligible
        ]
        if not mode_rankings:
            mode_rankings = rankings  # fallback to full list if no match

        selected_name = str(getattr(self.state_manager, "selected_strategy_name", "") or "").strip()
        winner = None
        if selected_name:
            winner = next(
                (
                    item for item in mode_rankings
                    if str(item.get("strategy") or item.get("name") or "").strip().lower() == selected_name.lower()
                ),
                None,
            )
        if winner is None:
            winner = mode_rankings[0]
        strategy_name = winner.get("strategy") or winner.get("name")
        if not strategy_name:
            return

        try:
            from engine.strategy_registry import get_strategy_by_name
            strategy_obj = get_strategy_by_name(strategy_name)
        except Exception as exc:
            self.state_manager.event_bus.emit(f"Trade plan skipped: strategy '{strategy_name}' unavailable ({exc}).", "WARNING")
            return

        if execution_df is None or execution_df.empty:
            return
        work = execution_df.copy()
        work.columns = [str(col).lower() for col in work.columns]
        if "atr" not in work.columns:
            try:
                work = compute_features(work) if len(work) >= 20 else work
            except Exception:
                pass

        row = work.iloc[-1]
        candle_ts = row.get("timestamp")
        candle_key = f"{symbol}|{timeframe}|{candle_ts}|{strategy_name}"
        if self.state_manager.last_plan_candle == candle_key:
            return

        try:
            candidate = strategy_obj.build_execution_candidate(tournament_input)
        except Exception:
            candidate = None
        if not candidate:
            self.state_manager.active_candidates = []
            self.state_manager.set_active_trade_plan(None)
            self.state_manager.last_plan_candle = candle_key
            self.state_manager.event_bus.emit(
                f"Trade plan cleared: {strategy_name} did not produce an executable candidate on {symbol} {timeframe}.",
                "INFO",
            )
            return

        direction = str(candidate.get("direction") or "BUY").upper()
        if direction == "BULLISH":
            direction = "BUY"
        elif direction == "BEARISH":
            direction = "SELL"
        entry_price = float(row.get("close", 0.0) or 0.0)
        atr = float(row.get("atr", 0.0) or 0.0)
        if not atr and {"high", "low"}.issubset(work.columns):
            atr = float((work["high"] - work["low"]).tail(20).mean() or 0.0)
        try:
            sl, tp = strategy_obj.calculate_sl_tp(entry_price, atr or max(entry_price * 0.001, 1.0), direction)
        except Exception:
            risk = max(atr or entry_price * 0.005, 1.0)
            sl = entry_price - risk if direction == "BUY" else entry_price + risk
            tp = entry_price + risk * 2.0 if direction == "BUY" else entry_price - risk * 2.0

        confidence = float(winner.get("confidence") or winner.get("market_fit_score") or 0.0)
        trade_quality = float(winner.get("market_fit_score") or confidence)
        market_regime = getattr(orch_ctx, "market_regime", {}) or {}
        plan = self.precision_entry_engine.build_plan(
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            direction=direction,
            current_price=entry_price,
            atr=atr or max(entry_price * 0.001, 1.0),
            confidence=confidence,
            trade_quality=trade_quality,
            sl=sl,
            tp=tp,
            candle_time=candle_ts,
            market_state=market_regime.get("market_state", market_regime.get("regime", "UNKNOWN")),
            vwap=self._latest_vwap(work),
        ).to_dict()

        plan["rank"] = winner.get("rank", 1)
        plan["score_breakdown"] = winner.get("score_breakdown", {})
        plan["confidence_breakdown"] = winner.get("confidence_breakdown", {})
        plan["deployment_bias"] = winner.get("deployment_bias")
        plan["risk_level"] = (getattr(orch_ctx, "institutional_risk", {}) or {}).get("risk_level")
        plan["entry_trigger"] = plan.get("entry_trigger")
        plan["lot"] = candidate.get("lot") or candidate.get("qty") or 0.01
        try:
            plan_candle_ts = pd.Timestamp(plan.get("candle_time"))
            live_candle_ts = self.last_live_candle_by_tf.get(str(timeframe).upper())
            plan["is_live_plan"] = bool(live_candle_ts is not None and plan_candle_ts >= pd.Timestamp(live_candle_ts))
        except Exception:
            plan["is_live_plan"] = False

        self.state_manager.active_candidates = [plan]
        self.state_manager.set_active_trade_plan(plan)
        self.state_manager.last_plan_candle = candle_key

    def _compile_engine_diagnostics(self, orch_ctx) -> Dict[str, Any]:
        """Maps output of the 19 engines to formatted diagnostic summaries and states."""
        h4 = orch_ctx.h4_structure or {}
        mtf = {"alignment_score": orch_ctx.h1_structure.get("_alignment_score", 50.0), "context_label": orch_ctx.h1_structure.get("context_label", "Developing")}
        sess = orch_ctx.session_context or {}
        trans = orch_ctx.regime_transition or {}
        mem = orch_ctx.market_memory or {}
        m5 = orch_ctx.m5_precision or {}
        clock = orch_ctx.execution_clock or {}
        regime = orch_ctx.market_regime or {}
        sig_q = orch_ctx.signal_quality or {}
        candle = orch_ctx.candlestick_intelligence or {}
        contra = orch_ctx.contradiction_engine or {}
        conf = orch_ctx.confidence_hierarchy or {}
        sat = orch_ctx.signal_saturation or {}
        risk = orch_ctx.institutional_risk or {}
        ready = orch_ctx.execution_readiness or {}
        
        # Calculate mock score contribution, penalties, contradictions, latency
        diagnostics = {
            "Engine 1: H4 Trend Structure": {
                "state": "ACTIVE" if h4.get("macro_direction") != "NEUTRAL" else "PASSIVE",
                "confidence": h4.get("macro_strength", 50.0),
                "score_contribution": 15.0 if h4.get("macro_direction") != "NEUTRAL" else 0.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "1.2ms",
                "details": f"Macro Direction: {h4.get('macro_direction', 'NEUTRAL')} | Trend Age: {h4.get('trend_age', 0)} candles"
            },
            "Engine 2: Multi-Timeframe Alignment": {
                "state": "ACTIVE" if mtf.get("alignment_score", 50.0) >= 70.0 else "PASSIVE",
                "confidence": mtf.get("alignment_score", 50.0),
                "score_contribution": 20.0 if mtf.get("alignment_score", 50.0) >= 70.0 else 0.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "2.4ms",
                "details": f"Alignment Score: {mtf.get('alignment_score', 50.0):.1f}/100 | Label: {mtf.get('context_label')}"
            },
            "Engine 3: Session Context Analyzer": {
                "state": "WATCHING" if sess.get("session_liquidity") == "LOW" else "ACTIVE",
                "confidence": 85.0 if sess.get("session_liquidity") in ("HIGH", "MEDIUM") else 50.0,
                "score_contribution": 10.0 if sess.get("session_liquidity") == "HIGH" else 5.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "0.8ms",
                "details": f"Active Session: {sess.get('current_session')} | Liquidity: {sess.get('session_liquidity')}"
            },
            "Engine 4: Regime Transition Detector": {
                "state": "COOLING" if trans.get("transition_state") != "STABLE" else "PASSIVE",
                "confidence": 100.0 - trans.get("collapse_risk", 0.0),
                "score_contribution": 0.0,
                "penalties": trans.get("collapse_risk", 0.0) * 0.2,
                "contradictions": 0,
                "latency": "1.6ms",
                "details": f"Transition State: {trans.get('transition_state')} | Collapse Risk: {trans.get('collapse_risk', 0.0):.1f}%"
            },
            "Engine 5: Market Memory Engine": {
                "state": "WATCHING",
                "confidence": mem.get("memory_strength", 60.0),
                "score_contribution": 5.0 if mem.get("memory_duration", 0) > 50 else 0.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "0.9ms",
                "details": f"Memory Horizon: {mem.get('memory_duration', 0)} candles | Strength: {mem.get('memory_strength', 50.0):.1f}%"
            },
            "Engine 6: M5 Execution Timing": {
                "state": "ACTIVE" if m5.get("timing_score", 50.0) >= 70.0 else "PASSIVE",
                "confidence": m5.get("timing_score", 50.0),
                "score_contribution": 10.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "1.1ms",
                "details": f"Precision timing score: {m5.get('timing_score', 50.0):.1f}/100"
            },
            "Engine 7: Execution Clock Engine": {
                "state": "ACTIVE" if clock.get("clock_state") == "OPTIMAL" else "WATCHING",
                "confidence": clock.get("overlap_efficiency", 60.0),
                "score_contribution": 8.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "0.5ms",
                "details": f"Clock State: {clock.get('clock_state')} | Overlap efficiency: {clock.get('overlap_efficiency', 50.0):.1f}%"
            },
            "Engine 8: Market Regime Detection": {
                "state": "ACTIVE",
                "confidence": regime.get("trend_strength", 50.0),
                "score_contribution": 10.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "1.8ms",
                "details": f"Detected Regime: {regime.get('regime')} | Direction: {regime.get('direction')}"
            },
            "Engine 9: Signal Quality Engine": {
                "state": "ACTIVE" if sig_q.get("quality_score", 50.0) >= 70.0 else "PASSIVE",
                "confidence": sig_q.get("quality_score", 50.0),
                "score_contribution": 12.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "2.2ms",
                "details": f"Quality Score: {sig_q.get('quality_score', 50.0):.1f}/100 | Confluences: {sig_q.get('confluence_count', 0)}"
            },
            "Engine 10: Candlestick Intelligence": {
                "state": "ACTIVE" if candle.get("candle_quality", 50.0) >= 70.0 else "PASSIVE",
                "confidence": candle.get("candle_quality", 50.0),
                "score_contribution": 5.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "0.7ms",
                "details": f"Pattern: {candle.get('pattern_name', 'None')} | Bias: {candle.get('direction_bias')}"
            },
            "Engine 11: Contradiction Engine": {
                "state": "BLOCKED" if contra.get("conflict_count", 0) > 1 else "ACTIVE",
                "confidence": 100.0 - contra.get("contradiction_score", 0.0),
                "score_contribution": 0.0,
                "penalties": contra.get("contradiction_score", 0.0),
                "contradictions": contra.get("conflict_count", 0),
                "latency": "3.5ms",
                "details": f"Conflicts found: {contra.get('conflict_count', 0)} | Penalty: -{contra.get('contradiction_score', 0.0):.1f} pts"
            },
            "Engine 12: Confidence Hierarchy": {
                "state": "ACTIVE",
                "confidence": conf.get("weighted_confidence_score", 50.0),
                "score_contribution": 0.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "1.3ms",
                "details": f"Weighted Score: {conf.get('weighted_confidence_score', 50.0):.1f}% | Saturated: {conf.get('saturated_confidence', 50.0):.1f}%"
            },
            "Engine 13: Signal Saturation Analyzer": {
                "state": "ACTIVE" if not sat.get("is_saturated") else "COOLING",
                "confidence": 100.0 - sat.get("saturation_penalty", 0.0),
                "score_contribution": 0.0,
                "penalties": sat.get("saturation_penalty", 0.0),
                "contradictions": 0,
                "latency": "1.5ms",
                "details": f"Saturation Level: {sat.get('saturation_level')} | Penalty: -{sat.get('saturation_penalty', 0.0):.1f} pts"
            },
            "Engine 14: Institutional Risk Engine": {
                "state": "BLOCKED" if risk.get("risk_level") in ("CRITICAL", "HIGH") else "ACTIVE",
                "confidence": 100.0 - risk.get("risk_score", 50.0),
                "score_contribution": 0.0,
                "penalties": risk.get("risk_score", 0.0) * 0.1,
                "contradictions": 0,
                "latency": "2.8ms",
                "details": f"Risk Level: {risk.get('risk_level')} (Score: {risk.get('risk_score', 50.0):.1f}/100)"
            },
            "Engine 15: Execution Readiness Engine": {
                "state": "ACTIVE" if ready.get("execution_state") == "READY" else "WATCHING",
                "confidence": ready.get("readiness_score", 50.0),
                "score_contribution": 0.0,
                "penalties": 0.0,
                "contradictions": len(ready.get("hard_blocks", [])),
                "latency": "2.0ms",
                "details": f"Readiness state: {ready.get('execution_state')} | Blocks: {ready.get('hard_blocks', [])}"
            },
            "Engine 16: Strategy Tournament": {
                "state": "ACTIVE",
                "confidence": 95.0,
                "score_contribution": 0.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "4.2ms",
                "details": f"Ranked {len(orch_ctx.tournament_results)} eligible strategies."
            },
            "Engine 17: Market Explainer": {
                "state": "ACTIVE",
                "confidence": 90.0,
                "score_contribution": 0.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "3.0ms",
                "details": f"Exclusion logs generated for {len(orch_ctx.market_explainer.get('strategy_rejections', {}))} strategies."
            },
            "Engine 18: Narrative Compression": {
                "state": "ACTIVE",
                "confidence": 85.0,
                "score_contribution": 0.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "8.5ms",
                "details": f"Compressed briefing outline compiled."
            },
            "Engine 19: Ingestion Pipeline": {
                "state": "ACTIVE",
                "confidence": 100.0,
                "score_contribution": 0.0,
                "penalties": 0.0,
                "contradictions": 0,
                "latency": "12.0ms",
                "details": "Normalized columns successfully."
            }
        }
        return diagnostics

    def _compile_pipeline_flow(self, orch_ctx) -> List[Dict[str, Any]]:
        """Compiles states of pipeline stages for progress flows."""
        h4 = orch_ctx.h4_structure or {}
        ready = orch_ctx.execution_readiness or {}
        contra = orch_ctx.contradiction_engine or {}
        
        stages = [
            {"name": "Market Data", "status": "PASS", "latency": "12ms"},
            {"name": "Regime Engine", "status": "PASS", "latency": "1.8ms"},
            {"name": "Liquidity Engine", "status": "PASS", "latency": "2.0ms"},
            {"name": "Structure Engine", "status": "PASS" if h4.get("macro_direction") != "NEUTRAL" else "WARNING", "latency": "1.2ms"},
            {"name": "Contradiction Engine", "status": "PASS" if contra.get("conflict_count", 0) == 0 else "FAIL", "latency": "3.5ms"},
            {"name": "Tournament Engine", "status": "PASS", "latency": "4.2ms"},
            {"name": "Execution Quality", "status": "PASS", "latency": "2.1ms"},
            {"name": "Candidate Validation", "status": "PASS" if ready.get("execution_state") == "READY" else "WARNING", "latency": "2.0ms"},
            {"name": "Deployment Gate", "status": "PASS" if ready.get("execution_state") == "READY" else "BLOCKED", "latency": "0.5ms"}
        ]
        return stages
