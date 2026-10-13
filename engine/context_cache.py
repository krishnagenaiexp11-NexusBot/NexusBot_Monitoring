"""
engine/context_cache.py
Context Caching Engine for NexusBot V2.

Caches computed OrchestrationContext instances using a unique hash of the base dataset
to prevent redundant quantitative recalculations.
"""
import hashlib
import pandas as pd
from engine.orchestration_context import OrchestrationContext


class ContextCache:
    """
    Registry for computed orchestration contexts.
    """

    def __init__(self):
        self._cache = {}

    def get_hash(self, df: pd.DataFrame) -> str:
        """Computes a unique sha256 hash based on the timestamp and close columns."""
        if df is None or df.empty:
            return "empty"
        try:
            # Hash timestamp + close values
            ts_str = df["timestamp"].astype(str).values.tobytes()
            close_vals = pd.to_numeric(df["close"], errors="coerce").fillna(0.0).values.tobytes()
            
            h = hashlib.sha256()
            h.update(ts_str)
            h.update(close_vals)
            return h.hexdigest()[:16]
        except Exception:
            return "fallback_hash_" + str(len(df))

    def get(self, df_hash: str) -> OrchestrationContext | None:
        """Retrieves a cached context by its hash key."""
        return self._cache.get(df_hash)

    def set(self, df_hash: str, context: OrchestrationContext) -> None:
        """Stores a context instance in the cache."""
        if df_hash and context:
            self._cache[df_hash] = context

    def clear(self) -> None:
        """Clears all cached context entries."""
        self._cache.clear()
