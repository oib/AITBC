"""Redis-based lease tracker for block subscription system."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import redis

from .config import settings
from .logger import get_logger

logger = get_logger(__name__)

# Redis keys
LEASE_PREFIX = "lease:subscriber:"
LEASE_SET = "lease:subscribers"


@dataclass
class SubscriberInfo:
    """Information about a subscriber."""
    node_id: str
    transport: str
    expiry: float
    chain_id: str


class LeaseTracker:
    """Manages subscriber leases in Redis."""

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url or settings.gossip_broadcast_url
        self._redis: redis.Redis | None = None
        self._running = False
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the lease tracker and background cleanup task."""
        if self._running:
            logger.info("Lease tracker already running")
            return

        try:
            logger.info(f"Starting lease tracker with Redis URL: {self._redis_url}")
            # Parse Redis URL
            if self._redis_url.startswith("redis://"):
                self._redis = redis.from_url(self._redis_url, decode_responses=True)
            else:
                self._redis = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

            logger.info(f"Redis client created: connected to {self._redis_url}")
            # Test connection
            pong = await asyncio.to_thread(self._redis.ping)
            logger.info(f"Redis ping successful: {pong}")
            self._running = True

            # Start background cleanup task
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Lease tracker started successfully")
        except Exception as e:
            logger.error(f"Failed to start lease tracker: {e}", exc_info=True)
            raise

    async def stop(self) -> None:
        """Stop the lease tracker."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await asyncio.to_thread(self._redis.close)
        logger.info("Lease tracker stopped")

    async def register_subscriber(
        self,
        node_id: str,
        transport: str,
        chain_id: str,
        duration: int | None = None
    ) -> float:
        """Register a subscriber with a lease.

        Args:
            node_id: Unique identifier for the subscriber node
            transport: Transport method (websocket, http, redis)
            chain_id: Chain ID for the subscription
            duration: Lease duration in seconds (defaults to settings.lease_duration)

        Returns:
            Expiry timestamp (Unix timestamp)
        """
        if not self._redis:
            raise RuntimeError("Lease tracker not started")

        duration = duration or settings.lease_duration
        expiry = time.time() + duration

        # Store subscriber info
        key = f"{LEASE_PREFIX}{node_id}"
        await asyncio.to_thread(self._redis.hset, key, mapping={
            "node_id": node_id,
            "transport": transport,
            "chain_id": chain_id,
            "expiry": str(expiry)
        })
        await asyncio.to_thread(self._redis.expire, key, duration + 60)  # Keep key a bit longer than lease

        # Add to subscribers set
        await asyncio.to_thread(self._redis.sadd, LEASE_SET, node_id)

        logger.info(f"Registered subscriber {node_id} with transport={transport}, expiry={expiry}")
        return expiry

    async def extend_lease(self, node_id: str, duration: int | None = None) -> float:
        """Extend a subscriber's lease.

        Args:
            node_id: Subscriber node ID
            duration: Additional duration in seconds (defaults to settings.lease_duration)

        Returns:
            New expiry timestamp
        """
        if not self._redis:
            raise RuntimeError("Lease tracker not started")

        key = f"{LEASE_PREFIX}{node_id}"
        exists = await asyncio.to_thread(self._redis.exists, key)

        if not exists:
            logger.warning(f"Cannot extend lease for unknown subscriber {node_id}")
            return 0.0

        duration = duration or settings.lease_duration
        new_expiry = time.time() + duration

        await asyncio.to_thread(self._redis.hset, key, "expiry", str(new_expiry))
        await asyncio.to_thread(self._redis.expire, key, duration + 60)

        logger.info(f"Extended lease for {node_id} to {new_expiry}")
        return new_expiry

    async def get_lease_expiry(self, node_id: str) -> float:
        """Get the current lease expiry for a subscriber.

        Args:
            node_id: Subscriber node ID

        Returns:
            Expiry timestamp (0 if not found or expired)
        """
        if not self._redis:
            return 0.0

        key = f"{LEASE_PREFIX}{node_id}"
        expiry_str = await asyncio.to_thread(self._redis.hget, key, "expiry")

        if not expiry_str:
            return 0.0

        expiry = float(expiry_str)
        if expiry < time.time():
            # Lease expired
            await self.revoke_lease(node_id)
            return 0.0

        return expiry

    async def revoke_lease(self, node_id: str) -> bool:
        """Revoke a subscriber's lease.

        Args:
            node_id: Subscriber node ID

        Returns:
            True if revoked, False if not found
        """
        if not self._redis:
            return False

        key = f"{LEASE_PREFIX}{node_id}"
        result = await asyncio.to_thread(self._redis.delete, key)
        await asyncio.to_thread(self._redis.srem, LEASE_SET, node_id)

        if result:
            logger.info(f"Revoked lease for {node_id}")
            return True
        return False

    async def get_valid_subscribers(self, chain_id: str | None = None) -> list[SubscriberInfo]:
        """Get all subscribers with valid (non-expired) leases.

        Args:
            chain_id: Optional filter by chain ID

        Returns:
            List of subscriber info
        """
        if not self._redis:
            return []

        now = time.time()
        subscribers = []

        # Get all subscriber IDs
        node_ids = await asyncio.to_thread(self._redis.smembers, LEASE_SET)

        for node_id in node_ids:
            key = f"{LEASE_PREFIX}{node_id}"
            data = await asyncio.to_thread(self._redis.hgetall, key)

            if not data:
                continue

            expiry = float(data.get("expiry", 0))
            if expiry < now:
                # Expired, clean up
                await self.revoke_lease(node_id)
                continue

            # Filter by chain ID if specified
            if chain_id and data.get("chain_id") != chain_id:
                continue

            subscribers.append(SubscriberInfo(
                node_id=data["node_id"],
                transport=data["transport"],
                expiry=expiry,
                chain_id=data["chain_id"]
            ))

        return subscribers

    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired leases."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Run every minute
                await self.cleanup_expired_leases()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Lease cleanup error: {e}")

    async def cleanup_expired_leases(self) -> int:
        """Clean up expired leases.

        Returns:
            Number of leases cleaned up
        """
        if not self._redis:
            return 0

        now = time.time()
        cleaned = 0

        node_ids = await asyncio.to_thread(self._redis.smembers, LEASE_SET)

        for node_id in node_ids:
            key = f"{LEASE_PREFIX}{node_id}"
            expiry_str = await asyncio.to_thread(self._redis.hget, key, "expiry")

            if not expiry_str:
                await self.revoke_lease(node_id)
                cleaned += 1
                continue

            expiry = float(expiry_str)
            if expiry < now:
                await self.revoke_lease(node_id)
                cleaned += 1

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} expired leases")

        return cleaned


# Global instance
lease_tracker = LeaseTracker()
