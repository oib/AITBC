"""#1529/#1530 pins: agent-coordinator Redis keys must be bounded.

- message hashes carry a TTL; sender/receiver indexes are zsets trimmed to
  MAX_INDEXED_MESSAGES_PER_AGENT and paginated via ZREVRANGE (no SMEMBERS
  fetch-all).
- subscription and peer keys carry TTLs.
- PeerStorage.get_all_peer_connections and AgentRegistry._load_agents_from_redis
  enumerate via SCAN (scan_iter), never KEYS — the fake below deliberately has
  no ``keys`` method so a regression fails loudly.
- WorkflowOrchestrator._load_workflow_execution resolves via the
  ``execution_ref:`` index instead of scanning ``execution:*`` per lookup.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from agent_app.routing.agent_discovery import AgentInfo, AgentRegistry, AgentStatus, AgentType
from agent_app.storage.message_storage import (
    MAX_INDEXED_MESSAGES_PER_AGENT,
    MESSAGE_TTL_SECONDS,
    PEER_TTL_SECONDS,
    MessageStorage,
    PeerStorage,
)
from agent_app.workflow.orchestrator import WorkflowExecution, WorkflowOrchestrator


class FakeRedis:
    """Minimal async Redis: hashes, string keys, sets, zsets. No ``keys``."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.strings: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.ttls: dict[str, int] = {}
        self.scan_iter_calls = 0

    # -- writes ---------------------------------------------------------
    async def hset(self, key, mapping=None, **kwargs):
        h = self.hashes.setdefault(key, {})
        if mapping:
            h.update({str(k): str(v) for k, v in mapping.items()})
        for k, v in kwargs.items():
            h[k] = str(v)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def sadd(self, key, *members):
        self.sets.setdefault(key, set()).update(str(m) for m in members)

    async def srem(self, key, *members):
        s = self.sets.get(key)
        if s:
            s.difference_update(str(m) for m in members)

    async def smembers(self, key):
        return set(self.sets.get(key, set()))

    async def zadd(self, key, mapping):
        z = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            z[str(member)] = float(score)

    async def zrem(self, key, *members):
        z = self.zsets.get(key)
        if z:
            for m in members:
                z.pop(str(m), None)

    async def zremrangebyrank(self, key, start, stop):
        z = self.zsets.get(key)
        if not z:
            return 0
        ordered = sorted(z.items(), key=lambda kv: kv[1])
        n = len(ordered)
        lo = max(start + n, 0) if start < 0 else min(start, n)
        hi = min(stop + n, n - 1) if stop < 0 else min(stop, n - 1)
        removed = ordered[lo : hi + 1] if hi >= lo else []
        for member, _ in removed:
            z.pop(member, None)
        return len(removed)

    async def zrevrange(self, key, start, end):
        z = self.zsets.get(key, {})
        ordered = sorted(z.items(), key=lambda kv: kv[1], reverse=True)
        n = len(ordered)
        lo = max(start + n, 0) if start < 0 else min(start, n)
        hi = min(end + n, n - 1) if end < 0 else min(end, n - 1)
        return [m for m, _ in ordered[lo : hi + 1]] if hi >= lo else []

    async def zcard(self, key):
        return len(self.zsets.get(key, {}))

    async def get(self, key):
        return self.strings.get(key)

    async def set(self, key, value, ex=None, **kwargs):
        self.strings[key] = value if isinstance(value, str) else str(value)
        if ex is not None:
            self.ttls[key] = int(ex)
        return True

    async def delete(self, key):
        removed = 0
        for store in (self.hashes, self.strings, self.sets, self.zsets):
            if key in store:
                del store[key]
                removed += 1
        return removed

    async def expire(self, key, seconds):
        self.ttls[key] = int(seconds)
        return True

    # -- enumeration (SCAN only — deliberately no keys()) ---------------
    async def scan_iter(self, match=None, count=None):
        self.scan_iter_calls += 1
        prefix = (match or "*").rstrip("*")
        for store in (self.hashes, self.strings, self.sets, self.zsets):
            for k in list(store):
                if k.startswith(prefix):
                    yield k


def _storage(redis: FakeRedis) -> MessageStorage:
    s = MessageStorage(redis_url="redis://unused")
    s.redis = redis  # type: ignore[assignment]
    s.sqlite_conn = None
    return s


def _msg(mid: str, sender: str = "a", receiver: str = "b", ts: str = "2026-08-21T12:00:00+00:00") -> dict:
    return {"message_id": mid, "sender_id": sender, "receiver_id": receiver, "content": "x", "timestamp": ts}


