"""Tests for aitbc.async_tasks — task registry and fire-and-forget spawns (#1602)."""

import asyncio

import pytest

import aitbc.async_tasks as async_tasks
from aitbc.async_tasks import TaskRegistry, create_task_with_logging, get_global_registry


async def test_create_task_with_logging_registers_with_global_registry() -> None:
    """create_task_with_logging tasks must be visible to cancel_all (#1602)."""
    started = asyncio.Event()

    async def forever() -> None:
        started.set()
        await asyncio.sleep(3600)

    name = "test-1602-registered"
    task = create_task_with_logging(forever(), name=name)
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert get_global_registry().get_status()[name] == "running"
    finally:
        await get_global_registry().cancel(name)
        get_global_registry()._tasks.pop(name, None)
    assert task.done()


async def test_global_registry_cancel_all_stops_logging_tasks() -> None:
    """The shutdown path (cancel_all) must reach create_task_with_logging spawns."""
    started = asyncio.Event()

    async def forever() -> None:
        started.set()
        await asyncio.sleep(3600)

    name = "test-1602-cancel-all"
    task = create_task_with_logging(forever(), name=name)
    await asyncio.wait_for(started.wait(), timeout=1)
    try:
        await get_global_registry().cancel_all(timeout=1)
        assert task.done()
    finally:
        get_global_registry()._tasks.pop(name, None)


async def test_track_prunes_done_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    """track() must not grow the registry without bound for per-request spawns."""
    monkeypatch.setattr(async_tasks, "_TRACK_PRUNE_THRESHOLD", 6)
    registry = TaskRegistry()

    async def quick() -> int:
        return 1

    # Fill past the threshold with done tasks, then track a live one.
    for i in range(6):
        t = asyncio.create_task(quick())
        await t
        registry.track(t, name=f"done-{i}")
    assert len(registry._tasks) == 6

    blocker = asyncio.Event()

    async def pending() -> None:
        await blocker.wait()

    live = asyncio.create_task(pending())
    registry.track(live, name="live")
    assert len(registry._tasks) == 7

    # Next track call sees len > threshold and prunes the done entries.
    registry.track(asyncio.create_task(quick()), name="trigger")
    await asyncio.sleep(0)
    assert "live" in registry._tasks
    assert not any(n.startswith("done-") for n in registry._tasks)
    live.cancel()
    blocker.set()
