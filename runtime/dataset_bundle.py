"""
runtime/dataset_bundle.py
Dataset Bundle exporter module for V2 pipeline.
"""
import os
import json
import hashlib
import datetime
import pandas as pd
from engine.multi_timeframe_pipeline import MultiTimeframePipeline

class DatasetBundle:
    """
    Saves and manages multi-timeframe bundles locally on disk.
    """

    def __init__(self, base_dir: str = "datasets/bundles"):
        self.base_dir = base_dir

    def save_bundle(
        self,
        symbol: str,
        broker: str,
        base_df: pd.DataFrame,
        integrity_score: float
    ) -> dict:
        """
        Takes the base timeframe DataFrame (typically M5 or M15), resamples it,
        saves all CSV files to datasets/bundles/<symbol>/, and writes metadata.json.

        Returns:
            The metadata dictionary.
        """
        symbol_clean = symbol.strip().upper()
        target_dir = os.path.join(self.base_dir, symbol_clean)
        os.makedirs(target_dir, exist_ok=True)

        # 1. Resample to all timeframes (M5, M15, H1, H4) using MultiTimeframePipeline
        pipeline = MultiTimeframePipeline()
        bundle = pipeline.process(base_df)

        # 2. Save individual CSV files
        timeframes = ["m5", "m15", "h1", "h4"]
        for tf in timeframes:
            tf_df = bundle.get(tf)
            if tf_df is not None and not tf_df.empty:
                file_path = os.path.join(target_dir, f"{tf}.csv")
                tf_df.to_csv(file_path, index=False)

        # 3. Calculate dataset hash based on the base dataframe close price and timestamp
        dataset_hash = self.calculate_hash(base_df)

        # 4. Generate metadata
        metadata = {
            "symbol": symbol_clean,
            "broker": broker,
            "rows": len(base_df),
            "downloaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
            "integrity_score": float(integrity_score),
            "dataset_hash": dataset_hash
        }

        # 5. Write metadata.json
        meta_path = os.path.join(target_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return metadata

    @staticmethod
    def calculate_hash(df: pd.DataFrame) -> str:
        """Computes a unique sha256 hash matching the ContextCache logic."""
        if df is None or df.empty:
            return "empty"
        try:
            ts_str = df["timestamp"].astype(str).values.tobytes()
            close_vals = pd.to_numeric(df["close"], errors="coerce").fillna(0.0).values.tobytes()
            
            h = hashlib.sha256()
            h.update(ts_str)
            h.update(close_vals)
            return h.hexdigest()[:16]
        except Exception:
            return "hash_" + str(len(df))

    def load_bundle(self, symbol: str) -> dict | None:
        """
        Loads a saved dataset bundle from disk if it exists.
        Returns:
            {
                "m5": pd.DataFrame,
                "m15": pd.DataFrame,
                "h1": pd.DataFrame,
                "h4": pd.DataFrame,
                "metadata": dict
            } or None
        """
        symbol_clean = symbol.strip().upper()
        target_dir = os.path.join(self.base_dir, symbol_clean)
        
        meta_path = os.path.join(target_dir, "metadata.json")
        if not os.path.exists(meta_path):
            return None

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            bundle = {"metadata": metadata}
            timeframes = ["m5", "m15", "h1", "h4"]
            for tf in timeframes:
                file_path = os.path.join(target_dir, f"{tf}.csv")
                if os.path.exists(file_path):
                    df = pd.read_csv(file_path)
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    bundle[tf] = df
                else:
                    bundle[tf] = pd.DataFrame()

            return bundle
        except Exception:
            return None
