from __future__ import annotations

import asyncio
import time
from collections import OrderedDict, defaultdict
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from aitbc.async_tasks import create_task_with_logging

from ...metrics import metrics_registry
from .._internal import _increment_publication, _message_id, _set_queue_gauge
from .base import GossipBackend, TopicSubscription


class MeshGossipBackend(GossipBackend):
    """Fan-out / merge gossip over a local bus plus direct links to every peer.

    Every validator runs this backend in its node process with:

    * ``local`` – the intra-host bus (normally Redis) shared with the node's own
      RPC process, whose ``/rpc/gossip/ws`` handler bridges inbound peer
      connections into that bus.
    * ``peers`` – one ``WebsocketGossipBackend`` per remote validator, pointing
      at that validator's ``/rpc/gossip/ws``.

    ``publish`` writes to the local bus synchronously and pushes to every peer
    best-effort in the background, so a slow or dead peer never blocks the
    caller (PBFT awaits its broadcasts). ``subscribe`` merges the local bus and
    all peer links into one queue and drops duplicates by message id, because
    the same message legitimately arrives over several links (direct push from
    the origin plus relay through each peer's RPC bridge). Peers that cannot be
    reached at subscribe time are retried in the background with backoff.

    The topology has no central relay: as long as a validator's node process
    can reach a quorum of peer RPC endpoints, consensus messages flow even when
    any single node (including the hub) is down.
    """

    def __init__(
        self,
        local: GossipBackend,
        peers: dict[str, GossipBackend],
        *,
        dedup_ttl: float = 300.0,
        dedup_max_size: int = 10000,
        peer_publish_timeout: float = 30.0,
        max_inflight_per_peer: int = 64,
        retry_min_delay: float = 1.0,
        retry_max_delay: float = 30.0,
    ) -> None:
        self._local = local
        self._peers = dict(peers)
        self._dedup_ttl = dedup_ttl
        self._dedup_max_size = dedup_max_size
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._seen_lock = asyncio.Lock()
        self._peer_publish_timeout = peer_publish_timeout
        self._max_inflight_per_peer = max_inflight_per_peer
        self._inflight: dict[str, set[asyncio.Task[None]]] = defaultdict(set)
        self._retry_min_delay = retry_min_delay
        self._retry_max_delay = retry_max_delay
        self._subscriptions: set[_MeshSubscription] = set()
        self._running = False

    @property
    def peer_names(self) -> list[str]:
        return list(self._peers.keys())

    async def start(self) -> None:
        from aitbc.aitbc_logging import get_logger

        logger = get_logger(__name__)
        await self._local.start()
        for name, peer in self._peers.items():
            try:
                await peer.start()
            except Exception as e:
                logger.warning("Mesh gossip peer %s failed to start: %s", name, e)
        self._running = True
        metrics_registry.set_gauge("gossip_mesh_peers_configured", float(len(self._peers)))

    async def _remember(self, message_id: str) -> bool:
        """Record ``message_id``; return True if it was already seen recently."""
        now = time.monotonic()
        async with self._seen_lock:
            seen = self._seen
            while seen:
                oldest_id, oldest_ts = next(iter(seen.items()))
                if now - oldest_ts <= self._dedup_ttl:
                    break
                seen.pop(oldest_id, None)
            if message_id in seen:
                return True
            seen[message_id] = now
            if len(seen) > self._dedup_max_size:
                seen.popitem(last=False)
            return False

    def _spawn_peer_publish(self, name: str, coro_factory: Callable[[], Any], topic: str) -> None:
        from aitbc.aitbc_logging import get_logger

        logger = get_logger(__name__)
        inflight = self._inflight[name]
        if len(inflight) >= self._max_inflight_per_peer:
            metrics_registry.increment("gossip_mesh_peer_publish_dropped_total")
            logger.warning(
                "Mesh gossip peer %s has %d publishes in flight; dropping message on %s",
                name,
                len(inflight),
                topic,
            )
            return

        async def _run() -> None:
            try:
                await asyncio.wait_for(coro_factory(), timeout=self._peer_publish_timeout)
                metrics_registry.increment("gossip_mesh_peer_publish_total")
            except Exception as e:
                metrics_registry.increment("gossip_mesh_peer_publish_failed_total")
                logger.info("Mesh gossip publish to peer %s on %s failed: %s", name, topic, e)

        task = create_task_with_logging(_run(), name=f"mesh-gossip-publish:{name}:{topic}")
        inflight.add(task)
        task.add_done_callback(inflight.discard)

    @staticmethod
    def _publish_factory(peer: GossipBackend, topic: str, message: Any) -> Callable[[], Any]:
        # A plain zero-arg closure (as opposed to a `lambda p=peer: ...` default-arg
        # trick) so each call site's peer/topic/message are bound as genuine function
        # parameters -- correct per-iteration capture without confusing mypy's
        # inference of the lambda's implicit parameter type.
        return lambda: peer.publish(topic, message)

    @staticmethod
    def _publish_batch_factory(peer: GossipBackend, topic: str, messages: list[Any]) -> Callable[[], Any]:
        return lambda: peer.publish_batch(topic, messages)

    async def publish(self, topic: str, message: Any) -> None:
        if not self._running:
            raise RuntimeError("Mesh backend not started")
        await self._local.publish(topic, message)
        for name, peer in self._peers.items():
            self._spawn_peer_publish(name, self._publish_factory(peer, topic, message), topic)
        _increment_publication("gossip_mesh_publications", topic)

    async def publish_batch(self, topic: str, messages: list[Any]) -> None:
        if not self._running:
            raise RuntimeError("Mesh backend not started")
        if not messages:
            return
        await self._local.publish_batch(topic, messages)
        for name, peer in self._peers.items():
            self._spawn_peer_publish(name, self._publish_batch_factory(peer, topic, messages), topic)
        _increment_publication("gossip_mesh_publications", topic)

    async def subscribe(self, topic: str, max_queue_size: int = 100) -> TopicSubscription:
        if not self._running:
            raise RuntimeError("Mesh backend not started")
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=max_queue_size)
        sub = _MeshSubscription(self, topic, queue, max_queue_size)
        # The local bus is mandatory: without it the node cannot even hear its
        # own RPC bridge, so a failure here is a real error.
        await sub.attach("local", self._local, retry=False)
        for name, peer in self._peers.items():
            await sub.attach(name, peer, retry=True)
        self._subscriptions.add(sub)

        def _unsubscribe() -> None:
            self._subscriptions.discard(sub)
            create_task_with_logging(sub.close(), name=f"mesh-gossip-unsub:{topic}")

        return TopicSubscription(topic=topic, queue=queue, _unsubscribe=_unsubscribe)

    async def shutdown(self) -> None:
        self._running = False
        for sub in list(self._subscriptions):
            with suppress(Exception):
                await asyncio.wait_for(sub.close(), timeout=5.0)
        self._subscriptions.clear()
        for tasks in self._inflight.values():
            for task in list(tasks):
                task.cancel()
        self._inflight.clear()
        for name, peer in self._peers.items():
            try:
                await asyncio.wait_for(peer.shutdown(), timeout=5.0)
            except Exception as e:
                from aitbc.aitbc_logging import get_logger

                get_logger(__name__).warning("Mesh gossip peer %s shutdown raised: %s", name, e)
        await self._local.shutdown()


