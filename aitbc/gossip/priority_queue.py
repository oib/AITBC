from __future__ import annotations

import heapq
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class PrioritizedMessage:
    """A gossip message with a priority level.

    Lower priority value = higher priority (sent first).
    """

    priority: int  # 1=highest (blocks), 5=lowest (discovery)
    sequence: int  # monotonic counter for FIFO within same priority
    topic: str = field(compare=False)
    message: Any = field(compare=False)


class PriorityMessageQueue:
    """Priority queue for gossip messages.

    Messages are ordered by priority (blocks first, then transactions,
    then status, then discovery). Within the same priority, messages
    are FIFO (by sequence number).

    Thread-safe for concurrent producers and a single consumer.
    """

    # Priority levels
    PRIORITY_BLOCK = 1
    PRIORITY_BLOCK_HEADER = 2
    PRIORITY_TRANSACTION = 3
    PRIORITY_STATUS = 4
    PRIORITY_DISCOVERY = 5

    def __init__(self, max_size: int = 10000) -> None:
        self._heap: list[PrioritizedMessage] = []
        self._max_size = max_size
        self._sequence = 0
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)

    def put(self, topic: str, message: Any, priority: int = PRIORITY_TRANSACTION) -> bool:
        """Add a message to the queue with given priority.

        Returns True if the message was added, False if the queue is full.
        """
        with self._lock:
            if len(self._heap) >= self._max_size:
                return False
            self._sequence += 1
            msg = PrioritizedMessage(
                priority=priority,
                sequence=self._sequence,
                topic=topic,
                message=message,
            )
            heapq.heappush(self._heap, msg)
            self._not_empty.notify()
            return True

    def get(self, timeout: float | None = None) -> PrioritizedMessage | None:
        """Get the highest-priority message. Returns None if empty/timeout."""
        with self._not_empty:
            if not self._heap:
                if timeout is None:
                    return None
                self._not_empty.wait(timeout=timeout)
                if not self._heap:
                    return None
            return heapq.heappop(self._heap)

    def get_batch(self, max_count: int = 100) -> list[PrioritizedMessage]:
        """Get up to max_count messages, ordered by priority then sequence.

        Used for batch sending.
        """
        result: list[PrioritizedMessage] = []
        with self._lock:
            while self._heap and len(result) < max_count:
                result.append(heapq.heappop(self._heap))
        return result

    def qsize(self) -> int:
        """Current queue size."""
        with self._lock:
            return len(self._heap)

    def clear(self) -> None:
        """Clear all messages."""
        with self._lock:
            self._heap.clear()
