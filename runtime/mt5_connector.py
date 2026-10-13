"""
runtime/mt5_connector.py
MT5 Connector Module for historical data pull and live order routing.
"""
import logging
from runtime.symbol_mapper import SymbolMapper

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

logger = logging.getLogger("MT5Connector")


class MT5Connector:
    """
    Handles terminal initialization, broker queries, and symbol validation.
    """

    def __init__(self):
        self.is_simulated = False
        self.last_order_request = None
        self.last_order_result = None

    def initialize(self, path: str = None) -> dict:
        """
        Initializes the MT5 connection. If the MetaTrader5 library or terminal is
        not available, gracefully falls back to Simulated/Research mode.
        """
        if mt5 is None:
            logger.warning("MetaTrader5 library not found. Falling back to Simulation Mode.")
            self.is_simulated = True
            return {
                "connected": True,
                "terminal": "MetaTrader 5 (Simulated)",
                "broker": "Nexus Simulation Broker",
                "server": "NexusSim-Demo",
                "is_simulated": True,
                "last_error": "MetaTrader5 Python package is not installed."
            }

        try:
            # Attempt to initialize terminal
            initialized = False
            if path:
                initialized = mt5.initialize(path=path)
            else:
                initialized = mt5.initialize()
                
            # If default init fails, try common Windows default path as fallback
            if not initialized and not path:
                default_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
                import os
                if os.path.exists(default_path):
                    logger.info(f"Default MT5 init failed. Trying default path: {default_path}")
                    initialized = mt5.initialize(path=default_path)

            if initialized:
                self.is_simulated = False
                terminal_info = mt5.terminal_info()
                account_info = mt5.account_info()
                
                broker = account_info.company if account_info else (terminal_info.company if terminal_info else "Broker")
                server = account_info.server if account_info else "Demo Server"
                terminal_name = terminal_info.name if terminal_info else "MetaTrader 5"
                
                logger.info(f"Connected to MT5: Terminal={terminal_name}, Broker={broker}, Server={server}")
                return {
                    "connected": True,
                    "terminal": terminal_name,
                    "broker": broker,
                    "server": server,
                    "is_simulated": False
                }
            else:
                last_err = mt5.last_error()
                logger.warning(f"Could not connect to MT5 terminal (Code: {last_err}). Falling back to Simulation Mode.")
                self.is_simulated = True
                return {
                    "connected": True,
                    "terminal": "MetaTrader 5 (Simulated)",
                    "broker": "Nexus Simulation Broker",
                    "server": "NexusSim-Demo",
                    "is_simulated": True,
                    "last_error": last_err
                }
        except Exception as exc:
            logger.error(f"MT5 Init Exception: {exc}. Falling back to Simulation Mode.")
            self.is_simulated = True
            return {
                "connected": True,
                "terminal": "MetaTrader 5 (Simulated)",
                "broker": "Nexus Simulation Broker",
                "server": "NexusSim-Demo",
                "is_simulated": True,
                "last_error": str(exc)
            }

    def get_account_info(self) -> dict:
        """
        Fetches currency account balance, leverage, and company info.
        """
        if self.is_simulated or mt5 is None:
            return {
                "broker": "Nexus Simulation Broker",
                "server": "NexusSim-Demo",
                "balance": 10000.0,
                "equity": 10000.0,
                "currency": "USD",
                "leverage": 100
            }

        try:
            acc = mt5.account_info()
            if acc is not None:
                return {
                    "broker": acc.company,
                    "server": acc.server,
                    "balance": float(acc.balance),
                    "equity": float(acc.equity),
                    "currency": acc.currency,
                    "leverage": int(acc.leverage)
                }
        except Exception as exc:
            logger.error(f"Failed to fetch account info: {exc}")
            
        return {
            "broker": "Unknown Broker",
            "server": "Unknown Server",
            "balance": 0.0,
            "equity": 0.0,
            "currency": "USD",
            "leverage": 100
        }

    def ensure_symbol(self, symbol: str) -> str:
        """
        Ensures the symbol is visible in MT5 MarketWatch.
        Matches exact casing, strips suffixes, and searches substring matches.
        Returns the exact matching broker symbol string or raises ValueError.
        """
        if self.is_simulated or mt5 is None:
            # Normalized simulation symbol
            return SymbolMapper.normalize(symbol)

        try:
            # 1. Direct match check
            info = mt5.symbol_info(symbol)
            if info is not None:
                if not mt5.symbol_select(symbol, True):
                    raise ValueError(f"MT5 symbol_select failed for '{symbol}': {mt5.last_error()}")
                return symbol

            # 2. Check uppercase exact match
            info_up = mt5.symbol_info(symbol.upper())
            if info_up is not None:
                if not mt5.symbol_select(symbol.upper(), True):
                    raise ValueError(f"MT5 symbol_select failed for '{symbol.upper()}': {mt5.last_error()}")
                return symbol.upper()

            # 3. Scan all symbols for suffix stripping or contains
            all_syms = mt5.symbols_get()
            if all_syms:
                norm_target = SymbolMapper.normalize(symbol)
                
                # Check normalized equivalence first
                for s in all_syms:
                    if SymbolMapper.normalize(s.name) == norm_target:
                        if not mt5.symbol_select(s.name, True):
                            raise ValueError(f"MT5 symbol_select failed for '{s.name}': {mt5.last_error()}")
                        return s.name

                # Substring match
                for s in all_syms:
                    if symbol.upper() in s.name.upper():
                        if not mt5.symbol_select(s.name, True):
                            raise ValueError(f"MT5 symbol_select failed for '{s.name}': {mt5.last_error()}")
                        return s.name
                        
            raise ValueError(f"Symbol '{symbol}' not found in MetaTrader 5.")
            
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise
            raise ValueError(f"Error validating symbol '{symbol}': {exc}")

    def place_order(
        self,
        symbol: str,
        direction: str,
        lot: float = 0.01,
        sl: float = 0.0,
        tp: float = 0.0,
        comment: str = "NexusBot",
        magic: int = 20250001,
    ) -> dict:
        """
        Places a live market order via MT5 order_send.
        Returns a dict with keys: ticket, status, retcode, comment, error.
        Falls back to a simulated ticket if MT5 is unavailable.
        """
        import random

        if self.is_simulated or mt5 is None:
            sim_ticket = random.randint(10000, 99999)
            self.last_order_request = {
                "symbol": symbol,
                "direction": direction,
                "lot": lot,
                "sl": sl,
                "tp": tp,
                "comment": comment,
                "magic": magic,
                "simulated": True,
            }
            self.last_order_result = {
                "ticket": sim_ticket,
                "status": "SIMULATED",
                "retcode": 0,
                "comment": f"Simulated order - {comment}",
                "error": None,
            }
            logger.info(
                f"[SIM] Order placed — {direction} {lot} lots {symbol} | Ticket #{sim_ticket}"
            )
            return {
                "ticket": sim_ticket,
                "status": "SIMULATED",
                "retcode": 0,
                "comment": f"Simulated order — {comment}",
                "error": None,
            }

        try:
            broker_symbol = self.ensure_symbol(symbol)
        except ValueError as exc:
            logger.error(f"Symbol validation failed: {exc}")
            self.last_order_request = {
                "symbol": symbol,
                "direction": direction,
                "lot": lot,
                "sl": sl,
                "tp": tp,
                "comment": comment,
                "magic": magic,
            }
            self.last_order_result = {"ticket": -1, "status": "ERROR", "retcode": -1, "comment": str(exc), "error": str(exc)}
            return self.last_order_result

        direction = str(direction or "").strip().upper()
        if direction not in {"BUY", "SELL"}:
            err = f"Unsupported order direction: {direction or 'EMPTY'}"
            self.last_order_result = {
                "ticket": -1,
                "status": "ERROR",
                "retcode": -1,
                "comment": err,
                "error": err,
            }
            return self.last_order_result

        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

        # Get latest tick for price
        tick = mt5.symbol_info_tick(broker_symbol)
        if tick is None:
            err = f"Could not retrieve tick for {broker_symbol}"
            logger.error(err)
            self.last_order_result = {"ticket": -1, "status": "ERROR", "retcode": -1, "comment": err, "error": err}
            return self.last_order_result

        price = tick.ask if direction == "BUY" else tick.bid
        info = mt5.symbol_info(broker_symbol)
        digits = int(getattr(info, "digits", 5) or 5)
        volume_min = float(getattr(info, "volume_min", 0.01) or 0.01)
        volume_max = float(getattr(info, "volume_max", lot) or lot)
        volume_step = float(getattr(info, "volume_step", volume_min) or volume_min)
        normalized_lot = max(volume_min, min(float(lot), volume_max))
        if volume_step > 0:
            normalized_lot = round(round(normalized_lot / volume_step) * volume_step, 8)
        normalized_lot = max(volume_min, min(normalized_lot, volume_max))
        price = round(float(price), digits)
        sl = round(float(sl), digits) if float(sl) > 0 else 0.0
        tp = round(float(tp), digits) if float(tp) > 0 else 0.0

        # MT5 comment must be plain ASCII, no special chars, max 31 characters
        import re
        safe_comment = re.sub(r"[^a-zA-Z0-9 .\-_]", "", comment)[:31]

        request = {
            "action":    mt5.TRADE_ACTION_DEAL,
            "symbol":    broker_symbol,
            "volume":    normalized_lot,
            "type":      order_type,
            "price":     price,
            "sl":        sl,
            "tp":        tp,
            "deviation": 20,
            "magic":     magic,
            "comment":   safe_comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        self.last_order_request = dict(request)

        result = mt5.order_send(request)

        # --- Filling mode fallback ---
        # Some brokers reject IOC; retry with FOK then RETURN automatically
        if result is not None and result.retcode == 10030:  # TRADE_RETCODE_INVALID_FILL
            for fill_mode in (mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
                request["type_filling"] = fill_mode
                result = mt5.order_send(request)
                if result is not None and result.retcode != 10030:
                    break

        if result is None:
            err = f"order_send returned None — last error: {mt5.last_error()}"
            logger.error(err)
            self.last_order_result = {"ticket": -1, "status": "FAILED", "retcode": -1, "comment": err, "error": err}
            return {"ticket": -1, "status": "FAILED", "retcode": -1, "comment": err, "error": err}

        success_retcodes = {
            int(getattr(mt5, "TRADE_RETCODE_DONE", 10009)),
            int(getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)),
            int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008)),
        }
        if int(result.retcode) in success_retcodes:
            order_ticket = int(getattr(result, "order", 0) or 0)
            deal_ticket = int(getattr(result, "deal", 0) or 0)
            ticket = order_ticket or deal_ticket
            self.last_order_result = {
                "ticket": ticket,
                "order_ticket": order_ticket,
                "deal_ticket": deal_ticket,
                "status": "PLACED",
                "retcode": result.retcode,
                "comment": result.comment,
                "error": None,
                "symbol": broker_symbol,
                "volume": normalized_lot,
                "price": price,
            }
            logger.info(
                f"[LIVE] Order placed — {direction} {lot} lots {broker_symbol} "
                f"@ {price:.5f} | Ticket #{result.order}"
            )
            return dict(self.last_order_result)
        else:
            err_msg = f"MT5 order failed — retcode={result.retcode}, comment={result.comment}"
            logger.error(err_msg)
            self.last_order_result = {
                "ticket": -1,
                "status": "FAILED",
                "retcode": result.retcode,
                "comment": result.comment,
                "error": err_msg,
            }
            return {
                "ticket": -1,
                "status": "FAILED",
                "retcode": result.retcode,
                "comment": result.comment,
                "error": err_msg,
            }

    def shutdown(self) -> None:
        """
        Safely shuts down the MT5 terminal API connection.
        """
        if not self.is_simulated and mt5 is not None:
            try:
                mt5.shutdown()
                logger.info("MT5 connection closed.")
            except Exception as exc:
                logger.error(f"Error during MT5 shutdown: {exc}")
