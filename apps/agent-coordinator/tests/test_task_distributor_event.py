"""AUDIT-RETRY (#1576): TaskDistributor must sleep on an event while all
priority queues are empty instead of polling five queues at ~100 Hz."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from agent_app.routing.load_balancer import LoadBalancer, TaskDistributor, TaskPriority


@pytest.fixture
def distributor() -> TaskDistributor:
    return TaskDistributor(LoadBalancer(registry=AsyncMock()))


async def test_distribution_loop_wakes_on_submit(distributor: TaskDistributor) -> None:
    distributed: list[dict] = []

    async def spy_distribute(task_info: dict) -> None:
        distributed.append(task_info)

    distributor._distribute_task = spy_distribute  # type: ignore[method-assign]
    task = asyncio.create_task(distributor.start_distribution())
    try:
        # Empty queues: the loop parks on the event — no hot polling.
        await asyncio.sleep(0.05)
        assert distributed == []
        assert not distributor._work_event.is_set()

        await distributor.submit_task({"job": "x"}, priority=TaskPriority.URGENT)
        for _ in range(100):
            if distributed:
                break
            await asyncio.sleep(0.01)
        assert len(distributed) == 1
        assert distributed[0]["task_data"] == {"job": "x"}
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_priority_order_preserved(distributor: TaskDistributor) -> None:
    order: list[str] = []

    async def spy_distribute(task_info: dict) -> None:
        order.append(task_info["task_data"]["tag"])

    distributor._distribute_task = spy_distribute  # type: ignore[method-assign]
    # Submit both before the loop starts so the drain order is deterministic.
    await distributor.submit_task({"tag": "low"}, priority=TaskPriority.LOW)
    await distributor.submit_task({"tag": "urgent"}, priority=TaskPriority.URGENT)
    task = asyncio.create_task(distributor.start_distribution())
    try:
        for _ in range(200):
            if len(order) == 2:
                break
            await asyncio.sleep(0.01)
        # URGENT queue is drained before LOW regardless of submit order.
        assert order == ["urgent", "low"]
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
