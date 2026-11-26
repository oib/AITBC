"""Redis-based lease tracker for offer subscriptions (v0.8.2 §B19).

Manages subscriber leases in Redis with key prefix
``lease:offer_subscriber:{node_id}``.  The blockchain-node has its own
``LeaseTracker`` (``apps/blockchain-node/src/aitbc_chain/lease_tracker.py``)
with prefix ``lease:subscriber:``, but that module imports blockchain-node
config and cannot be shared directly.  This is a minimal, self-contained
implementation for the trading service.

When Redis is unavailable, falls back to in-memory lease tracking so the
service remains functional (and tests pass without Redis).
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

LEASE_PREFIX = "lease:offer_subscriber:"


def hash_lease_token(token: str) -> str:
    """SHA-256 hex digest stored on the lease; the plaintext token is
    returned to the subscriber once at issuance and never persisted."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# redis is an optional dependency (lazy-imported in start()); fold its error
# base into the ops tuple only when importable.
try:
    from redis.exceptions import RedisError as _RedisError

    _REDIS_ERRORS: tuple[type[BaseException], ...] = (_RedisError,)
except ImportError:
    _REDIS_ERRORS = ()

# Expected failure surface below: lazy redis import (ImportError), Redis
# transport errors, URL parse failures, float decode (ValueError), and
# data-shape errors. RuntimeError covers abort-style raises; genuine
# BaseExceptions still propagate (#1862).
_OPS_ERRORS = (
    ImportError,
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    *_REDIS_ERRORS,
)


def _sanitize_url(url: str) -> str:
    """Remove credentials from a URL before logging (same convention as aitbc_chain)."""
    from urllib.parse import urlparse, urlunparse

    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            netloc = f"{parsed.hostname or ''}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except _OPS_ERRORS:
        logger.debug("URL sanitize failed; using raw URL", exc_info=True)
    return url


