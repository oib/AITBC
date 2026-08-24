from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network import AITBCHTTPClient

logger = get_logger(__name__)
router = APIRouter(tags=["blockchain"])


def _rpc_get(path: str, *, timeout: float = 5.0) -> dict[str, Any]:
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
        raise HTTPException(status_code=502, detail="Blockchain RPC unavailable") from e


@router.get("/status")
async def blockchain_status() -> dict[str, Any]:
    """Get blockchain status."""
    try:
        from ....config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{rpc_url}/rpc/head")
        return {
            "status": "connected",
            "height": response.get("height", 0),
            "hash": response.get("hash", ""),
            "timestamp": response.get("timestamp", ""),
            "tx_count": response.get("tx_count", 0),
        }
    except NetworkError:
        return {"status": "synced", "block": 0, "proposer": "genesis", "note": "RPC unavailable - returning mock data"}
    except Exception:
        return {"status": "error", "error": "Failed to get blockchain status"}


@router.get("/sync-status")
async def blockchain_sync_status() -> dict[str, Any]:
    """Get blockchain synchronization status."""
    try:
        from ....config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{rpc_url}/rpc/syncStatus")
        if response.get("syncing", False):
            return {
                "status": "syncing",
                "current_block": response.get("current_block", 0),
                "highest_block": response.get("highest_block", 0),
            }
        else:
            return {"status": "synced", "block": response.get("current_block", 0)}
    except NetworkError as e:
        logger.error("RPC connection failed: %s", e)
        return {"status": "error", "error": "RPC connection failed"}
    except Exception:
        return {"status": "error", "error": "Failed to get sync status"}


@router.get("/blocks/{height}")
async def get_block(height: int) -> dict[str, Any]:
    """Get block by height."""
    return _rpc_get(f"/rpc/blocks/{height}")


@router.get("/blocks/hash/{block_hash}")
async def get_block_by_hash(block_hash: str) -> dict[str, Any]:
    """Get block by hash."""
    return _rpc_get(f"/rpc/blocks/hash/{block_hash}")


@router.get("/transactions/{tx_hash}")
async def get_transaction(tx_hash: str) -> dict[str, Any]:
    """Get transaction by hash."""
    try:
        from ....config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{rpc_url}/rpc/transaction/{tx_hash}")
        return response
    except NetworkError as e:
        logger.error("RPC connection failed: %s", e)
        return {"status": "error", "error": "RPC connection failed"}


@router.get("/accounts/{address}")
async def get_account(address: str) -> dict[str, Any]:
    """Get account balance and state."""
    try:
        from ....config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{rpc_url}/rpc/accounts/{address}")
        return response
    except NetworkError as e:
        logger.error("RPC connection failed: %s", e)
        return {"status": "error", "error": "RPC connection failed"}


@router.get("/validators")
async def get_validators() -> dict[str, Any]:
    """List validators."""
    try:
        from ....config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{rpc_url}/rpc/head")
        proposer = response.get("proposer", "genesis")
        return {"validators": [{"address": proposer, "status": "active"}], "total": 1}
    except NetworkError as e:
        logger.error("RPC connection failed: %s", e)
        return {"status": "error", "error": "RPC connection failed"}
    except Exception as e:
        logger.error("Failed to get validators: %s", e)
        return {"status": "error", "error": str(e)}


@router.get("/supply")
async def get_supply() -> dict[str, Any]:
    """Get token supply."""
    try:
        from ....config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{rpc_url}/rpc/genesis_allocations")
        allocations = response.get("allocations", [])
        total_supply = sum(alloc.get("balance", 0) for alloc in allocations)
        return {"total_supply": total_supply, "circulating_supply": total_supply, "unit": "AIT"}
    except NetworkError as e:
        logger.error("RPC connection failed: %s", e)
        return {"status": "error", "error": "RPC connection failed"}


@router.get("/state/dump")
async def get_state_dump() -> dict[str, Any]:
    """Get state dump."""
    try:
        from ....config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{rpc_url}/rpc/blocks-range?start=0&end=10")
        return {"state": response, "timestamp": response.get("timestamp", "")}
    except NetworkError as e:
        logger.error("RPC connection failed: %s", e)
        return {"status": "error", "error": "RPC connection failed"}
