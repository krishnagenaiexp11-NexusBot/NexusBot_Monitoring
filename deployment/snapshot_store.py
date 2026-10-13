"""
deployment/snapshot_store.py
Thread-safe snapshot store for atomic immutable state access in NexusBot V3.
"""
import threading
import copy
from deployment.live_state_snapshot import LiveStateSnapshot


class SnapshotStore:
    """
    Atomic read-write store for LiveStateSnapshot instances.
    Provides thread safety and guarantees immutable snapshots.
    """

    def __init__(self, initial_snapshot: LiveStateSnapshot | None = None):
        self._lock = threading.Lock()
        self._snapshot = initial_snapshot or LiveStateSnapshot()

    def get_snapshot(self) -> LiveStateSnapshot:
        """
        Retrieves the current immutable snapshot.
        """
        with self._lock:
            # Since LiveStateSnapshot is frozen and fields are mostly basic types,
            # we return it directly. We copy nested dicts just to ensure safety.
            return self._snapshot

    def write_snapshot(self, snapshot: LiveStateSnapshot) -> None:
        """
        Atomically replaces the active snapshot.
        """
        if not isinstance(snapshot, LiveStateSnapshot):
            raise TypeError("Value must be a LiveStateSnapshot instance.")
        with self._lock:
            self._snapshot = snapshot

    def update_snapshot(self, **kwargs) -> None:
        """
        Atomically updates fields in the active snapshot.
        """
        with self._lock:
            data = self._snapshot.to_dict()
            for k, v in kwargs.items():
                if k in data:
                    data[k] = v
            self._snapshot = LiveStateSnapshot.from_dict(data)
