"""
Subscription router.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from aitbc.rate_limiting import rate_limit

from .. import peer_keys
from ..escrow_routes import verify_rpc_peer_key
from ..subscription import (
    get_lease_status,
    get_subscribers,
    heartbeat,
    register_subscription,
    revoke_subscription,
)

router = APIRouter(tags=["subscription"])


def _enforce_key_node_binding(api_key: str, node_id: str) -> None:
    """Issued join keys may only manage their own node_id's lease.

    Keys from ``BLOCKCHAIN_RPC_API_KEY_PEERS`` are fleet-internal and unbound.
    """
    if peer_keys.is_issued_key(api_key) and peer_keys.peer_key_node_scope(api_key) != node_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Issued peer key is bound to a different node_id",
        )


@router.post("/join", summary="Self-serve island join: issue a node-bound peer key")
@rate_limit(rate=5, per=3600, error_message="Join rate limit exceeded — try again later")
async def join_route(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Issue a peer key bound to the caller's node_id.

    The key is returned once and only its hash is stored; it authorizes
    /rpc/subscribe, /rpc/heartbeat and /rpc/lease/{node_id} for that node_id
    only. Chain config files are served separately at /agent/bootstrap.env
    and /agent/genesis.json.
    """
    client_ip = request.client.host if request.client else "unknown"
    node_id = str(body.get("node_id") or "").strip()
    contact = str(body.get("contact") or "").strip() or None

    if not peer_keys.valid_node_id(node_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="node_id must match ^[a-zA-Z0-9][a-zA-Z0-9._-]{2,63}$",
        )
    if peer_keys.node_id_taken(node_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="node_id already enrolled — contact the operator to re-issue",
        )
    if peer_keys.recent_count_for_ip(client_ip) >= peer_keys.MAX_KEYS_PER_IP_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many keys issued for this address today",
        )
    if peer_keys.total_count() >= peer_keys.MAX_TOTAL_KEYS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Island join capacity reached — contact the operator",
        )

    key = peer_keys.issue(node_id, client_ip, contact)

    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.hostname
    base_url = f"{proto}://{host}"
    return {
        "node_id": node_id,
        "peer_key": key,
        "env_snippet": f"BLOCKCHAIN_RPC_API_KEY={key}",
        "bootstrap_env_url": f"{base_url}/agent/bootstrap.env",
        "genesis_json_url": f"{base_url}/agent/genesis.json",
        "subscribe_url": f"{base_url}/rpc/subscribe",
        "note": "The peer key is shown once and bound to this node_id; store it in the node's env.",
    }


@router.post("/subscribe", summary="Register for block subscription with lease")
@rate_limit(rate=10, per=60)
async def register_subscription_route(
    request: Request, body: dict[str, Any], api_key: str = Depends(verify_rpc_peer_key)
) -> dict[str, Any]:
    """Register a follower node for block subscription with a lease"""
    client_ip = request.client.host if request.client else "unknown"
    body["_client_ip"] = client_ip
    _enforce_key_node_binding(api_key, str(body.get("node_id") or ""))
    return await register_subscription(body)


@router.post("/heartbeat", summary="Extend subscription lease via heartbeat")
@rate_limit(rate=60, per=60)
async def heartbeat_route(
    request: Request, body: dict[str, Any], api_key: str = Depends(verify_rpc_peer_key)
) -> dict[str, Any]:
    """Extend a subscriber's lease via heartbeat"""
    client_ip = request.client.host if request.client else "unknown"
    body["_client_ip"] = client_ip
    _enforce_key_node_binding(api_key, str(body.get("node_id") or ""))
    return await heartbeat(body)


@router.get("/lease/{node_id}", summary="Get lease status for a subscriber")
@rate_limit(rate=100, per=60)
async def lease_status_route(request: Request, node_id: str) -> dict[str, Any]:  # noqa: ARG001
    """Check the lease status for a subscriber"""
    return await get_lease_status(node_id)


@router.delete("/lease/{node_id}", summary="Revoke subscription lease")
@rate_limit(rate=10, per=60)
async def revoke_lease_route(request: Request, node_id: str, api_key: str = Depends(verify_rpc_peer_key)) -> dict[str, Any]:  # noqa: ARG001
    """Revoke a subscriber's lease"""
    _enforce_key_node_binding(api_key, node_id)
    return await revoke_subscription(node_id)


@router.get("/subscribers", summary="Get all valid subscribers")
@rate_limit(rate=100, per=60)
async def subscribers_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:  # noqa: ARG001
    """Get all subscribers with valid leases"""
    return await get_subscribers(chain_id)
