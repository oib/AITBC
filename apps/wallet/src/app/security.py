from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests: int = 30, window_seconds: int = 60) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._records: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            entries = self._records[key]
            while entries and now - entries[0] > self._window_seconds:
                entries.popleft()
            if len(entries) >= self._max_requests:
                return False
            entries.append(now)
            return True


def validate_password_rules(password: str) -> None:
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("password must include at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("password must include at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("password must include at least one digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("password must include at least one symbol")


def wipe_buffer(buffer: bytearray) -> None:
    for index in range(len(buffer)):
        buffer[index] = 0
