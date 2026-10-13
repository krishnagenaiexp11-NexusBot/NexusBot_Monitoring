"""
runtime/mt5_connector_stub.py
MT5 Connector Stub — placeholder-compatible architecture only.

No real MT5 execution. Provides stub functions that return mock status.
Future: replace connect_stub() with actual MetaTrader5 library calls.
"""
import datetime


class MT5ConnectionStatus:
    CONNECTED    = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    STUB         = "STUB"


def connect_stub(server: str = "demo.broker.com", login: int = 0, password: str = "") -> dict:
    """
    Stub connection function.
    Returns a mock connection status dict.
    Replace this with real MetaTrader5.initialize() calls in production.
    """
    return {
        "status":       MT5ConnectionStatus.STUB,
        "server":       server,
        "login":        login,
        "connected_at": datetime.datetime.utcnow().isoformat() + "Z",
        "message":      "MT5 stub connection — no real broker connection. For research only.",
        "is_stub":      True,
    }


def load_from_csv(path: str) -> dict:
    """
    Loads OHLCV data from a CSV file for paper-trading simulations.
    Returns a dict with status and DataFrame.
    """
    try:
        import pandas as pd
        from utils.validation import validate_ohlcv
        df = pd.read_csv(path)
        df = validate_ohlcv(df)
        return {
            "status":  "OK",
            "df":      df,
            "rows":    len(df),
            "source":  path,
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "df":     None,
            "error":  str(exc),
            "source": path,
        }


def get_account_info_stub() -> dict:
    """Mock account info for UI display."""
    return {
        "balance":   10_000.0,
        "equity":    10_000.0,
        "margin":    0.0,
        "leverage":  "100:1",
        "currency":  "USD",
        "is_stub":   True,
    }


def get_open_positions_stub() -> list:
    """Returns empty list — no live positions in stub mode."""
    return []