class _MeshSubscription:
    """One merged topic subscription across the local bus and all peer links."""

    def __init__(self, mesh: MeshGossipBackend, topic: str, queue: asyncio.Queue[Any], max_queue_size: int) -> None:
        self._mesh = mesh
        self._topic = topic
        self._queue = queue
        self._max_queue_size = max_queue_size
        self._sources: dict[str, TopicSubscription] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._closed = False

    async def attach(self, name: str, backend: GossipBackend, *, retry: bool) -> None:
        try:
            source = await backend.subscribe(self._topic, max_queue_size=self._max_queue_size)
        except Exception as e:
            if not retry:
                raise
            from aitbc.aitbc_logging import get_logger

            get_logger(__name__).warning("Mesh gossip peer %s unavailable for %s; will retry: %s", name, self._topic, e)
            metrics_registry.increment("gossip_mesh_peer_subscribe_failed_total")
            self._tasks[name] = create_task_with_logging(
                self._retry_attach(name, backend),
                name=f"mesh-gossip-retry:{name}:{self._topic}",
            )
            return
        self._sources[name] = source
        self._tasks[name] = create_task_with_logging(
            self._forward(name, source),
            name=f"mesh-gossip-forward:{name}:{self._topic}",
        )

    async def _retry_attach(self, name: str, backend: GossipBackend) -> None:
        from aitbc.aitbc_logging import get_logger

        logger = get_logger(__name__)
        delay = self._mesh._retry_min_delay
        while not self._closed:
            await asyncio.sleep(delay)
            if self._closed:
                return
            try:
                source = await backend.subscribe(self._topic, max_queue_size=self._max_queue_size)
            except Exception as e:
                delay = min(delay * 2, self._mesh._retry_max_delay)
                logger.info("Mesh gossip peer %s still unavailable for %s (retry in %ss): %s", name, self._topic, delay, e)
                continue
            logger.info("Mesh gossip peer %s attached for %s", name, self._topic)
            self._sources[name] = source
            # Replace ourselves with the forwarding loop for this source.
            self._tasks[name] = create_task_with_logging(
                self._forward(name, source),
                name=f"mesh-gossip-forward:{name}:{self._topic}",
            )
            return

    async def _forward(self, name: str, source: TopicSubscription) -> None:
        while not self._closed:
            message = await source.queue.get()
            if await self._mesh._remember(_message_id(self._topic, message)):
                metrics_registry.increment("gossip_mesh_dedup_skipped_total")
                continue
            await self._queue.put(message)
            _set_queue_gauge(self._topic, self._queue.qsize())

    async def close(self) -> None:
        self._closed = True
        for task in self._tasks.values():
            if task is not asyncio.current_task():
                task.cancel()
        for task in self._tasks.values():
            if task is asyncio.current_task():
                continue
            with suppress(asyncio.CancelledError, asyncio.TimeoutError, Exception):
                await asyncio.wait_for(task, timeout=2.0)
        self._tasks.clear()
        for source in self._sources.values():
            with suppress(Exception):
                source.close()
        self._sources.clear()
