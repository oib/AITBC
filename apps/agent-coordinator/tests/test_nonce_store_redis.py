"""#749 regression: _issue/_dedup must actually await redis.set — an
unawaited call dropped the coroutine, so fresh nonces never persisted
and every consume failed (403 invalid_identity_nonce)."""

from __future__ import annotations

import pytest

from agent_app.services.nonce_store import NonceStore


class FakeAsyncRedis:
    """Minimal async redis stand-in recording real state."""

    def __init__(self):
        self.data: dict[str, str] = {}
        self.set_calls = 0

    async def set(self, key, value, ex=None, nx=False):
        self.set_calls += 1
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def getdel(self, key):
        return self.data.pop(key, None)


@pytest.mark.asyncio
async def test_issue_then_consume_via_redis_backend(monkeypatch):
    redis = FakeAsyncRedis()
    monkeypatch.setattr("agent_app.services.nonce_store._shared_redis", lambda: redis)
    store = NonceStore()
    nonce = await store.issue_registration_nonce("agent-1")
    assert redis.set_calls == 1  # the unawaited call made this 0 pre-fix
    assert await store.consume_registration_nonce("agent-1", nonce) is True
    # consumed — replay must fail
    assert await store.consume_registration_nonce("agent-1", nonce) is False


@pytest.mark.asyncio
async def test_dedup_actually_records(monkeypatch):
    redis = FakeAsyncRedis()
    monkeypatch.setattr("agent_app.services.nonce_store._shared_redis", lambda: redis)
    store = NonceStore()
    assert await store.check_request_nonce("a", "n1", 60) is True
    # second claim of the same (agent, nonce) must be refused — pre-fix the
    # coroutine object made bool(was_set) always True AND wrote nothing
    assert await store.check_request_nonce("a", "n1", 60) is False
