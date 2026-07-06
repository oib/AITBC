"""
Subscription router.
"""

from typing import Any
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request

from aitbc.rate_limiting import rate_limit

from ...logger import get_logger

_logger = get_logger(__name__)

router = APIRouter(tags=["subscription"])

# Optional imports - will be None if module not available
get_lease_status: Callable[..., Any] | None = None
get_subscribers: Callable[..., Any] | None = None
heartbeat: Callable[..., Any] | None = None
register_subscription: Callable[..., Any] | None = None
revoke_subscription: Callable[..., Any] | None = None

try:
    from ..subscription import (
        get_lease_status,
        get_subscribers,
        heartbeat,
        register_subscription,
        revoke_subscription,
    )
except ImportError as e:
    _logger.error("Subscription module not available: %s — affected endpoints will return 503", e)


@router.post("/subscribe", summary="Register for block subscription with lease")
@rate_limit(rate=10, per=60)
async def register_subscription_route(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Register a follower node for block subscription with a lease"""
    if register_subscription is None:
        raise HTTPException(status_code=503, detail="Subscription module not available")
    client_ip = request.client.host if request.client else "unknown"
    body["_client_ip"] = client_ip
    return await register_subscription(body)  # type: ignore[no-any-return]


@router.post("/heartbeat", summary="Extend subscription lease via heartbeat")
@rate_limit(rate=60, per=60)
async def heartbeat_route(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Extend a subscriber's lease via heartbeat"""
    if heartbeat is None:
        raise HTTPException(status_code=503, detail="Subscription module not available")
    client_ip = request.client.host if request.client else "unknown"
    body["_client_ip"] = client_ip
    return await heartbeat(body)  # type: ignore[no-any-return]


@router.get("/lease/{node_id}", summary="Get lease status for a subscriber")
@rate_limit(rate=100, per=60)
async def lease_status_route(node_id: str) -> dict[str, Any]:
    """Check the lease status for a subscriber"""
    if get_lease_status is None:
        raise HTTPException(status_code=503, detail="Subscription module not available")
    return await get_lease_status(node_id)  # type: ignore[no-any-return]


@router.delete("/lease/{node_id}", summary="Revoke subscription lease")
@rate_limit(rate=10, per=60)
async def revoke_lease_route(node_id: str) -> dict[str, Any]:
    """Revoke a subscriber's lease"""
    if revoke_subscription is None:
        raise HTTPException(status_code=503, detail="Subscription module not available")
    return await revoke_subscription(node_id)  # type: ignore[no-any-return]


@router.get("/subscribers", summary="Get all valid subscribers")
@rate_limit(rate=100, per=60)
async def subscribers_route(chain_id: str | None = None) -> dict[str, Any]:
    """Get all subscribers with valid leases"""
    if get_subscribers is None:
        raise HTTPException(status_code=503, detail="Subscription module not available")
    return await get_subscribers(chain_id)  # type: ignore[no-any-return]