class OfferLeaseTracker:
    """Manages offer-subscriber leases in Redis with in-memory fallback."""

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis_url = redis_url
        self._redis: Any = None
        self._started = False
        # In-memory fallback: node_id -> expiry timestamp
        self._mem_leases: dict[str, float] = {}
        # In-memory fallback: node_id -> lease token hash (#3028)
        self._mem_lease_tokens: dict[str, str] = {}

    @property
    def started(self) -> bool:
        return self._started

    @property
    def using_redis(self) -> bool:
        """True if the Redis backend is active (not in-memory fallback)."""
        return self._redis is not None

    async def start(self) -> None:
        """Start the lease tracker — connect to Redis if available."""
        if self._started:
            return
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.Redis.from_url(
                self._redis_url, socket_timeout=5, socket_connect_timeout=5, decode_responses=True
            )
            pong = await self._redis.ping()
            logger.info("OfferLeaseTracker connected to Redis (%s): ping=%s", _sanitize_url(self._redis_url), pong)
        except _OPS_ERRORS as e:
            logger.warning(
                "OfferLeaseTracker Redis connection failed (%s), using in-memory fallback: %s",
                _sanitize_url(self._redis_url),
                e,
            )
            self._redis = None
        self._started = True

    async def stop(self) -> None:
        """Stop the lease tracker and release resources."""
        self._started = False
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except _OPS_ERRORS:
                logger.debug("Redis close failed during lease tracker shutdown", exc_info=True)
            self._redis = None
        self._mem_leases.clear()
        self._mem_lease_tokens.clear()
        logger.info("OfferLeaseTracker stopped")

    async def register_subscriber(self, node_id: str, chain_id: str, duration: int, token_hash: str | None = None) -> float:
        """Register a subscriber lease.

        Args:
            node_id: Unique subscriber identifier.
            chain_id: Chain the subscription is for.
            duration: Lease TTL in seconds (heartbeat interval × 3).
            token_hash: SHA-256 hash of the lease bearer token to bind to
                this lease (#3028). Only the hash is stored; ``None`` leaves
                any existing binding untouched.

        Returns:
            Expiry timestamp (Unix seconds).
        """
        if not self._started:
            await self.start()
        expiry = time.time() + duration
        if self._redis is not None:
            key = f"{LEASE_PREFIX}{node_id}"
            try:
                mapping: dict[str, str] = {
                    "node_id": node_id,
                    "chain_id": chain_id,
                    "expiry": str(expiry),
                }
                if token_hash is not None:
                    mapping["token_hash"] = token_hash
                await self._redis.hset(key, mapping=mapping)
                await self._redis.expire(key, duration + 60)
                logger.info("Registered offer subscriber %s (chain=%s) expiry=%s", node_id, chain_id, expiry)
            except _OPS_ERRORS as e:
                logger.warning("Redis register failed for %s, using in-memory: %s", node_id, e)
                self._mem_leases[node_id] = expiry
                if token_hash is not None:
                    self._mem_lease_tokens[node_id] = token_hash
        else:
            self._mem_leases[node_id] = expiry
            if token_hash is not None:
                self._mem_lease_tokens[node_id] = token_hash
        return expiry

    async def lease_token_state(self, node_id: str) -> tuple[bool, str | None]:
        """Return ``(active, token_hash)`` for a subscriber's lease (#3028).

        ``active`` is False when no unexpired lease exists. ``token_hash``
        is the bound bearer-token digest, or ``None`` for a lease issued
        before token binding existed (treated as unbound by callers).
        """
        if not self._started:
            await self.start()
        if self._redis is not None:
            key = f"{LEASE_PREFIX}{node_id}"
            try:
                expiry_str, token_hash = await self._redis.hmget(key, "expiry", "token_hash")
                if not expiry_str:
                    return False, None
                if float(expiry_str) < time.time():
                    await self.revoke_lease(node_id)
                    return False, None
                return True, (token_hash or None)
            except _OPS_ERRORS as e:
                logger.warning("Redis lease-token read failed for %s, using in-memory: %s", node_id, e)
        expiry = self._mem_leases.get(node_id)
        if expiry is None:
            return False, None
        if expiry < time.time():
            self._mem_leases.pop(node_id, None)
            self._mem_lease_tokens.pop(node_id, None)
            return False, None
        return True, self._mem_lease_tokens.get(node_id)

    async def extend_lease(self, node_id: str, duration: int) -> float:
        """Renew a subscriber lease.

        Returns:
            New expiry timestamp, or 0.0 if the lease does not exist.
        """
        if not self._started:
            await self.start()
        if self._redis is not None:
            key = f"{LEASE_PREFIX}{node_id}"
            try:
                exists = await self._redis.exists(key)
                if not exists:
                    logger.warning("Cannot extend lease for unknown subscriber %s", node_id)
                    return 0.0
                new_expiry = time.time() + duration
                await self._redis.hset(key, mapping={"expiry": str(new_expiry)})
                await self._redis.expire(key, duration + 60)
                logger.info("Extended offer lease for %s to %s", node_id, new_expiry)
                return new_expiry
            except _OPS_ERRORS as e:
                logger.warning("Redis extend failed for %s, using in-memory: %s", node_id, e)
                if node_id not in self._mem_leases:
                    return 0.0
                new_expiry = time.time() + duration
                self._mem_leases[node_id] = new_expiry
                return new_expiry
        # In-memory
        if node_id not in self._mem_leases:
            return 0.0
        new_expiry = time.time() + duration
        self._mem_leases[node_id] = new_expiry
        return new_expiry

    async def validate_lease(self, node_id: str) -> bool:
        """Check whether a subscriber's lease is still valid."""
        if not self._started:
            await self.start()
        if self._redis is not None:
            key = f"{LEASE_PREFIX}{node_id}"
            try:
                expiry_str = await self._redis.hget(key, "expiry")
                if not expiry_str:
                    return False
                expiry = float(expiry_str)
                if expiry < time.time():
                    await self.revoke_lease(node_id)
                    return False
                return True
            except _OPS_ERRORS as e:
                logger.warning("Redis validate failed for %s, using in-memory: %s", node_id, e)
                return self._mem_validate(node_id)
        return self._mem_validate(node_id)

    def _mem_validate(self, node_id: str) -> bool:
        expiry = self._mem_leases.get(node_id)
        if expiry is None:
            return False
        if expiry < time.time():
            self._mem_leases.pop(node_id, None)
            self._mem_lease_tokens.pop(node_id, None)
            return False
        return True

    async def revoke_lease(self, node_id: str) -> bool:
        """Revoke a subscriber lease.

        Returns:
            True if revoked, False if not found.
        """
        if not self._started:
            await self.start()
        if self._redis is not None:
            key = f"{LEASE_PREFIX}{node_id}"
            try:
                result = await self._redis.delete(key)
                return bool(result)
            except _OPS_ERRORS as e:
                logger.warning("Redis revoke failed for %s, using in-memory: %s", node_id, e)
                self._mem_lease_tokens.pop(node_id, None)
                return self._mem_leases.pop(node_id, None) is not None
        self._mem_lease_tokens.pop(node_id, None)
        return self._mem_leases.pop(node_id, None) is not None

    async def get_lease_expiry(self, node_id: str) -> float:
        """Get the current lease expiry for a subscriber.

        Returns:
            Expiry timestamp (0.0 if not found or expired).
        """
        if not self._started:
            await self.start()
        if self._redis is not None:
            key = f"{LEASE_PREFIX}{node_id}"
            try:
                expiry_str = await self._redis.hget(key, "expiry")
                if not expiry_str:
                    return 0.0
                expiry = float(expiry_str)
                if expiry < time.time():
                    await self.revoke_lease(node_id)
                    return 0.0
                return expiry
            except _OPS_ERRORS as e:
                logger.warning("Redis get-expiry failed for %s, using in-memory: %s", node_id, e)
                expiry = self._mem_leases.get(node_id, 0.0)
                if expiry and expiry < time.time():
                    self._mem_leases.pop(node_id, None)
                    self._mem_lease_tokens.pop(node_id, None)
                    return 0.0
                return expiry
        expiry = self._mem_leases.get(node_id, 0.0)
        if expiry and expiry < time.time():
            self._mem_leases.pop(node_id, None)
            self._mem_lease_tokens.pop(node_id, None)
            return 0.0
        return expiry
