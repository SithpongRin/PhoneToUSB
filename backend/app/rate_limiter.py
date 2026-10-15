"""
In-memory sliding window rate limiter for PhoneToUSB backend.
Throttles excessive connection attempts and pairing requests.
"""

import time
from collections import defaultdict
from typing import Dict, List

class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, identifier: str) -> bool:
        now = time.time()
        timestamps = self._history[identifier]

        # Purge timestamps outside sliding window
        valid_timestamps = [t for t in timestamps if now - t < self.window_seconds]
        self._history[identifier] = valid_timestamps

        if len(valid_timestamps) >= self.max_requests:
            return False

        self._history[identifier].append(now)
        return True

    def clear(self):
        self._history.clear()
