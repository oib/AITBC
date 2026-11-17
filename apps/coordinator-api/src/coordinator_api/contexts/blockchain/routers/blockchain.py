from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import AITBCError, NetworkError
from aitbc.network import AITBCHTTPClient
from aitbc.utils.units import UNITS_PER_AIT, units_to_ait

logger = get_logger(__name__)
router = APIRouter(tags=["blockchain"])

# Expected failure surface for the status/sync/validators endpoints:
# filesystem/JSON, data-shape, runtime, the lazy config import, and the
# aitbc error hierarchy (AITBCHTTPClient re-raises RateLimitError /
# CircuitBreakerOpenError unwrapped). BaseExceptions still propagate.
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
    AITBCError,
)


def _rpc_get(path: str, *, timeout: float = 5.0, unavailable_status: int = 502) -> dict[str, Any]:
    """GET ``path`` on the blockchain node and translate its failures into HTTP ones.

    Two things this fixes for the routes below. The config import is
    ``....config`` -- ``coordinator_api.config`` -- not ``..config``, which names
    a module that does not exist. The resulting ImportError sailed past the
    ``except NetworkError`` handler, so these endpoints answered 500 instead of
    returning anything at all.

    And a node that does not have a height or a hash answers 404. That is an
    answer, not an outage. The previous shape folded it into the same
    "RPC connection failed" body used for a node that is down, and returned both
    with status 200 -- so a caller could not tell a missing block from a dead
    chain, and neither one looked like an error.
    ``unavailable_status`` selects the code for a dead/unreachable node: 502
    for the block routes (upstream bad gateway) or 503 for the read routes,
    matching the ``/status`` and ``/supply`` convention (#2172).
    """
    from ....config import settings

    rpc_url = settings.blockchain_rpc_url.rstrip("/")
    client = AITBCHTTPClient(timeout=timeout)
    try:
        return client.get(f"{rpc_url}{path}")
    except NetworkError as e:
        # AITBCHTTPClient wraps the requests HTTPError, so the node's status code
        # survives on the cause. RetryPolicy re-raises 4xx without retrying.
        response = getattr(e.__cause__, "response", None)
        if getattr(response, "status_code", None) == 404:
            raise HTTPException(status_code=404, detail="Not found on the blockchain node") from e
        logger.error("RPC request to %s failed: %s", path, e)
        raise HTTPException(status_code=unavailable_status, detail="Blockchain RPC unavailable") from e


@router.get("/status")
def blockchain_status() -> dict[str, Any]:
    """Get blockchain status.

    A dead RPC node is an honest 503 — the previous fallback returned
    ``{"status": "synced", ...}`` mock data with HTTP 200, so a down chain
    looked healthy (#2170).
    """
    try:
        from ....config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{rpc_url}/rpc/head")
    except NetworkError as e:
        logger.error("RPC connection failed: %s", e)
        raise HTTPException(status_code=503, detail="Blockchain RPC unavailable") from e
    except _OPS_ERRORS as e:
        logger.error("Failed to get blockchain status: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get blockchain status") from e
    return {
        "status": "connected",
        "height": response.get("height", 0),
        "hash": response.get("hash", ""),
        "timestamp": response.get("timestamp", ""),
        "tx_count": response.get("tx_count", 0),
    }


@router.get("/sync-status")
def blockchain_sync_status() -> dict[str, Any]:
    """Get blockchain synchronization status.

    An unreachable node is an honest 503 like ``/status`` and ``/supply`` —
    never a 200 ``{"status": "error"}`` body a caller cannot distinguish from
    a real answer (#2172).
    """
    response = _rpc_get("/rpc/syncStatus", unavailable_status=503)
    if response.get("syncing", False):
        return {
            "status": "syncing",
            "current_block": response.get("current_block", 0),
            "highest_block": response.get("highest_block", 0),
        }
    return {"status": "synced", "block": response.get("current_block", 0)}


@router.get("/blocks/{height}")
def get_block(height: int) -> dict[str, Any]:
    """Get block by height."""
    return _rpc_get(f"/rpc/blocks/{height}")


@router.get("/blocks/hash/{block_hash}")
def get_block_by_hash(block_hash: str) -> dict[str, Any]:
    """Get block by hash."""
    return _rpc_get(f"/rpc/blocks/hash/{block_hash}")


@router.get("/transactions/{tx_hash}")
def get_transaction(tx_hash: str) -> dict[str, Any]:
    """Get transaction by hash."""
    return _rpc_get(f"/rpc/transaction/{tx_hash}", unavailable_status=503)


@router.get("/accounts/{address}")
def get_account(address: str) -> dict[str, Any]:
    """Get account balance and state."""
    return _rpc_get(f"/rpc/accounts/{address}", unavailable_status=503)


@router.get("/validators")
def get_validators() -> dict[str, Any]:
    """List consensus validators.

    Proxies the node's real ``/rpc/consensus/validators`` (address, stake,
    reputation, role, is_active, last_proposed) — the previous shape invented
    a single ``{"address": proposer, "status": "active"}`` entry from
    ``/rpc/head``, which flatly misreported the PBFT validator set (#2175).
    ``total`` is now the honest count of returned validators; the upstream
    ``chain_id``/``multi_validator_enabled`` flags pass through.
    """
    response = _rpc_get("/rpc/consensus/validators", unavailable_status=503)
    validators = response.get("validators") or []
    return {**response, "validators": validators, "total": len(validators)}


@router.get("/supply")
def get_supply() -> dict[str, Any]:
    """Get token supply.

    ``total_supply`` stays genesis-derived (``total_supply_basis``), while
    ``circulating_supply`` is the node's live aggregate over the committed
    account table (``/rpc/supply``; ``basis: live_accounts``) — net of fee
    burns by omission and of bond slashes via the bond-burn row. A dead node
    is an honest 503, not a stale-looking genesis number standing in for the
    live one. AIT values are decimal strings; the ``*_units`` fields carry
    the raw base-unit integers (``units_per_ait`` per AIT). A node that
    answers 200 with a malformed payload gets the same honest-503
    treatment as a dead node — never a KeyError 500.
    """
    try:
        from ....config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0, api_key=settings.blockchain_rpc_api_key)
        genesis = client.get(f"{rpc_url}/rpc/genesis_allocations")
        live = client.get(f"{rpc_url}/rpc/supply")
    except NetworkError as e:
        logger.error("RPC request failed: %s", e)
        raise HTTPException(status_code=503, detail="Blockchain RPC unavailable") from e
    total_units = sum(alloc.get("balance", 0) for alloc in genesis.get("allocations", []))
    try:
        return {
            "total_supply": format(units_to_ait(total_units).normalize(), "f"),
            "total_supply_units": total_units,
            "total_supply_basis": "genesis_allocations",
            "circulating_supply": live["circulating_ait"],
            "circulating_supply_units": live["circulating_units"],
            "bond_burned_units": live["bond_burned_units"],
            "height": live["height"],
            "unit": "AIT",
            "units_per_ait": UNITS_PER_AIT,
            "basis": "live_accounts",
        }
    except KeyError as e:
        logger.error("malformed /rpc/supply payload (missing %s): %r", e, live)
        raise HTTPException(
            status_code=503,
            detail="Blockchain RPC returned a malformed /rpc/supply payload",
        ) from e


@router.get("/state/dump")
def get_state_dump() -> dict[str, Any]:
    """Get state dump."""
    response = _rpc_get("/rpc/blocks-range?start=0&end=10", unavailable_status=503)
    return {"state": response, "timestamp": response.get("timestamp", "")}
