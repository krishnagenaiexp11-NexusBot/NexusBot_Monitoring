"""
runtime/dataset_registry.py
SQLite-based Dataset Registry for tracking downloaded assets.
"""
import sqlite3
import datetime
import os
from pathlib import Path


class DatasetRegistry:
    """
    Manages metadata storage for downloaded symbols, historical scopes, and integrity rates.
    """

    def __init__(self, db_path: str = "storage/dataset_registry.sqlite"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """Initializes tables for datasets, downloads, and integrity reports."""
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS datasets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        rows INTEGER NOT NULL,
                        integrity_score REAL NOT NULL,
                        dataset_hash TEXT NOT NULL UNIQUE,
                        downloaded_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        start_date TEXT NOT NULL,
                        end_date TEXT NOT NULL,
                        rows_downloaded INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS integrity_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dataset_hash TEXT NOT NULL,
                        duplicates_removed INTEGER NOT NULL,
                        missing_candles INTEGER NOT NULL,
                        integrity_score REAL NOT NULL,
                        timestamp TEXT NOT NULL
                    )
                    """
                )
        finally:
            conn.close()

    def register_dataset(
        self,
        symbol: str,
        timeframe: str,
        rows: int,
        integrity_score: float,
        dataset_hash: str
    ) -> None:
        """Registers or updates a dataset metadata entry."""
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO datasets (symbol, timeframe, rows, integrity_score, dataset_hash, downloaded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(dataset_hash) DO UPDATE SET
                        rows = excluded.rows,
                        integrity_score = excluded.integrity_score,
                        downloaded_at = excluded.downloaded_at
                    """,
                    (
                        symbol.upper(),
                        timeframe,
                        rows,
                        float(integrity_score),
                        dataset_hash,
                        datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
                    )
                )
        finally:
            conn.close()

    def log_download(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        rows_downloaded: int,
        status: str
    ) -> None:
        """Logs a historical data pull operation."""
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO downloads (symbol, timeframe, start_date, end_date, rows_downloaded, status, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol.upper(),
                        timeframe,
                        str(start_date),
                        str(end_date),
                        rows_downloaded,
                        status,
                        datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
                    )
                )
        finally:
            conn.close()

    def log_integrity_report(
        self,
        dataset_hash: str,
        duplicates_removed: int,
        missing_candles: int,
        integrity_score: float
    ) -> None:
        """Logs the integrity details for a dataset."""
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO integrity_reports (dataset_hash, duplicates_removed, missing_candles, integrity_score, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        dataset_hash,
                        duplicates_removed,
                        missing_candles,
                        float(integrity_score),
                        datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
                    )
                )
        finally:
            conn.close()

    def get_latest_datasets(self) -> list[dict]:
        """Returns all registered datasets, sorted by downloaded timestamp descending."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM datasets ORDER BY downloaded_at DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
