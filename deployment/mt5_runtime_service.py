"""
deployment/mt5_runtime_service.py
Dedicated MT5 Runtime Service for NexusBot V4.
"""
import time, threading, logging, random
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from deployment.snapshot_store import SnapshotStore
from deployment.live_state_snapshot import LiveStateSnapshot, MT5ConnectionState, LivePositionState, MarketStateSnapshot
from runtime.mt5_connector import MT5Connector
from engine.event_bus import EventBus, MT5_POSITION_SYNCED, MT5_ERROR
try:
    import MetaTrader5 as mt5_lib
except ImportError:
    mt5_lib = None

logger = logging.getLogger("MT5RuntimeService")

class MT5RuntimeService:
    """Sole owner of MT5 connectivity. Writes results to SnapshotStore."""
    def __init__(self, snapshot_store: SnapshotStore, event_bus: EventBus = None):
        self.snapshot_store = snapshot_store
        self.event_bus = event_bus
        self.connector = MT5Connector()
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.lock = threading.Lock()
        self.symbol = "UNKNOWN"
        self._simulated_positions: List[Dict[str, Any]] = []

    def start(self, symbol: str = "UNKNOWN") -> bool:
        if self.thread and self.thread.is_alive():
            return True
        self.symbol = symbol
        conn_res = self.connector.initialize()
        logger.info(f"MT5 init: {conn_res}")
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._polling_loop, name="MT5Poller", daemon=True)
        self.thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self.thread:
            self.thread.join(timeout=2.0)
        self.connector.shutdown()

    def set_symbol(self, symbol: str) -> None:
        with self.lock:
            self.symbol = symbol

    def place_order(self, direction: str, lot: float, sl: float = 0.0, tp: float = 0.0, comment: str = "NexusBot") -> dict:
        with self.lock:
            snap = self.snapshot_store.get_snapshot()
            symbol = snap.symbol or self.symbol
            res = self.connector.place_order(symbol=symbol, direction=direction, lot=lot, sl=sl, tp=tp, comment=comment)
            if self.connector.is_simulated and res.get("ticket", 0) > 0:
                entry_price = snap.market_state.price or 2000.0
                pos = {"ticket": res["ticket"], "symbol": symbol, "strategy": "Manual","direction": direction, "entry_time": datetime.now(timezone.utc).isoformat(),"entry_price": entry_price, "current_price": entry_price,"sl": sl, "tp": tp, "lot": lot, "qty": lot,"live_pnl": 0.0, "profit": 0.0, "confidence": 75.0,"regime_at_entry": snap.market_state.regime,"mt5_status": "SIMULATED", "lifecycle_stage": "ACTIVE"}
                self._simulated_positions.append(pos)
            return res

    def close_position(self, ticket: int, direction: str, lot: float, symbol: str) -> dict:
        with self.lock:
            if self.connector.is_simulated or mt5_lib is None:
                self._simulated_positions = [p for p in self._simulated_positions if p["ticket"] != ticket]
                return {"ticket": ticket, "status": "CLOSED", "retcode": 0}
            order_type = mt5_lib.ORDER_TYPE_SELL if direction.upper() == "BUY" else mt5_lib.ORDER_TYPE_BUY
            tick = mt5_lib.symbol_info_tick(symbol)
            if not tick:
                return {"ticket": ticket, "status": "FAILED", "error": f"No price for {symbol}"}
            price = tick.bid if direction.upper() == "BUY" else tick.ask
            request = {"action": mt5_lib.TRADE_ACTION_DEAL, "symbol": symbol,"volume": float(lot), "type": order_type,"position": int(ticket), "price": price,"deviation": 20, "comment": "Close Position","type_time": mt5_lib.ORDER_TIME_GTC,"type_filling": mt5_lib.ORDER_FILLING_IOC}
            result = mt5_lib.order_send(request)
            if result and result.retcode == mt5_lib.TRADE_RETCODE_DONE:
                return {"ticket": ticket, "status": "CLOSED", "retcode": result.retcode}
            return {"ticket": ticket, "status": "FAILED", "error": f"retcode={result.retcode if result else None}"}

    def _polling_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll_cycle()
            except Exception as e:
                logger.error(f"MT5 poll: {e}", exc_info=True)
            time.sleep(1.0)

    def _poll_cycle(self) -> None:
        snap = self.snapshot_store.get_snapshot()
        symbol = snap.symbol or self.symbol
        is_sim = self.connector.is_simulated
        price, spread_pts = self._get_price(symbol, is_sim, snap)
        balance, equity, currency, leverage = self._get_account(is_sim)
        active_positions, pending_orders = self._sync_positions(symbol, is_sim, price, snap)
        ts = datetime.now(timezone.utc).isoformat()
        mt5_conn = MT5ConnectionState(connected=not is_sim, account_balance=balance, account_equity=equity,account_currency=currency, account_leverage=leverage,last_sync_time=ts, is_simulated=is_sim)
        data = snap.to_dict()
        data["market_state"] = MarketStateSnapshot(regime=snap.market_state.regime, macro_direction=snap.market_state.macro_direction,phase=snap.market_state.phase, stress_index=snap.market_state.stress_index,price=price, spread=spread_pts, volatility=snap.market_state.volatility,collapse_prob=snap.market_state.collapse_prob,market_personality=snap.market_state.market_personality)
        data["mt5_connection"] = mt5_conn
        data["active_positions"] = [LivePositionState(**p) if isinstance(p, dict) else p for p in active_positions]
        data["pending_orders"] = pending_orders
        data["live_metrics"] = {"balance": balance, "equity": equity, "leverage": leverage, "currency": currency, "daily_pnl": equity - 10000.0}
        data["timestamp"] = ts
        self.snapshot_store.write_snapshot(LiveStateSnapshot.from_dict(data))
        if not is_sim and self.event_bus:
            self.event_bus.publish(MT5_POSITION_SYNCED, {"positions": len(active_positions), "orders": len(pending_orders), "symbol": symbol})

    def _get_price(self, symbol: str, is_sim: bool, snap: LiveStateSnapshot):
        if not is_sim and mt5_lib is not None:
            tick = mt5_lib.symbol_info_tick(symbol)
            if tick:
                bid = float(tick.bid); ask = float(tick.ask)
                price = (ask + bid) / 2.0
                spread_pts = ask - bid
                info = mt5_lib.symbol_info(symbol)
                if info and info.point:
                    spread_pts /= info.point
                return price, spread_pts
        last_price = snap.market_state.price or 2000.0
        price = last_price + random.uniform(-0.15, 0.15)
        spread_pts = 12.0 + random.uniform(-0.5, 0.5)
        return price, spread_pts

    def _get_account(self, is_sim: bool):
        if not is_sim:
            try:
                acc = mt5_lib.account_info()
                if acc:
                    return float(acc.balance), float(acc.equity), acc.currency, int(acc.leverage)
            except Exception:
                pass
        return 10000.0, 10000.0, "USD", 100

    def _sync_positions(self, symbol: str, is_sim: bool, price: float, snap: LiveStateSnapshot):
        if not is_sim and mt5_lib is not None:
            positions = mt5_lib.positions_get()
            active = []
            if positions:
                for p in positions:
                    direction = "BUY" if p.type == mt5_lib.POSITION_TYPE_BUY else "SELL"
                    active.append({"ticket": int(p.ticket), "symbol": p.symbol,"strategy": p.comment or "External", "direction": direction,"entry_time": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat() if p.time else "","entry_price": float(p.price_open), "current_price": price,"sl": float(p.sl), "tp": float(p.tp),"lot": float(p.volume), "qty": float(p.volume),"live_pnl": float(p.profit), "profit": float(p.profit),"confidence": 75.0, "regime_at_entry": snap.market_state.regime,"mt5_status": "LIVE", "lifecycle_stage": "ACTIVE"})
            orders = mt5_lib.orders_get()
            pending = []
            if orders:
                for o in orders:
                    pending.append({"ticket": int(o.ticket), "symbol": o.symbol,"type": str(o.type), "price": float(o.price_open),"volume": float(o.volume), "sl": float(o.sl), "tp": float(o.tp)})
            return active, pending
        else:
            for pos in self._simulated_positions:
                direction_factor = 1.0 if pos["direction"] == "BUY" else -1.0
                mult = 100.0 if "XAU" in pos.get("symbol", "") else 1.0
                pnl = (price - pos["entry_price"]) * pos["lot"] * direction_factor * mult
                pos["live_pnl"] = pnl; pos["profit"] = pnl; pos["current_price"] = price
                hit_sl = (pos["direction"] == "BUY" and pos.get("sl", 0) > 0 and price <= pos["sl"])
                hit_tp = (pos["direction"] == "BUY" and pos.get("tp", 0) > 0 and price >= pos["tp"])
                if hit_sl or hit_tp:
                    pos["lifecycle_stage"] = "CLOSING"
            live = [p for p in self._simulated_positions if p["lifecycle_stage"] != "CLOSING"]
            self._simulated_positions = live
            return list(live), []
