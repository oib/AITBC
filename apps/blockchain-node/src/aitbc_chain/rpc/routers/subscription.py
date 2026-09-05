"""
Subscription router.
"""

from typing import Any

from fastapi import APIRouter, Request

from aitbc.rate_limiting import rate_limit

from ..subscription import (
    get_lease_status,
    get_subscribers,
    heartbeat,
    register_subscription,
    revoke_subscription,
)

router = APIRouter(tags=["subscription"])


@router.post("/subscribe", summary="Register for block subscription with lease")
@rate_limit(rate=10, per=60)
async def register_subscription_route(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Register a follower node for block subscription with a lease"""
    client_ip = request.client.host if request.client else "unknown"
    body["_client_ip"] = client_ip
    return await register_subscription(body)


@router.post("/heartbeat", summary="Extend subscription lease via heartbeat")
@rate_limit(rate=60, per=60)
async def heartbeat_route(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Extend a subscriber's lease via heartbeat"""
    client_ip = request.client.host if request.client else "unknown"
    body["_client_ip"] = client_ip
    return await heartbeat(body)


@router.get("/lease/{node_id}", summary="Get lease status for a subscriber")
@rate_limit(rate=100, per=60)
async def lease_status_route(node_id: str) -> dict[str, Any]:
    """Check the lease status for a subscriber"""
    return await get_lease_status(node_id)


@router.delete("/lease/{node_id}", summary="Revoke subscription lease")
@rate_limit(rate=10, per=60)
async def revoke_lease_route(node_id: str) -> dict[str, Any]:
    """Revoke a subscriber's lease"""
    return await revoke_subscription(node_id)


@router.get("/subscribers", summary="Get all valid subscribers")
@rate_limit(rate=100, per=60)
async def subscribers_route(chain_id: str | None = None) -> dict[str, Any]:
    """Get all subscribers with valid leases"""
    return await get_subscribers(chain_id)
