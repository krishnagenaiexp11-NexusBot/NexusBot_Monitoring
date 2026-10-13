from collections import deque
from datetime import datetime, timezone


class EventBus:
    def __init__(self, max_events: int = 500):
        self.events = deque(maxlen=max_events)

    def emit(self, message: str, level: str = "INFO") -> dict:
        event = {
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "level": level,
            "message": message,
        }
        self.events.append(event)
        return event

    def latest(self) -> list[dict]:
        return list(self.events)
