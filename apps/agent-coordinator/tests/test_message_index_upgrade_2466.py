"""Tests for #2466: legacy SET→zset index upgrade must not drop concurrent stores.

``_upgrade_legacy_message_index`` converted SET indexes non-atomically
(TYPE → SMEMBERS → DELETE → ZADD) from every store/read/delete path. Two
coroutines observing ``set`` could interleave such that the second
``DELETE`` landed after a concurrent ``store_message`` ``ZADD``, silently
dropping that message from the inbox index. Upgrades are now serialized
per key with the type re-checked inside the lock.
"""

from __future__ import annotations

import asyncio

import pytest

from agent_app.storage.message_storage import MessageStorage


class _FakeRedis:
    """Minimal async Redis covering the message-index surface."""

    def __init__(self, delete_delay: float = 0.0) -> None:
        self.sets: dict[str, set[str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.hashes: dict[str, dict] = {}
        self.delete_delay = delete_delay
        self.delete_calls = 0

    async def type(self, key: str) -> str:
        if key in self.sets:
            return "set"
        if key in self.zsets:
            return "zset"
        return "none"

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, ()))

    async def zscore(self, key: str, member: str):
        zset = self.zsets.get(key)
        return zset.get(member) if zset else None

    async def hgetall(self, key: str) -> dict:
        return dict(self.hashes.get(key, {}))

    async def delete(self, key: str) -> int:
        self.delete_calls += 1
        if self.delete_delay:
            # Widen the conversion window so an unserialized second upgrade
            # would interleave its DELETE after a concurrent ZADD.
            await asyncio.sleep(self.delete_delay)
        self.sets.pop(key, None)
        self.zsets.pop(key, None)
        return 1

    async def zadd(self, key: str, mapping: dict) -> int:
        zset = self.zsets.setdefault(key, {})
        zset.update({str(m): float(s) for m, s in mapping.items()})
        return len(mapping)

    async def zremrangebyrank(self, key: str, start: int, stop: int) -> int:
        return 0

    async def hset(self, key: str, mapping: dict) -> int:
        self.hashes[key] = dict(mapping)
        return len(mapping)

    async def expire(self, key: str, ttl: int) -> bool:
        return True


def _storage(redis: _FakeRedis) -> MessageStorage:
    storage = MessageStorage(redis_url="redis://unused")
    storage.redis = redis  # type: ignore[assignment]
    return storage


def _legacy_inbox(redis: _FakeRedis, agent: str = "agent-1") -> str:
    """Seed a pre-#1529 SET index plus the legacy message hash it points at."""
    index_key = f"messages:sender:{agent}"
    redis.sets[index_key] = {"old-1"}
    redis.hashes["message:old-1"] = {"message_id": "old-1", "sender": agent, "timestamp": "1700000000.0"}
    return index_key


def _msg(message_id: str, sender: str = "agent-1") -> dict:
    return {"message_id": message_id, "sender": sender, "recipient": "agent-2", "timestamp": "1700000001.0"}


@pytest.mark.asyncio
async def test_concurrent_stores_on_legacy_set_keep_both_ids():
    redis = _FakeRedis(delete_delay=0.02)
    index_key = _legacy_inbox(redis)
    storage = _storage(redis)

    results = await asyncio.gather(
        storage.store_message("m-1", _msg("m-1")),
        storage.store_message("m-2", _msg("m-2")),
    )
    assert results == [True, True]

    assert index_key not in redis.sets
    members = set(redis.zsets[index_key])
    assert {"old-1", "m-1", "m-2"} <= members
    # The conversion ran once — the second caller saw the zset and returned.
    assert redis.delete_calls == 1


@pytest.mark.asyncio
async def test_concurrent_direct_upgrades_convert_once():
    redis = _FakeRedis(delete_delay=0.02)
    index_key = _legacy_inbox(redis)
    storage = _storage(redis)

    await asyncio.gather(
        storage._upgrade_legacy_message_index(index_key),
        storage._upgrade_legacy_message_index(index_key),
    )

    assert index_key not in redis.sets
    assert set(redis.zsets[index_key]) == {"old-1"}
    assert redis.delete_calls == 1


@pytest.mark.asyncio
async def test_store_during_upgrade_window_is_not_dropped():
    """A store that lands while an upgrade is mid-flight keeps its index entry."""
    redis = _FakeRedis(delete_delay=0.05)
    index_key = _legacy_inbox(redis)
    storage = _storage(redis)

    upgrade = asyncio.create_task(storage._upgrade_legacy_message_index(index_key))
    await asyncio.sleep(0.01)  # let the upgrade pass TYPE/SMEMBERS and enter DELETE
    store = asyncio.create_task(storage.store_message("m-late", _msg("m-late")))
    await asyncio.gather(upgrade, store)

    members = set(redis.zsets.get(index_key, {}))
    assert {"old-1", "m-late"} <= members
