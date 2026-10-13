"""
deployment/replay_controller.py
Replay Controller managing pointer, dataset indexing, and playback speeds.
"""
import pandas as pd
from typing import Tuple


class ReplayController:
    """
    Manages historical candle playback simulation.
    Keep pointers isolated from live execution loops.
    """

    def __init__(self):
        self.candle_pointer = 0
        self.replay_dataset = pd.DataFrame()
        self.playback_speed = 1.0
        self.play_status = "PAUSED"  # PLAYING | PAUSED
        self.events = []

    def load_dataset(self, df: pd.DataFrame) -> None:
        """Loads dataset and resets pointers."""
        if df is None or df.empty:
            self.replay_dataset = pd.DataFrame()
            self.candle_pointer = 0
            return
        # Standardize columns to lowercase for internal processing
        self.replay_dataset = df.copy()
        self.candle_pointer = min(200, len(df) - 1)  # Start with enough historical candles to run indicators

    def step_candle(self) -> bool:
        """
        Steps forward by 1 candle. Returns True if advanced, False if reached end.
        """
        if self.replay_dataset.empty:
            return False
            
        if self.candle_pointer < len(self.replay_dataset) - 1:
            self.candle_pointer += 1
            self.events.append(f"Replay advanced to index {self.candle_pointer}")
            if len(self.events) > 50:
                self.events.pop(0)
            return True
        return False

    def get_current_slice(self) -> pd.DataFrame:
        """
        Returns the historical slice up to the current pointer.
        """
        if self.replay_dataset.empty:
            return pd.DataFrame()
        return self.replay_dataset.iloc[:self.candle_pointer + 1]

    def set_speed(self, speed: float) -> None:
        """Sets playback speed."""
        self.playback_speed = max(0.1, min(10.0, speed))

    def set_play_status(self, status: str) -> None:
        """Sets play status."""
        if status in ("PLAYING", "PAUSED"):
            self.play_status = status
