"""agent:* redis scan must survive foreign keys in the same namespace (#628).

The discovery loader globs ``agent:*``; nonce dedup keys written as the
literal ``"1"`` under that prefix used to crash the load at startup with
``'int' object is not subscriptable``. Nonces now live under ``agentnonce:*``
and the loader skips anything that is not a JSON object.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from agent_app import state as app_state
from agent_app.routing.agent_discovery import AgentInfo, AgentRegistry, AgentStatus, AgentType
from agent_app.services import nonce_store


class _FakeRedis:
    """Minimal async Redis stand-in: string keys only, NX semantics for dedup."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def keys(self, pattern: str) -> list[str]:
        prefix = pattern.rstrip("*")
        return [k for k in self.store if k.startswith(prefix)]

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex=None, nx: bool = False):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)

    async def getdel(self, key: str) -> str | None:
        return self.store.pop(key, None)


def _agent_payload(agent_id: str) -> str:
    return json.dumps(
        AgentInfo(
            agent_id=agent_id,
            agent_type=AgentType.WORKER,
            status=AgentStatus.ACTIVE,
            capabilities=["compute"],
            services=["miner"],
            endpoints={},
            metadata={},
            last_heartbeat=datetime.now(UTC),
            registration_time=datetime.now(UTC),
        ).to_dict()
    )


async def test_load_skips_non_dict_keys_in_agent_namespace():
    redis = _FakeRedis()
    # Bad keys first: without the per-key guard the load aborts here and the
    # valid agent scanned afterwards is never registered.
    redis.store["agent:reqnonce:miner-1:deadbeef"] = "1"  # int payload
    redis.store["agent:regnonce:miner-2"] = "abc123nonce"  # non-JSON string
    redis.store["agent:miner-1"] = _agent_payload("miner-1")
    registry = AgentRegistry()
    registry.redis_client = redis

    await registry._load_agents_from_redis()

    assert list(registry.agents) == ["miner-1"]
    assert registry.agents["miner-1"].agent_type == AgentType.WORKER


async def test_load_skips_malformed_agent_record_but_keeps_valid_ones():
    redis = _FakeRedis()
    redis.store["agent:broken"] = '{"agent_id": "broken"}'  # dict but incomplete
    redis.store["agent:miner-1"] = _agent_payload("miner-1")
    registry = AgentRegistry()
    registry.redis_client = redis

    await registry._load_agents_from_redis()

    assert list(registry.agents) == ["miner-1"]


async def test_nonce_writes_use_agentnonce_prefix(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(app_state, "agent_registry", SimpleNamespace(redis_client=redis))
    monkeypatch.setattr(app_state, "message_storage", SimpleNamespace(redis=None))

    store = nonce_store.NonceStore()
    await store.issue_registration_nonce("miner-1")
    await store.issue_login_nonce("miner-1")
    await store.check_message_nonce("miner-1", "n1", 60)
    await store.check_request_nonce("miner-1", "n2", 60)

    assert redis.store, "expected nonce keys to be written"
    assert all(k.startswith("agentnonce:") for k in redis.store)
    assert not any(k.startswith("agent:") for k in redis.store)

    # And a discovery load alongside those writes stays clean.
    redis.store["agent:miner-1"] = _agent_payload("miner-1")
    registry = AgentRegistry()
    registry.redis_client = redis
    await registry._load_agents_from_redis()
    assert list(registry.agents) == ["miner-1"]