@pytest.mark.asyncio
async def test_store_message_sets_ttl_and_zset_indexes():
    r = FakeRedis()
    s = _storage(r)
    await s.store_message("m1", _msg("m1"))

    assert r.ttls["message:m1"] == MESSAGE_TTL_SECONDS
    assert r.zsets["messages:sender:a"] == {"m1": pytest.approx(1787313600.0)}
    assert r.zsets["messages:receiver:b"] == {"m1": pytest.approx(1787313600.0)}
    assert "m1" in r.zsets["messages:timestamp"]


@pytest.mark.asyncio
async def test_index_trim_keeps_newest_entries():
    r = FakeRedis()
    s = _storage(r)
    # Pre-fill beyond the cap, then store one more.
    z = r.zsets.setdefault("messages:sender:a", {})
    for i in range(MAX_INDEXED_MESSAGES_PER_AGENT + 10):
        z[f"old-{i}"] = float(i)
    await s.store_message("new-1", _msg("new-1", ts="2026-08-21T12:00:00+00:00"))

    kept = r.zsets["messages:sender:a"]
    assert len(kept) == MAX_INDEXED_MESSAGES_PER_AGENT
    assert "new-1" in kept
    assert "old-0" not in kept  # oldest trimmed


@pytest.mark.asyncio
async def test_get_messages_by_sender_paginates_and_prunes_stale():
    r = FakeRedis()
    s = _storage(r)
    await s.store_message("m1", _msg("m1", ts="2026-08-21T10:00:00+00:00"))
    await s.store_message("m2", _msg("m2", ts="2026-08-21T11:00:00+00:00"))
    await s.store_message("m3", _msg("m3", ts="2026-08-21T12:00:00+00:00"))

    page = await s.get_messages_by_sender("a", limit=2, offset=0)
    assert [m["message_id"] for m in page] == ["m3", "m2"]  # newest first
    page2 = await s.get_messages_by_sender("a", limit=2, offset=2)
    assert [m["message_id"] for m in page2] == ["m1"]

    # A stale index entry (message hash gone) is pruned on read.
    r.zsets["messages:sender:a"]["ghost"] = 9999999999.0
    await s.get_messages_by_sender("a", limit=10)
    assert "ghost" not in r.zsets["messages:sender:a"]


@pytest.mark.asyncio
async def test_peer_storage_scan_iter_and_ttl():
    r = FakeRedis()
    p = PeerStorage(redis_url="redis://unused")
    p.redis = r  # type: ignore[assignment]

    await p.add_peer("agent-1", "peer-9", {"connected_at": "now"})
    assert r.ttls["peers:agent-1"] == PEER_TTL_SECONDS
    assert r.ttls["peer_connection:agent-1:peer-9"] == PEER_TTL_SECONDS

    conns = await p.get_all_peer_connections()
    assert conns == {"agent-1": ["peer-9"]}
    # FakeRedis has no keys() — reaching it would raise AttributeError.
    assert r.scan_iter_calls >= 1


@pytest.mark.asyncio
async def test_subscription_ttl_set_on_write():
    r = FakeRedis()
    s = _storage(r)
    await s.add_subscription("agent-1", "jobs", {"min_priority": "high"})
    assert r.ttls["subscription:agent-1:jobs"] > 0
    assert r.ttls["subscriptions:agent:agent-1"] > 0
    assert r.ttls["subscriptions:topic:jobs"] > 0


@pytest.mark.asyncio
async def test_workflow_execution_lookup_uses_ref_index():
    r = FakeRedis()
    orch = WorkflowOrchestrator(redis_url="redis://unused")
    orch.redis_client = r

    ex = WorkflowExecution(execution_id="e1", workflow_id="wf-1")
    await orch._save_workflow_execution(ex)

    # Ref index written with same TTL as the row.
    assert r.strings["execution_ref:e1"] == "wf-1"
    assert r.ttls["execution_ref:e1"] == 86400

    loaded = await orch._load_workflow_execution("e1")
    assert loaded is not None
    assert loaded.execution_id == "e1"
    assert loaded.workflow_id == "wf-1"


@pytest.mark.asyncio
async def test_load_agents_from_redis_uses_scan_iter():
    r = FakeRedis()
    registry = AgentRegistry()
    registry.redis_client = r

    payload = json.dumps(
        AgentInfo(
            agent_id="miner-1",
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=[],
            services=[],
            endpoints={},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
        ).to_dict()
    )
    await r.set("agent:miner-1", payload)
    # Foreign key in the same namespace must be skipped, not crash the load.
    await r.set("agent:reqnonce:x", "1")

    await registry._load_agents_from_redis()
    assert list(registry.agents) == ["miner-1"]
    assert r.scan_iter_calls >= 1
