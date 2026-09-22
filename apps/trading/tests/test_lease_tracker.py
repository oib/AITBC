"""Regression tests for ``OfferLeaseTracker``.

Every Redis call in this tracker was written as
``await asyncio.to_thread(self._redis.hset, ...)`` against a
``redis.asyncio`` client.  ``to_thread`` *calls* the method in a worker
thread, which for a coroutine function merely builds a coroutine object and
returns it; the object was then discarded un-awaited.  No command ever
reached Redis and no exception was raised, so the ``except Exception``
in-memory fallback never engaged either — ``register_subscriber`` logged
success and returned a plausible expiry while the key did not exist, and
``extend_lease``/``revoke_lease`` reported success for node IDs that had
never been registered (a coroutine object is truthy, so ``if not exists:``
never fired).  The only visible symptom was a ``RuntimeWarning: coroutine
'Redis.execute_command' was never awaited`` attributed to whatever frame
happened to be running at GC time.

The load-bearing assertions below are therefore ``assert_awaited*`` rather
than ``assert_called*``: the old code *called* every mock exactly as the new
code does, and differs only in never awaiting the result.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from trading_service.services.lease_tracker import LEASE_PREFIX, OfferLeaseTracker

NODE = "node-a"
KEY = f"{LEASE_PREFIX}{NODE}"


@pytest.fixture
def redis_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.ping.return_value = True
    return mock


async def _started(redis_mock: AsyncMock) -> OfferLeaseTracker:
    """A tracker whose ``start()`` connected to ``redis_mock``."""
    tracker = OfferLeaseTracker("redis://mock:6379/0")
    with patch("redis.asyncio.Redis.from_url", return_value=redis_mock):
        await tracker.start()
    assert tracker.using_redis
    return tracker


# ---------------------------------------------------------------------------
# register_subscriber
# ---------------------------------------------------------------------------


async def test_register_subscriber_awaits_the_redis_writes(redis_mock: AsyncMock) -> None:
    tracker = await _started(redis_mock)

    expiry = await tracker.register_subscriber(node_id=NODE, chain_id="ait-hub", duration=30)

    redis_mock.hset.assert_awaited_once_with(KEY, mapping={"node_id": NODE, "chain_id": "ait-hub", "expiry": str(expiry)})
    redis_mock.expire.assert_awaited_once_with(KEY, 90)
    assert time.time() <= expiry <= time.time() + 30


async def test_register_subscriber_does_not_shadow_into_memory_on_success(redis_mock: AsyncMock) -> None:
    """The in-memory dict is the *fallback*; a successful Redis write must not populate it."""
    tracker = await _started(redis_mock)

    await tracker.register_subscriber(node_id=NODE, chain_id="ait-hub", duration=30)

    assert tracker._mem_leases == {}


async def test_register_subscriber_falls_back_to_memory_when_redis_raises(redis_mock: AsyncMock) -> None:
    """A *raised* Redis error is the only thing that reaches the fallback; the bug raised nothing."""
    redis_mock.hset.side_effect = RuntimeError("connection reset")
    tracker = await _started(redis_mock)

    expiry = await tracker.register_subscriber(node_id=NODE, chain_id="ait-hub", duration=30)

    assert tracker._mem_leases[NODE] == expiry
    redis_mock.expire.assert_not_awaited()


# ---------------------------------------------------------------------------
# extend_lease
# ---------------------------------------------------------------------------


async def test_extend_lease_refuses_an_unregistered_node(redis_mock: AsyncMock) -> None:
    """``EXISTS`` returning 0 must short-circuit — the bug made this branch unreachable."""
    redis_mock.exists.return_value = 0
    tracker = await _started(redis_mock)

    assert await tracker.extend_lease(node_id="never-registered", duration=30) == 0.0

    redis_mock.exists.assert_awaited_once_with(f"{LEASE_PREFIX}never-registered")
    redis_mock.hset.assert_not_awaited()
    redis_mock.expire.assert_not_awaited()


async def test_extend_lease_renews_an_existing_node(redis_mock: AsyncMock) -> None:
    redis_mock.exists.return_value = 1
    tracker = await _started(redis_mock)

    new_expiry = await tracker.extend_lease(node_id=NODE, duration=30)

    redis_mock.hset.assert_awaited_once_with(KEY, mapping={"expiry": str(new_expiry)})
    redis_mock.expire.assert_awaited_once_with(KEY, 90)
    assert time.time() <= new_expiry <= time.time() + 30


# ---------------------------------------------------------------------------
# validate_lease / get_lease_expiry
# ---------------------------------------------------------------------------


async def test_validate_lease_reads_the_stored_expiry(redis_mock: AsyncMock) -> None:
    future = time.time() + 60
    redis_mock.hget.return_value = str(future)
    tracker = await _started(redis_mock)

    assert await tracker.validate_lease(NODE) is True
    redis_mock.hget.assert_awaited_once_with(KEY, "expiry")


async def test_validate_lease_revokes_an_expired_lease(redis_mock: AsyncMock) -> None:
    redis_mock.hget.return_value = str(time.time() - 1)
    redis_mock.delete.return_value = 1
    tracker = await _started(redis_mock)

    assert await tracker.validate_lease(NODE) is False
    redis_mock.delete.assert_awaited_once_with(KEY)


async def test_validate_lease_is_false_for_a_missing_key(redis_mock: AsyncMock) -> None:
    redis_mock.hget.return_value = None
    tracker = await _started(redis_mock)

    assert await tracker.validate_lease(NODE) is False
    redis_mock.delete.assert_not_awaited()


async def test_get_lease_expiry_returns_the_stored_float(redis_mock: AsyncMock) -> None:
    future = time.time() + 60
    redis_mock.hget.return_value = str(future)
    tracker = await _started(redis_mock)

    assert await tracker.get_lease_expiry(NODE) == pytest.approx(future)


async def test_get_lease_expiry_is_zero_for_a_missing_key(redis_mock: AsyncMock) -> None:
    redis_mock.hget.return_value = None
    tracker = await _started(redis_mock)

    assert await tracker.get_lease_expiry(NODE) == 0.0


# ---------------------------------------------------------------------------
# revoke_lease
# ---------------------------------------------------------------------------


async def test_revoke_lease_reports_what_redis_deleted(redis_mock: AsyncMock) -> None:
    redis_mock.delete.return_value = 1
    tracker = await _started(redis_mock)

    assert await tracker.revoke_lease(NODE) is True
    redis_mock.delete.assert_awaited_once_with(KEY)


async def test_revoke_lease_is_false_when_nothing_was_deleted(redis_mock: AsyncMock) -> None:
    """``DELETE`` returning 0 must read as "not found" — the bug always reported True."""
    redis_mock.delete.return_value = 0
    tracker = await _started(redis_mock)

    assert await tracker.revoke_lease("never-registered") is False


# ---------------------------------------------------------------------------
# Round trip against a fake Redis, and the in-memory fallback
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Just enough of ``redis.asyncio`` to hold a hash and a TTL."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.ttls: dict[str, int] = {}

    async def ping(self) -> bool:
        return True

    async def hset(self, key: str, mapping: dict[str, str]) -> int:
        self.hashes.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True

    async def exists(self, key: str) -> int:
        return int(key in self.hashes)

    async def hget(self, key: str, field: str) -> Any:
        return self.hashes.get(key, {}).get(field)

    async def delete(self, key: str) -> int:
        self.ttls.pop(key, None)
        return int(self.hashes.pop(key, None) is not None)

    async def aclose(self) -> None:
        return None


async def test_round_trip_against_a_fake_redis() -> None:
    """The end-to-end shape the fleet probe checks: the key actually lands, with a TTL."""
    fake = _FakeRedis()
    tracker = OfferLeaseTracker("redis://mock:6379/0")
    with patch("redis.asyncio.Redis.from_url", return_value=fake):
        await tracker.start()

    expiry = await tracker.register_subscriber(node_id=NODE, chain_id="ait-hub", duration=30)

    assert fake.hashes[KEY] == {"node_id": NODE, "chain_id": "ait-hub", "expiry": str(expiry)}
    assert fake.ttls[KEY] == 90
    assert await tracker.validate_lease(NODE) is True
    assert await tracker.get_lease_expiry(NODE) == pytest.approx(expiry)

    extended = await tracker.extend_lease(node_id=NODE, duration=60)
    assert extended > expiry
    assert fake.hashes[KEY]["expiry"] == str(extended)
    assert fake.ttls[KEY] == 120

    assert await tracker.extend_lease(node_id="never-registered", duration=60) == 0.0
    assert await tracker.revoke_lease(NODE) is True
    assert await tracker.revoke_lease(NODE) is False
    assert await tracker.validate_lease(NODE) is False


async def test_in_memory_fallback_when_redis_is_unavailable() -> None:
    tracker = OfferLeaseTracker("redis://mock:6379/0")
    with patch("redis.asyncio.Redis.from_url", side_effect=RuntimeError("no redis here")):
        await tracker.start()

    assert tracker.started
    assert not tracker.using_redis

    expiry = await tracker.register_subscriber(node_id=NODE, chain_id="ait-hub", duration=30)
    assert await tracker.validate_lease(NODE) is True
    assert await tracker.get_lease_expiry(NODE) == pytest.approx(expiry)
    assert await tracker.extend_lease(node_id=NODE, duration=60) > expiry
    assert await tracker.extend_lease(node_id="never-registered", duration=60) == 0.0
    assert await tracker.revoke_lease(NODE) is True
    assert await tracker.revoke_lease(NODE) is False
