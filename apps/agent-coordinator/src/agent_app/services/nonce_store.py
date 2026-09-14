"""One-time nonce store for agent identity attestation and message replay.

Phase A of docs/agent-coordinator/agent-signed-envelopes.md:

* ``GET /v1/agents/nonce`` issues a one-time 300 s nonce that must be covered by
  a registration ``identity_proof`` — this binds the agent_id ↔ identity_address
  claim to a live, fresh request rather than a replayed signature.
* ``POST /api/v1/agent/messages/send`` dedups ``(sender, nonce)`` so a captured
  envelope cannot be replayed inside the timestamp window.

The store prefers the shared Redis client that ``lifespan`` already wires onto
``state`` (the registry's or the message storage's — either is the same
deployment Redis) and falls back to an in-process TTL map. The fallback is
correct on the single-process coordinator and merely best-effort across
restarts, which matches the doc's replay model.
"""

from __future__ import annotations

import time
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.crypto import generate_nonce

from .. import state

logger = get_logger(__name__)

REGISTRATION_NONCE_TTL_SECONDS = 300

_REGISTRATION_KEY_PREFIX = "agent:regnonce:"
_MESSAGE_KEY_PREFIX = "agent:msgnonce:"


def _shared_redis() -> Any | None:
    """Return the Redis client lifespan already opened, if one is up."""
    registry = state.agent_registry
    client = getattr(registry, "redis_client", None)
    if client is not None:
        return client
    return getattr(state.message_storage, "redis", None)


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class NonceStore:
    """Issue/consume registration nonces and dedup message nonces."""

    def __init__(self) -> None:
        # key -> (value, expiry_epoch); used only when Redis is unavailable.
        self._memory: dict[str, tuple[str, float]] = {}

    # -- in-memory fallback ---------------------------------------------------

    def _memory_get(self, key: str) -> str | None:
        entry = self._memory.get(key)
        if entry is None:
            return None
        value, expires = entry
        if expires <= time.time():
            del self._memory[key]
            return None
        return value

    def _memory_set(self, key: str, value: str, ttl: int) -> None:
        self._memory[key] = (value, time.time() + ttl)

    def _memory_pop_match(self, key: str, expected: str) -> bool:
        if self._memory_get(key) != expected:
            return False
        del self._memory[key]
        return True

    # -- registration nonces --------------------------------------------------

    async def issue_registration_nonce(self, agent_id: str) -> str:
        """Return a fresh one-time nonce for ``agent_id`` (300 s TTL)."""
        nonce = generate_nonce(16)
        key = _REGISTRATION_KEY_PREFIX + agent_id
        redis = _shared_redis()
        if redis is not None:
            try:
                await redis.set(key, nonce, ex=REGISTRATION_NONCE_TTL_SECONDS)
                return nonce
            except Exception as e:
                logger.warning("Redis nonce issue failed, using memory fallback: %s", e)
        self._memory_set(key, nonce, REGISTRATION_NONCE_TTL_SECONDS)
        return nonce

    async def consume_registration_nonce(self, agent_id: str, nonce: str) -> bool:
        """Atomically consume ``nonce`` for ``agent_id``; True iff it was valid and unused."""
        if not nonce:
            return False
        key = _REGISTRATION_KEY_PREFIX + agent_id
        redis = _shared_redis()
        if redis is not None:
            try:
                getdel = getattr(redis, "getdel", None)
                if getdel is not None:
                    stored = await getdel(key)
                else:  # redis < 6.2: read-then-delete is not atomic, still one-time
                    stored = await redis.get(key)
                    if stored is not None:
                        await redis.delete(key)
                return _as_str(stored) == nonce
            except Exception as e:
                logger.warning("Redis nonce consume failed, trying memory fallback: %s", e)
        return self._memory_pop_match(key, nonce)

    # -- message nonce dedup --------------------------------------------------

    async def check_message_nonce(self, sender_id: str, nonce: str, ttl: int) -> bool:
        """Record ``(sender_id, nonce)``; True iff it was not seen inside its TTL."""
        if not nonce:
            return True
        key = _MESSAGE_KEY_PREFIX + sender_id + ":" + nonce
        expiry = max(int(ttl), 1)
        redis = _shared_redis()
        if redis is not None:
            try:
                was_set = await redis.set(key, "1", ex=expiry, nx=True)
                return bool(was_set)
            except Exception as e:
                logger.warning("Redis message-nonce check failed, using memory fallback: %s", e)
        if self._memory_get(key) is not None:
            return False
        self._memory_set(key, "1", expiry)
        return True


_nonce_store = NonceStore()


def get_nonce_store() -> NonceStore:
    """Process-wide nonce store; binds to the shared Redis client on each use."""
    return _nonce_store
