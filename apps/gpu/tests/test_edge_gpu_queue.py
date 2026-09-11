"""Tests for the Redis-backed GPU job queue in EdgeGPUService."""

from __future__ import annotations

import asyncio
import uuid

import pytest

# Skip the module when local Redis is not reachable or requires authentication.
_REDIS_TEST_URL = "redis://localhost:6379/0"
try:
    import redis as _redis_sync  # noqa: F401

    _redis = _redis_sync.Redis.from_url(_REDIS_TEST_URL, socket_connect_timeout=2)
    _redis.ping()
    _redis.close()
    from redis.asyncio import Redis  # noqa: E402
except Exception:
    pytestmark = pytest.mark.skip(
        f"Redis at {_REDIS_TEST_URL} is not reachable or requires auth; "
        "configure a reachable Redis instance to run these tests"
    )
    Redis = None  # type: ignore[assignment,misc]

from sqlalchemy.ext.asyncio import AsyncSession

from gpu_service.services.edge_gpu_service import EdgeGPUService
from gpu_service.storage import engine


def _queue_key(gpu_id: str) -> str:
    return f"aitbc:gpu:queue:{gpu_id}"


@pytest.mark.asyncio
async def test_edge_gpu_queue_priority_and_fifo() -> None:
    """Higher-priority jobs are popped first; equal priority is FIFO."""
    gpu_id = f"test-gpu-{uuid.uuid4().hex[:8]}"
    client_id = "test-client"

    # Ensure the Redis key starts empty.
    redis = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    await redis.delete(_queue_key(gpu_id))

    async with AsyncSession(engine, expire_on_commit=False) as session:
        service = EdgeGPUService(session)

        low = await service.queue_job(gpu_id, client_id, 1, {"task": "low"})
        await asyncio.sleep(0.01)
        high_one = await service.queue_job(gpu_id, client_id, 10, {"task": "high-one"})
        await asyncio.sleep(0.01)
        high_two = await service.queue_job(gpu_id, client_id, 10, {"task": "high-two"})

        first = await service.get_next_queued_job(gpu_id)
        second = await service.get_next_queued_job(gpu_id)
        third = await service.get_next_queued_job(gpu_id)

        assert first is not None
        assert first.id == high_one.id
        assert first.status.value == "running"

        assert second is not None
        assert second.id == high_two.id

        assert third is not None
        assert third.id == low.id

        # Complete one job and verify a DB lookup still works.
        completed = await service.complete_job(first.id)
        assert completed is not None
        assert completed.status.value == "completed"

    await redis.delete(_queue_key(gpu_id))
    await redis.aclose()
