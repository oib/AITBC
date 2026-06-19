"""Subscription RPC endpoints for lease-based block push system."""

from typing import Any

from fastapi import HTTPException

from ..config import settings
from ..lease_tracker import lease_tracker
from ..logger import get_logger

logger = get_logger(__name__)


async def register_subscription(request: dict[str, Any]) -> dict[str, Any]:
    """Register a follower node for block subscription with a lease.

    Request body:
        node_id: str - Unique identifier for the follower node
        transport: str - Transport method (websocket, http, redis)
        chain_id: str - Chain ID to subscribe to
        duration: int (optional) - Lease duration in seconds

    Returns:
        node_id: str
        transport: str
        chain_id: str
        expiry: float - Unix timestamp when lease expires
        lease_duration: int - Actual lease duration granted
    """
    node_id = request.get("node_id")
    transport = request.get("transport", "websocket")
    chain_id = request.get("chain_id", settings.chain_id)
    duration = request.get("duration")
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id is required")
    if transport not in ["websocket", "http", "redis"]:
        raise HTTPException(status_code=400, detail=f"Invalid transport: {transport}")
    logger.info("Subscription request from node_id=%s, lease_tracker._running=%s", node_id, lease_tracker._running)
    try:
        expiry = await lease_tracker.register_subscriber(
            node_id=node_id, transport=transport, chain_id=chain_id, duration=duration
        )
        return {
            "node_id": node_id,
            "transport": transport,
            "chain_id": chain_id,
            "expiry": expiry,
            "lease_duration": duration or settings.lease_duration,
        }
    except Exception as e:
        logger.error("Failed to register subscription: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def heartbeat(request: dict[str, Any]) -> dict[str, Any]:
    """Extend a subscriber's lease via heartbeat.

    Request body:
        node_id: str - Subscriber node ID
        duration: int (optional) - Additional duration in seconds

    Returns:
        node_id: str
        expiry: float - New expiry timestamp
        lease_duration: int - Duration added
    """
    node_id = request.get("node_id")
    duration = request.get("duration")
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id is required")
    try:
        expiry = await lease_tracker.extend_lease(node_id, duration)
        if expiry == 0.0:
            raise HTTPException(status_code=404, detail="Subscriber not found or lease expired")
        return {"node_id": node_id, "expiry": expiry, "lease_duration": duration or settings.lease_duration}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to extend lease: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def get_lease_status(node_id: str) -> dict[str, Any]:
    """Check the lease status for a subscriber.

    Returns:
        node_id: str
        expiry: float - Expiry timestamp (0 if not found/expired)
        valid: bool - Whether lease is currently valid
        remaining_seconds: int - Seconds until expiry (0 if invalid)
    """
    try:
        import time

        expiry = await lease_tracker.get_lease_expiry(node_id)
        now = time.time()
        valid = expiry > now
        remaining = int(expiry - now) if valid else 0
        return {"node_id": node_id, "expiry": expiry, "valid": valid, "remaining_seconds": remaining}
    except Exception as e:
        logger.error("Failed to get lease status: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def revoke_subscription(node_id: str) -> dict[str, Any]:
    """Revoke a subscriber's lease.

    Returns:
        node_id: str
        revoked: bool - Whether lease was revoked
    """
    try:
        revoked = await lease_tracker.revoke_lease(node_id)
        return {"node_id": node_id, "revoked": revoked}
    except Exception as e:
        logger.error("Failed to revoke lease: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


async def get_subscribers(chain_id: str | None = None) -> dict[str, Any]:
    """Get all subscribers with valid leases.

    Query params:
        chain_id: str (optional) - Filter by chain ID

    Returns:
        subscribers: list - List of subscriber info
        count: int - Number of valid subscribers
    """
    try:
        subscribers = await lease_tracker.get_valid_subscribers(chain_id)
        return {
            "subscribers": [
                {"node_id": s.node_id, "transport": s.transport, "chain_id": s.chain_id, "expiry": s.expiry}
                for s in subscribers
            ],
            "count": len(subscribers),
        }
    except Exception as e:
        logger.error("Failed to get subscribers: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
