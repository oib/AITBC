"""Leases are scoped to (node_id, chain_id), not node_id alone.

A node that follows several chains registers once per chain. When the lease
key was node_id alone the second registration overwrote the first, so only the
last chain ever had a valid subscriber and blocks for the others were never
broadcast.
"""

from __future__ import annotations

import time

import pytest
from aitbc_chain.lease_tracker import LEASE_PREFIX, LEASE_SET, LeaseTracker

NODE = "0x51cEe80240DBB2fdcDBF1Fd806659b05242e7903"
CHAIN_A = "ait-hub.aitbc.bubuit.net"
CHAIN_B = "ait-shop-island.aitbc.bubuit.net"


class FakeRedis:
    """Minimal synchronous Redis stand-in covering what LeaseTracker calls."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets: dict[str, set[str]] = {}

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None

    def hset(self, key: str, mapping: dict[str, str]) -> int:
        self.hashes.setdefault(key, {}).update(mapping)
        return len(mapping)

    def hget(self, key: str, field: str) -> str | None:
        return self.hashes.get(key, {}).get(field)

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    def expire(self, key: str, seconds: int) -> bool:
        return key in self.hashes

    def exists(self, key: str) -> int:
        return 1 if key in self.hashes else 0

    def delete(self, key: str) -> int:
        return 1 if self.hashes.pop(key, None) is not None else 0

    def sadd(self, key: str, member: str) -> int:
        members = self.sets.setdefault(key, set())
        added = member not in members
        members.add(member)
        return int(added)

    def srem(self, key: str, member: str) -> int:
        self.sets.setdefault(key, set()).discard(member)
        return 1

    def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))


@pytest.fixture
def tracker() -> LeaseTracker:
    t = LeaseTracker(redis_url="redis://unused")
    t._redis = FakeRedis()  # type: ignore[assignment]  # test double, not a real client
    return t


async def test_registering_a_second_chain_keeps_the_first(tracker: LeaseTracker) -> None:
    await tracker.register_subscriber(NODE, "http", CHAIN_A)
    await tracker.register_subscriber(NODE, "http", CHAIN_B)

    assert [s.chain_id for s in await tracker.get_valid_subscribers(CHAIN_A)] == [CHAIN_A]
    assert [s.chain_id for s in await tracker.get_valid_subscribers(CHAIN_B)] == [CHAIN_B]
    assert len(await tracker.get_valid_subscribers()) == 2


async def test_heartbeat_without_chain_id_extends_every_lease(tracker: LeaseTracker) -> None:
    await tracker.register_subscriber(NODE, "http", CHAIN_A, duration=10)
    await tracker.register_subscriber(NODE, "http", CHAIN_B, duration=10)

    new_expiry = await tracker.extend_lease(NODE, duration=600)

    assert new_expiry > time.time() + 500
    for chain in (CHAIN_A, CHAIN_B):
        assert await tracker.get_lease_expiry(NODE, chain) == pytest.approx(new_expiry)


async def test_heartbeat_with_chain_id_extends_only_that_lease(tracker: LeaseTracker) -> None:
    await tracker.register_subscriber(NODE, "http", CHAIN_A, duration=10)
    await tracker.register_subscriber(NODE, "http", CHAIN_B, duration=10)

    await tracker.extend_lease(NODE, duration=600, chain_id=CHAIN_A)

    assert await tracker.get_lease_expiry(NODE, CHAIN_A) > time.time() + 500
    assert await tracker.get_lease_expiry(NODE, CHAIN_B) < time.time() + 500


async def test_revoke_targets_one_chain_or_all(tracker: LeaseTracker) -> None:
    await tracker.register_subscriber(NODE, "http", CHAIN_A)
    await tracker.register_subscriber(NODE, "http", CHAIN_B)

    assert await tracker.revoke_lease(NODE, CHAIN_A) is True
    assert await tracker.get_lease_expiry(NODE, CHAIN_A) == 0.0
    assert await tracker.get_lease_expiry(NODE, CHAIN_B) > 0.0

    assert await tracker.revoke_lease(NODE) is True
    assert await tracker.get_valid_subscribers() == []
    assert await tracker.revoke_lease(NODE) is False


async def test_legacy_node_keyed_lease_still_resolves(tracker: LeaseTracker) -> None:
    """Leases written before the composite key keep working until they expire."""
    fake = tracker._redis
    fake.hashes[f"{LEASE_PREFIX}{NODE}"] = {  # type: ignore[union-attr]
        "node_id": NODE,
        "transport": "http",
        "chain_id": CHAIN_A,
        "expiry": str(time.time() + 300),
        "client_ip": "10.0.0.1",
    }
    fake.sets[LEASE_SET] = {NODE}  # type: ignore[union-attr]

    assert len(await tracker.get_valid_subscribers(CHAIN_A)) == 1
    assert await tracker.get_lease_expiry(NODE, CHAIN_A) > time.time()
    assert await tracker.get_lease_expiry(NODE, CHAIN_B) == 0.0
    assert await tracker.extend_lease(NODE, duration=600) > time.time() + 500


async def test_registering_replaces_a_legacy_lease(tracker: LeaseTracker) -> None:
    """Re-registration migrates the old key instead of double-counting the node."""
    fake = tracker._redis
    fake.hashes[f"{LEASE_PREFIX}{NODE}"] = {  # type: ignore[union-attr]
        "node_id": NODE,
        "transport": "http",
        "chain_id": CHAIN_A,
        "expiry": str(time.time() + 300),
        "client_ip": "10.0.0.1",
    }
    fake.sets[LEASE_SET] = {NODE}  # type: ignore[union-attr]

    await tracker.register_subscriber(NODE, "http", CHAIN_A)

    assert len(await tracker.get_valid_subscribers(CHAIN_A)) == 1
    assert f"{LEASE_PREFIX}{NODE}" not in fake.hashes  # type: ignore[union-attr]


async def test_expired_leases_are_cleaned_per_chain(tracker: LeaseTracker) -> None:
    await tracker.register_subscriber(NODE, "http", CHAIN_A, duration=300)
    await tracker.register_subscriber(NODE, "http", CHAIN_B, duration=300)
    fake = tracker._redis
    fake.hashes[f"{LEASE_PREFIX}{NODE}|{CHAIN_B}"]["expiry"] = str(time.time() - 1)  # type: ignore[union-attr]

    assert await tracker.cleanup_expired_leases() == 1
    assert [s.chain_id for s in await tracker.get_valid_subscribers()] == [CHAIN_A]
