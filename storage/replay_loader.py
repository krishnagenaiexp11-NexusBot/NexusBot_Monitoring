"""
storage/replay_loader.py
Replay Ingestion and Parsing Engine for NexusBot V3.

Loads regime logs from results/regime_logs/ to replay historical context and decisions.
"""
import os
import json
from datetime import datetime


class ReplayLoader:
    """
    Scans and parses stored decision logs to reconstruct historical
    execution and decision intelligence.
    """

    LOG_DIR = "results/regime_logs"

    @classmethod
    def list_logs(cls) -> list:
        """
        Scans results/regime_logs/ for all valid JSON logs and returns
        metadata dictionaries sorted descending by timestamp.
        """
        if not os.path.exists(cls.LOG_DIR):
            return []

        logs = []
        for filename in os.listdir(cls.LOG_DIR):
            if filename.startswith("log_") and filename.endswith(".json"):
                filepath = os.path.join(cls.LOG_DIR, filename)
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                    
                    # Extract header info
                    logs.append({
                        "filename": filename,
                        "filepath": filepath,
                        "timestamp": data.get("timestamp", ""),
                        "symbol": data.get("symbol", "N/A"),
                        "timeframe": data.get("timeframe", "N/A"),
                        "market_state": data.get("market_state", "N/A"),
                        "winner": data.get("tournament", {}).get("winner", "None"),
                        "fit_score": data.get("tournament", {}).get("market_fit_score", 0.0),
                    })
                except Exception:
                    # Skip corrupt or malformed files
                    continue

        # Sort logs by filename or timestamp desc
        logs.sort(key=lambda x: x["filename"], reverse=True)
        return logs

    @classmethod
    def load_log(cls, filepath: str) -> dict | None:
        """
        Loads and parses a single regime log file by absolute or relative path.
        """
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            return None
