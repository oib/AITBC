"""Redis-based lease tracker for block subscription system."""

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import redis

from .config import settings


def _fmt_expiry(expiry: float) -> str:
    """Format a Unix timestamp as human-readable UTC datetime."""
    return datetime.fromtimestamp(expiry, UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


from aitbc.async_tasks import create_task_with_logging
from .logger import get_logger

logger = get_logger(__name__)
LEASE_PREFIX = "lease:subscriber:"
LEASE_SET = "lease:subscribers"
# A node that follows several chains registers once per chain, so the lease is
# keyed on both. Keying on node_id alone meant the second registration
# overwrote the first and only the last chain ever received blocks.
LEASE_SEPARATOR = "|"


def _decode(value: Any) -> str:
    """Normalise a Redis value to str regardless of decode_responses."""
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _member(node_id: str, chain_id: str) -> str:
    """Build the lease set member identifying one node's lease on one chain."""
    return f"{node_id}{LEASE_SEPARATOR}{chain_id}"


@dataclass
class SubscriberInfo:
    """Information about a subscriber."""

    node_id: str
    transport: str
    expiry: float
    chain_id: str
    client_ip: str = "unknown"


class LeaseTracker:
    """Manages subscriber leases in Redis."""

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url or settings.gossip_broadcast_url
        self._redis: redis.Redis | None = None
        self._running = False
        self._cleanup_task: asyncio.Task[Any] | None = None

    async def start(self) -> None:
        """Start the lease tracker and background cleanup task."""
        if self._running:
            logger.info("Lease tracker already running")
            return
        try:
            logger.info("Starting lease tracker with Redis URL: %s", self._redis_url)
            if self._redis_url and self._redis_url.startswith("redis://"):
                self._redis = redis.from_url(self._redis_url, decode_responses=True)
            else:
                self._redis = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
            logger.info("Redis client created: connected to %s", self._redis_url)
            pong = await asyncio.to_thread(self._redis.ping)
            logger.info("Redis ping successful: %s", pong)
            self._running = True
            self._cleanup_task = create_task_with_logging(self._cleanup_loop(), name="lease_tracker_cleanup")
            logger.info("Lease tracker started successfully")
        except Exception as e:
            logger.error("Failed to start lease tracker: %s", e)
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

    async def _members_for_node(self, node_id: str, chain_id: str | None = None) -> list[str]:
        """Return the lease set members belonging to a node.

        Recognises both the composite "<node_id>|<chain_id>" members written
        since multi-chain support and the bare "<node_id>" members written
        before it, so leases already in Redis keep working until they expire.

        Args:
            node_id: Subscriber node ID
            chain_id: Optional chain ID to narrow to a single lease

        Returns:
            Matching lease set members
        """
        if not self._redis:
            return []
        prefix = f"{node_id}{LEASE_SEPARATOR}"
        members = await asyncio.to_thread(self._redis.smembers, LEASE_SET)
        matched = []
        for raw in members:
            member = _decode(raw)
            if member != node_id and not member.startswith(prefix):
                continue
            if chain_id is not None and not await self._member_matches_chain(member, chain_id):
                continue
            matched.append(member)
        return matched

    async def _member_matches_chain(self, member: str, chain_id: str) -> bool:
        """Check whether a lease set member belongs to a chain."""
        if LEASE_SEPARATOR in member:
            return member.split(LEASE_SEPARATOR, 1)[1] == chain_id
        if not self._redis:
            return False
        # Legacy member: the chain is only recorded inside the hash.
        stored = await asyncio.to_thread(self._redis.hget, f"{LEASE_PREFIX}{member}", "chain_id")
        return stored is not None and _decode(stored) == chain_id

    async def _revoke_member(self, member: str) -> bool:
        """Delete one lease by its lease set member."""
        if not self._redis:
            return False
        result = await asyncio.to_thread(self._redis.delete, f"{LEASE_PREFIX}{member}")
        await asyncio.to_thread(self._redis.srem, LEASE_SET, member)
        if result:
            logger.info("Revoked lease for %s", member)
            return True
        return False

    async def register_subscriber(
        self, node_id: str, transport: str, chain_id: str, duration: int | None = None, client_ip: str = "unknown"
    ) -> float:
        """Register a subscriber with a lease.

        A node holds one lease per chain: registering for a second chain adds a
        lease rather than replacing the first.

        Args:
            node_id: Unique identifier for the subscriber node
            transport: Transport method (websocket, http, redis)
            chain_id: Chain ID for the subscription
            duration: Lease duration in seconds (defaults to settings.lease_duration)
            client_ip: IP address of the subscribing node

        Returns:
            Expiry timestamp (Unix timestamp)
        """
        if not self._redis:
            raise RuntimeError("Lease tracker not started")
        duration = duration or settings.lease_duration
        expiry = time.time() + duration
        member = _member(node_id, chain_id)
        key = f"{LEASE_PREFIX}{member}"
        await asyncio.to_thread(
            self._redis.hset,
            key,
            mapping={
                "node_id": node_id,
                "transport": transport,
                "chain_id": chain_id,
                "expiry": str(expiry),
                "client_ip": client_ip,
            },
        )
        await asyncio.to_thread(self._redis.expire, key, duration + 60)
        await asyncio.to_thread(self._redis.sadd, LEASE_SET, member)
        # Drop any pre-multi-chain lease for this node so the same subscriber is
        # not counted twice while the old key lives out its TTL.
        await asyncio.to_thread(self._redis.delete, f"{LEASE_PREFIX}{node_id}")
        await asyncio.to_thread(self._redis.srem, LEASE_SET, node_id)
        logger.info(
            "Registered subscriber %s (ip=%s) on chain=%s with transport=%s, expiry=%s",
            node_id,
            client_ip,
            chain_id,
            transport,
            _fmt_expiry(expiry),
        )
        return expiry

    async def extend_lease(
        self, node_id: str, duration: int | None = None, client_ip: str = "unknown", chain_id: str | None = None
    ) -> float:
        """Extend a subscriber's lease.

        Args:
            node_id: Subscriber node ID
            duration: Additional duration in seconds (defaults to settings.lease_duration)
            client_ip: IP address of the heartbeat sender
            chain_id: Optional chain ID; when omitted every lease the node holds
                is extended, so heartbeats that carry only a node_id keep working

        Returns:
            New expiry timestamp (0.0 if the node holds no lease)
        """
        if not self._redis:
            raise RuntimeError("Lease tracker not started")
        members = await self._members_for_node(node_id, chain_id)
        if not members:
            logger.warning("Cannot extend lease for unknown subscriber %s (ip=%s)", node_id, client_ip)
            return 0.0
        duration = duration or settings.lease_duration
        new_expiry = time.time() + duration
        extended = 0
        for member in members:
            key = f"{LEASE_PREFIX}{member}"
            if not await asyncio.to_thread(self._redis.exists, key):
                # Set member whose hash has already expired out from under it.
                await asyncio.to_thread(self._redis.srem, LEASE_SET, member)
                continue
            await asyncio.to_thread(self._redis.hset, key, mapping={"expiry": str(new_expiry), "client_ip": client_ip})
            await asyncio.to_thread(self._redis.expire, key, duration + 60)
            extended += 1
        if not extended:
            logger.warning("Cannot extend lease for unknown subscriber %s (ip=%s)", node_id, client_ip)
            return 0.0
        logger.info(
            "Extended lease for %s (ip=%s) on %s chain(s) to %s", node_id, client_ip, extended, _fmt_expiry(new_expiry)
        )
        return new_expiry

    async def get_lease_expiry(self, node_id: str, chain_id: str | None = None) -> float:
        """Get the current lease expiry for a subscriber.

        Args:
            node_id: Subscriber node ID
            chain_id: Optional chain ID; when omitted the latest expiry across
                every chain the node follows is returned

        Returns:
            Expiry timestamp (0 if not found or expired)
        """
        if not self._redis:
            return 0.0
        now = time.time()
        latest = 0.0
        for member in await self._members_for_node(node_id, chain_id):
            expiry_str = await asyncio.to_thread(self._redis.hget, f"{LEASE_PREFIX}{member}", "expiry")
            if not expiry_str:
                continue
            expiry = float(expiry_str)
            if expiry < now:
                await self._revoke_member(member)
                continue
            latest = max(latest, expiry)
        return latest

    async def revoke_lease(self, node_id: str, chain_id: str | None = None) -> bool:
        """Revoke a subscriber's lease.

        Args:
            node_id: Subscriber node ID
            chain_id: Optional chain ID; when omitted every lease the node holds
                is revoked

        Returns:
            True if at least one lease was revoked, False if none was found
        """
        if not self._redis:
            return False
        revoked = False
        for member in await self._members_for_node(node_id, chain_id):
            revoked |= await self._revoke_member(member)
        return revoked

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
        members = await asyncio.to_thread(self._redis.smembers, LEASE_SET)
        for raw in members:
            member = _decode(raw)
            key = f"{LEASE_PREFIX}{member}"
            data = await asyncio.to_thread(self._redis.hgetall, key)
            if not data:
                continue
            expiry = float(data.get("expiry", 0))
            if expiry < now:
                await self._revoke_member(member)
                continue
            if chain_id and data.get("chain_id") != chain_id:
                continue
            subscribers.append(
                SubscriberInfo(
                    node_id=str(data["node_id"]),
                    transport=str(data["transport"]),
                    expiry=expiry,
                    chain_id=str(data["chain_id"]),
                    client_ip=str(data.get("client_ip", "unknown")),
                )
            )
        return subscribers

    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired leases."""
        while self._running:
            try:
                await asyncio.sleep(60)
                await self.cleanup_expired_leases()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Lease cleanup error: %s", e)

    async def cleanup_expired_leases(self) -> int:
        """Clean up expired leases.

        Returns:
            Number of leases cleaned up
        """
        if not self._redis:
            return 0
        now = time.time()
        cleaned = 0
        members = await asyncio.to_thread(self._redis.smembers, LEASE_SET)
        for raw in members:
            member = _decode(raw)
            expiry_str = await asyncio.to_thread(self._redis.hget, f"{LEASE_PREFIX}{member}", "expiry")
            if not expiry_str:
                await self._revoke_member(member)
                cleaned += 1
                continue
            expiry = float(expiry_str)
            if expiry < now:
                await self._revoke_member(member)
                cleaned += 1
        if cleaned > 0:
            logger.info("Cleaned up %s expired leases", cleaned)
        return cleaned


lease_tracker = LeaseTracker()
