"""#1533 pins: RedisStateManager per-key docs carry TTL and enumerate via SCAN.

Hash fields cannot expire individually, so exchange payments moved to
``set_doc``/``get_doc``/``docs`` — one Redis string key per payment with
``EX``, enumerated with ``SCAN`` batches (never KEYS/HGETALL).
"""

from __future__ import annotations

import pytest

from coordinator_api.contexts.infrastructure.services.redis_state import RedisStateManager


class _FakeRedis:
    """String-key stand-in: set(ex=), get, scan, delete."""

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.scan_calls = 0

    async def set(self, key, value, ex=None):
        self.strings[key] = value
        if ex is not None:
            self.ttls[key] = int(ex)
        return True

    async def get(self, key):
        return self.strings.get(key)

    async def delete(self, *keys):
        n = 0
        for k in keys:
            n += int(self.strings.pop(k, None) is not None)
        return n

    async def scan(self, cursor, match=None, count=None):
        self.scan_calls += 1
        prefix = (match or "*").rstrip("*")
        return 0, [k for k in self.strings if k.startswith(prefix)]


def _manager_with_redis(r: _FakeRedis) -> RedisStateManager:
    m = RedisStateManager()
    m._redis = r
    m._initialized = True
    return m


@pytest.mark.asyncio
async def test_set_doc_stores_json_with_ttl():
    r = _FakeRedis()
    m = _manager_with_redis(r)
    await m.set_doc("exchange", "pay-1", {"payment_id": "pay-1", "status": "pending"}, ttl=3600)

    assert r.ttls["aitbc:coordinator:exchange:pay-1"] == 3600
    got = await m.get_doc("exchange", "pay-1")
    assert got == {"payment_id": "pay-1", "status": "pending"}


@pytest.mark.asyncio
async def test_docs_enumerates_via_scan_and_expires():
    r = _FakeRedis()
    m = _manager_with_redis(r)
    await m.set_doc("exchange", "p1", {"a": 1}, ttl=100)
    await m.set_doc("exchange", "p2", {"a": 2}, ttl=100)
    # A hash-namespace key and another namespace must not leak into docs().
    r.strings["aitbc:coordinator:exchange"] = "{}"  # the old hash key shape
    r.strings["aitbc:coordinator:other:x"] = "{}"

    docs = await m.docs("exchange")
    assert set(docs) == {"p1", "p2"}
    assert docs["p1"] == {"a": 1}
    assert r.scan_calls >= 1


@pytest.mark.asyncio
async def test_docs_memory_fallback():
    m = RedisStateManager()
    m._redis = None
    await m.set_doc("exchange", "p1", {"a": 1}, ttl=100)
    docs = await m.docs("exchange")
    assert docs == {"p1": {"a": 1}}
    await m.delete_doc("exchange", "p1")
    assert await m.docs("exchange") == {}
