"""
runtime/mt5_data_downloader.py
MT5 Data Downloader Module for historical OHLCV data.
"""
import os
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from runtime.mt5_connector import MT5Connector
from runtime.timeframe_mapper import TIMEFRAME_MAP

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

logger = logging.getLogger("MT5DataDownloader")


class MT5DataDownloader:
    """
    Downloads historical rates from MetaTrader 5 or falls back to simulation datasets.
    """

    def __init__(self, connector: MT5Connector = None):
        self.connector = connector or MT5Connector()
        # Initialize connection status
        if not hasattr(self.connector, 'is_simulated'):
            self.connector.initialize()

    def download_historical_data(
        self,
        symbol: str,
        timeframe_str: str,
        start_date: datetime,
        end_date: datetime
    ) -> tuple[pd.DataFrame, dict]:
        """
        Downloads data from MT5 broker or loads mock data, normalizes it, and returns
        the DataFrame along with an integrity report.

        Args:
            symbol: Symbol string (e.g. "XAUUSD")
            timeframe_str: Timeframe string (e.g. "M5")
            start_date: Start datetime object (timezone naive or aware)
            end_date: End datetime object (timezone naive or aware)

        Returns:
            (DataFrame, integrity_report_dict)
        """
        # Ensure correct datetimes
        dt_start = pd.to_datetime(start_date)
        dt_end = pd.to_datetime(end_date)

        # 1. Fallback to simulation mode if requested or MT5 connector is in simulated mode
        if self.connector.is_simulated or mt5 is None:
            logger.info(f"[Simulation Mode] Ingesting mock data for {symbol} ({timeframe_str}).")
            return self._load_simulated_data(symbol, timeframe_str, dt_start, dt_end)

        # 2. Real MT5 Data Download
        try:
            # Match broker-specific symbol name
            broker_symbol = self.connector.ensure_symbol(symbol)
            tf_const = TIMEFRAME_MAP.get(timeframe_str)
            if tf_const is None:
                raise ValueError(f"Unsupported timeframe: {timeframe_str}")

            # Ensure datetime is naive UTC for copy_rates_range
            utc_start = dt_start.tz_localize(None) if dt_start.tzinfo else dt_start
            utc_end = dt_end.tz_localize(None) if dt_end.tzinfo else dt_end

            rates = mt5.copy_rates_range(broker_symbol, tf_const, utc_start, utc_end)
            
            if rates is None or len(rates) == 0:
                last_err = mt5.last_error()
                logger.warning(f"No rates returned from MT5 for {broker_symbol}. last_error={last_err}")
                return self._empty_result(
                    timeframe_str,
                    f"No rates returned from MT5 for {broker_symbol}. last_error={last_err}"
                )

            df_raw = pd.DataFrame(rates)
            
            # Normalize fields
            # columns in rates: time, open, high, low, close, tick_volume, spread, real_volume
            df = pd.DataFrame()
            df["timestamp"] = pd.to_datetime(df_raw["time"], unit="s", utc=True)
            df["open"] = df_raw["open"].astype(float)
            df["high"] = df_raw["high"].astype(float)
            df["low"] = df_raw["low"].astype(float)
            df["close"] = df_raw["close"].astype(float)
            df["volume"] = df_raw["tick_volume"].astype(float)
            df["spread"] = df_raw["spread"].astype(float)
            df["symbol"] = symbol
            df["timeframe"] = timeframe_str

            return self._clean_and_generate_report(df, timeframe_str)

        except Exception as exc:
            last_err = mt5.last_error() if mt5 is not None else None
            logger.error(f"MT5 download failed: {exc}. last_error={last_err}")
            return self._empty_result(timeframe_str, f"MT5 download failed: {exc}; last_error={last_err}")

    def _empty_result(self, timeframe_str: str, error: str = "") -> tuple[pd.DataFrame, dict]:
        df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "spread", "symbol", "timeframe"])
        report = {
            "rows": 0,
            "duplicates_removed": 0,
            "missing_candles": 0,
            "integrity_score": 0.0,
            "timeframe": timeframe_str,
            "error": error,
        }
        return df, report

    def _load_simulated_data(
        self,
        symbol: str,
        timeframe_str: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> tuple[pd.DataFrame, dict]:
        """
        Loads CSV dataset files from local directory to serve as simulation data.
        """
        # Clean symbol to match file name
        normalized_sym = symbol.strip().upper()
        
        # Determine fallback file
        csv_file = "XAUUSD_M5_1y.csv" if "USD" in normalized_sym or "XAU" in normalized_sym else "EURUSD_MT5_M5_3y.csv"
        # Check files in datasets
        datasets_dir = os.path.join(os.getcwd(), "datasets")
        file_path = os.path.join(datasets_dir, csv_file)

        if not os.path.exists(file_path):
            # Check backup files
            backup_files = [f for f in os.listdir(datasets_dir) if f.endswith(".csv")]
            if backup_files:
                file_path = os.path.join(datasets_dir, backup_files[0])
            else:
                # Generate synthetic dataframe if datasets is empty
                return self._generate_synthetic_df(symbol, timeframe_str, start_date, end_date)

        try:
            df_csv = pd.read_csv(file_path)
            
            # Map canonical names if needed
            mappings = {
                "Date": "date",
                "Time": "time",
                "Volume": "volume",
                "TickVol": "volume",
                "Spread": "spread",
            }
            df_csv = df_csv.rename(columns={k: v for k, v in mappings.items() if k in df_csv.columns})
            
            # Handle combined or separate Date/Time
            if "date" in df_csv.columns and "time" in df_csv.columns:
                df_csv["timestamp"] = pd.to_datetime(df_csv["date"] + " " + df_csv["time"])
            elif "timestamp" in df_csv.columns:
                df_csv["timestamp"] = pd.to_datetime(df_csv["timestamp"])
            else:
                # Use index or index-based timestamps
                dates = pd.date_range("2025-01-01", periods=len(df_csv), freq="5min")
                df_csv["timestamp"] = dates

            # Sort and make UTC aware
            df_csv = df_csv.sort_values("timestamp")
            if df_csv["timestamp"].dt.tz is None:
                df_csv["timestamp"] = df_csv["timestamp"].dt.tz_localize("UTC")
            else:
                df_csv["timestamp"] = df_csv["timestamp"].dt.tz_convert("UTC")

            # Filter by date range
            mask = (df_csv["timestamp"] >= start_date) & (df_csv["timestamp"] <= end_date)
            df_filtered = df_csv.loc[mask].copy()

            if df_filtered.empty:
                # If date range returns nothing, return last 2000 rows
                df_filtered = df_csv.tail(2000).copy()

            # Ensure all canonical columns are present
            required_cols = ["open", "high", "low", "close", "volume"]
            for col in required_cols:
                if col not in df_filtered.columns:
                    df_filtered[col] = 1.0  # default fallback

            df = pd.DataFrame()
            df["timestamp"] = df_filtered["timestamp"]
            df["open"] = df_filtered["open"].astype(float)
            df["high"] = df_filtered["high"].astype(float)
            df["low"] = df_filtered["low"].astype(float)
            df["close"] = df_filtered["close"].astype(float)
            df["volume"] = df_filtered["volume"].astype(float)
            df["spread"] = df_filtered["spread"].astype(float) if "spread" in df_filtered.columns else 2.0
            df["symbol"] = symbol
            df["timeframe"] = timeframe_str

            return self._clean_and_generate_report(df, timeframe_str)

        except Exception as exc:
            logger.error(f"Failed to load fallback CSV: {exc}")
            return self._generate_synthetic_df(symbol, timeframe_str, start_date, end_date)

    def _generate_synthetic_df(
        self,
        symbol: str,
        timeframe_str: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> tuple[pd.DataFrame, dict]:
        """Generates mock synthetic data for safety fallback."""
        np.random.seed(42)
        # Determine freq
        freq_map = {"M1": "1min", "M5": "5min", "M15": "15min", "H1": "1h", "H4": "4h"}
        freq = freq_map.get(timeframe_str, "5min")

        dates = pd.date_range(start=start_date, end=end_date, freq=freq, tz="UTC")
        if len(dates) < 100:
            # Ensure at least some data
            dates = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=1000, freq=freq)

        rows = len(dates)
        price = 100.0 + np.cumsum(np.random.randn(rows) * 0.3)
        spread = np.abs(np.random.randn(rows)) * 0.2 + 0.1
        
        df = pd.DataFrame({
            "timestamp": dates,
            "open": price,
            "high": price + spread,
            "low": price - spread,
            "close": price + np.random.randn(rows) * 0.05,
            "volume": np.random.randint(100, 2000, rows).astype(float),
            "spread": spread * 10.0,  # in points
            "symbol": symbol,
            "timeframe": timeframe_str
        })
        return self._clean_and_generate_report(df, timeframe_str)

    def _clean_and_generate_report(self, df: pd.DataFrame, timeframe_str: str) -> tuple[pd.DataFrame, dict]:
        """
        Cleans data (removes duplicates) and generates an integrity report.
        """
        initial_rows = len(df)
        
        # Remove duplicates
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        duplicates_removed = initial_rows - len(df)

        # Detect missing candles based on median timeframe delta
        missing_candles = 0
        if len(df) > 1:
            deltas = df["timestamp"].diff().dropna()
            expected_delta = deltas.median()
            
            # Loop and find gaps (excluding weekend gaps of >= 45 hours)
            gaps = deltas[deltas > expected_delta * 1.5]
            for gap in gaps:
                if gap < pd.Timedelta(hours=45):
                    missing_candles += int(gap // expected_delta) - 1

        # Calculate integrity score
        total_expected = len(df) + missing_candles
        integrity_score = 100.0 * (len(df) / total_expected) if total_expected > 0 else 100.0

        report = {
            "rows": len(df),
            "duplicates_removed": duplicates_removed,
            "missing_candles": missing_candles,
            "integrity_score": round(integrity_score, 2)
        }

        return df, report
