"""Regression tests for the WebsocketGossipBackend reconnect lifecycle.

#705: a failed reconnect used to suppress every subsequent attempt — the
nested ``_schedule_reconnect`` ran while the topic was still marked
``_reconnecting``, and the outer task then discarded the marker on exit,
leaving an active subscriber with no retry task. These tests pin the
discard-before-schedule ordering.
"""

from __future__ import annotations

import asyncio

import pytest
from aitbc_chain.gossip.backends import websocket as wsmod
from aitbc_chain.gossip.backends.websocket import WebsocketGossipBackend

TOPIC = "blocks.bc-2"


def _backend_with_subscriber() -> WebsocketGossipBackend:
    backend = WebsocketGossipBackend("ws://127.0.0.1:1/rpc/gossip/ws")
    backend._running = True
    backend._ref_counts[TOPIC] = 1
    backend._queues[TOPIC] = asyncio.Queue()
    backend._reconnect_backoff[TOPIC] = 0.01
    return backend


@pytest.mark.asyncio
async def test_failed_reconnect_schedules_next_attempt() -> None:
    """One transient failure must not strand an active subscriber."""
    backend = _backend_with_subscriber()
    attempts: list[str] = []
    recovered = asyncio.Event()

    async def fake_ensure(topic: str) -> None:
        attempts.append(topic)
        if len(attempts) == 1:
            raise RuntimeError("simulated restart-window HTTP 502")
        recovered.set()

    backend._ensure_connection = fake_ensure  # type: ignore[method-assign]
    spawned: list[asyncio.Task[None]] = []
    original_spawn = wsmod.create_task_with_logging
    wsmod.create_task_with_logging = lambda coro, *, name: spawned.append(original_spawn(coro, name=name))
    try:
        backend._schedule_reconnect(TOPIC)
        await asyncio.wait_for(recovered.wait(), timeout=1.0)
        # The first attempt failed; a second attempt ran without any external
        # trigger and succeeded — the retry path is alive again.
        assert len(attempts) >= 2
        # On success the backoff resets and no further reconnect is pending
        # (the reader takes over on the next real connection drop).
        assert backend._reconnect_backoff[TOPIC] == 0.5
        assert TOPIC not in backend._reconnecting
        assert backend._ref_counts[TOPIC] == 1
        assert TOPIC in backend._queues
    finally:
        backend._running = False
        wsmod.create_task_with_logging = original_spawn
        for task in spawned:
            if not task.done():
                task.cancel()
        await asyncio.gather(*spawned, return_exceptions=True)


@pytest.mark.asyncio
async def test_concurrent_schedule_does_not_spawn_second_task() -> None:
    """A schedule while a reconnect task is pending must not duplicate it."""
    backend = _backend_with_subscriber()
    attempts = 0
    in_attempt = asyncio.Event()
    release = asyncio.Event()

    async def slow_ensure(topic: str) -> None:
        nonlocal attempts
        attempts += 1
        in_attempt.set()
        await release.wait()

    backend._ensure_connection = slow_ensure  # type: ignore[method-assign]
    spawned: list[asyncio.Task[None]] = []
    original_spawn = wsmod.create_task_with_logging
    wsmod.create_task_with_logging = lambda coro, *, name: spawned.append(original_spawn(coro, name=name))
    try:
        backend._schedule_reconnect(TOPIC)
        await asyncio.wait_for(in_attempt.wait(), timeout=1.0)
        # While the first task is inside _ensure_connection, the marker is
        # still held — a second schedule is a no-op.
        backend._schedule_reconnect(TOPIC)
        await asyncio.sleep(0.05)
        assert len(spawned) == 1
        release.set()
        await asyncio.gather(*spawned)
        assert attempts == 1
    finally:
        backend._running = False
        wsmod.create_task_with_logging = original_spawn
        for task in spawned:
            if not task.done():
                task.cancel()
        await asyncio.gather(*spawned, return_exceptions=True)


@pytest.mark.asyncio
async def test_unsubscribed_topic_aborts_pending_reconnect() -> None:
    """A subscriber that closed during backoff gets no reconnect."""
    backend = _backend_with_subscriber()
    attempts = 0

    async def fake_ensure(topic: str) -> None:
        nonlocal attempts
        attempts += 1

    backend._ensure_connection = fake_ensure  # type: ignore[method-assign]
    backend._schedule_reconnect(TOPIC)
    # Subscriber drops out before the backoff sleep completes.
    backend._ref_counts[TOPIC] = 0
    await asyncio.sleep(0.1)
    assert attempts == 0
    assert TOPIC not in backend._reconnecting
    backend._running = False
