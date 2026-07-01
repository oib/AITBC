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

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

LEASE_PREFIX = "lease:offer_subscriber:"


class OfferLeaseTracker:
    """Manages offer-subscriber leases in Redis with in-memory fallback."""

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis_url = redis_url
        self._redis: Any = None
        self._started = False
        # In-memory fallback: node_id -> expiry timestamp
        self._mem_leases: dict[str, float] = {}

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
            logger.info("OfferLeaseTracker connected to Redis (%s): ping=%s", self._redis_url, pong)
        except Exception as e:
            logger.warning("OfferLeaseTracker Redis connection failed (%s), using in-memory fallback: %s", self._redis_url, e)
            self._redis = None
        self._started = True

    async def stop(self) -> None:
        """Stop the lease tracker and release resources."""
        self._started = False
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
        self._mem_leases.clear()
        logger.info("OfferLeaseTracker stopped")

    async def register_subscriber(self, node_id: str, chain_id: str, duration: int) -> float:
        """Register a subscriber lease.

        Args:
            node_id: Unique subscriber identifier.
            chain_id: Chain the subscription is for.
            duration: Lease TTL in seconds (heartbeat interval × 3).

        Returns:
            Expiry timestamp (Unix seconds).
        """
        if not self._started:
            await self.start()
        expiry = time.time() + duration
        if self._redis is not None:
            key = f"{LEASE_PREFIX}{node_id}"
            try:
                await asyncio.to_thread(
                    self._redis.hset,
                    key,
                    mapping={
                        "node_id": node_id,
                        "chain_id": chain_id,
                        "expiry": str(expiry),
                    },
                )
                await asyncio.to_thread(self._redis.expire, key, duration + 60)
                logger.info("Registered offer subscriber %s (chain=%s) expiry=%s", node_id, chain_id, expiry)
            except Exception as e:
                logger.warning("Redis register failed for %s, using in-memory: %s", node_id, e)
                self._mem_leases[node_id] = expiry
        else:
            self._mem_leases[node_id] = expiry
        return expiry

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
                exists = await asyncio.to_thread(self._redis.exists, key)
                if not exists:
                    logger.warning("Cannot extend lease for unknown subscriber %s", node_id)
                    return 0.0
                new_expiry = time.time() + duration
                await asyncio.to_thread(self._redis.hset, key, mapping={"expiry": str(new_expiry)})
                await asyncio.to_thread(self._redis.expire, key, duration + 60)
                logger.info("Extended offer lease for %s to %s", node_id, new_expiry)
                return new_expiry
            except Exception as e:
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
                expiry_str = await asyncio.to_thread(self._redis.hget, key, "expiry")
                if not expiry_str:
                    return False
                expiry = float(expiry_str)
                if expiry < time.time():
                    await self.revoke_lease(node_id)
                    return False
                return True
            except Exception as e:
                logger.warning("Redis validate failed for %s, using in-memory: %s", node_id, e)
                return self._mem_validate(node_id)
        return self._mem_validate(node_id)

    def _mem_validate(self, node_id: str) -> bool:
        expiry = self._mem_leases.get(node_id)
        if expiry is None:
            return False
        if expiry < time.time():
            self._mem_leases.pop(node_id, None)
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
                result = await asyncio.to_thread(self._redis.delete, key)
                return bool(result)
            except Exception as e:
                logger.warning("Redis revoke failed for %s, using in-memory: %s", node_id, e)
                return node_id in self._mem_leases.pop(node_id, None)  # type: ignore[return-value]
        return node_id in self._mem_leases.pop(node_id, None)  # type: ignore[return-value]

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
                expiry_str = await asyncio.to_thread(self._redis.hget, key, "expiry")
                if not expiry_str:
                    return 0.0
                expiry = float(expiry_str)
                if expiry < time.time():
                    await self.revoke_lease(node_id)
                    return 0.0
                return expiry
            except Exception as e:
                logger.warning("Redis get-expiry failed for %s, using in-memory: %s", node_id, e)
                expiry = self._mem_leases.get(node_id, 0.0)
                if expiry and expiry < time.time():
                    self._mem_leases.pop(node_id, None)
                    return 0.0
                return expiry
        expiry = self._mem_leases.get(node_id, 0.0)
        if expiry and expiry < time.time():
            self._mem_leases.pop(node_id, None)
            return 0.0
        return expiry
