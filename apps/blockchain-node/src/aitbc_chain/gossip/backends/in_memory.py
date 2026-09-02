from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from .._internal import (
    _clear_topic_metrics,
    _increment_publication,
    _set_queue_gauge,
    _update_subscriber_metrics,
)
from .base import GossipBackend, TopicSubscription


class InMemoryGossipBackend(GossipBackend):
    def __init__(self) -> None:
        self._topics: dict[str, list[asyncio.Queue[Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, message: Any) -> None:
        async with self._lock:
            queues = list(self._topics.get(topic, []))
        for queue in queues:
            await queue.put(message)
            _set_queue_gauge(topic, queue.qsize())
        _increment_publication("gossip_publications", topic)

    async def publish_batch(self, topic: str, messages: list[Any]) -> None:
        for message in messages:
            await self.publish(topic, message)

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=max_queue_size)
        async with self._lock:
            self._topics[topic].append(queue)
            _update_subscriber_metrics(self._topics)
        _set_queue_gauge(topic, queue.qsize())

        def _unsubscribe() -> None:
            queues = self._topics.get(topic)
            if queues is None or queue not in queues:
                return
            queues.remove(queue)
            if not queues:
                self._topics.pop(topic, None)
                _clear_topic_metrics(topic)
            _update_subscriber_metrics(self._topics)

        return TopicSubscription(topic=topic, queue=queue, _unsubscribe=_unsubscribe)

    async def shutdown(self) -> None:
        async with self._lock:
            topics = list(self._topics.keys())
            self._topics.clear()
        for topic in topics:
            _clear_topic_metrics(topic)
        _update_subscriber_metrics(self._topics)
