from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from aitbc import get_logger, AITBCHTTPClient, NetworkError

logger = get_logger(__name__)


router = APIRouter(tags=["blockchain"])


@router.get("/status")
async def blockchain_status() -> dict[str, Any]:
    """Get blockchain status."""
    try:
        from ..config import settings

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
    except NetworkError as e:
        # Return mock data if RPC is unavailable
        return {
            "status": "synced",
            "block": 0,
            "proposer": "genesis",
            "note": "RPC unavailable - returning mock data"
        }
    except Exception as e:
        return {"status": "error", "error": "Failed to get blockchain status"}


@router.get("/sync-status")
async def blockchain_sync_status() -> dict[str, Any]:
    """Get blockchain synchronization status."""
    try:
        from ..config import settings

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
        return {"status": "error", "error": f"RPC connection failed: {e}"}
    except Exception as e:
        return {"status": "error", "error": "Failed to get sync status"}

@router.get("/blocks/{height}")
async def get_block(height: int) -> dict[str, Any]:
    """Get block by height."""
    try:
        from ..config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{rpc_url}/rpc/blocks/{height}")
        return response
    except NetworkError as e:
        return {"status": "error", "error": f"RPC connection failed: {e}"}


@router.get("/blocks/hash/{block_hash}")
async def get_block_by_hash(block_hash: str) -> dict[str, Any]:
    """Get block by hash."""
    try:
        from ..config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{rpc_url}/rpc/blocks/hash/{block_hash}")
        return response
    except NetworkError as e:
        return {"status": "error", "error": f"RPC connection failed: {e}"}


@router.get("/transactions/{tx_hash}")
async def get_transaction(tx_hash: str) -> dict[str, Any]:
    """Get transaction by hash."""
    try:
        from ..config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{rpc_url}/rpc/transactions/{tx_hash}")
        return response
    except NetworkError as e:
        return {"status": "error", "error": f"RPC connection failed: {e}"}


@router.get("/accounts/{address}")
async def get_account(address: str) -> dict[str, Any]:
    """Get account balance and state."""
    try:
        from ..config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        response = client.get(f"{rpc_url}/rpc/accounts/{address}")
        return response
    except NetworkError as e:
        return {"status": "error", "error": f"RPC connection failed: {e}"}


@router.get("/validators")
async def get_validators() -> dict[str, Any]:
    """List validators."""
    try:
        from ..config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        # PoA proposers are the validators
        response = client.get(f"{rpc_url}/rpc/head")
        proposer = response.get("proposer", "genesis")
        return {
            "validators": [{"address": proposer, "status": "active"}],
            "total": 1
        }
    except NetworkError as e:
        return {"status": "error", "error": f"RPC connection failed: {e}"}


@router.get("/supply")
async def get_supply() -> dict[str, Any]:
    """Get token supply."""
    try:
        from ..config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        # Calculate supply from genesis allocations
        response = client.get(f"{rpc_url}/rpc/genesis_allocations")
        allocations = response.get("allocations", [])
        total_supply = sum(alloc.get("balance", 0) for alloc in allocations)
        return {
            "total_supply": total_supply,
            "circulating_supply": total_supply,
            "unit": "AIT"
        }
    except NetworkError as e:
        return {"status": "error", "error": f"RPC connection failed: {e}"}


@router.get("/state/dump")
async def get_state_dump() -> dict[str, Any]:
    """Get state dump."""
    try:
        from ..config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip("/")
        client = AITBCHTTPClient(timeout=5.0)
        # Get recent blocks as state snapshot
        response = client.get(f"{rpc_url}/rpc/blocks-range?start=0&end=10")
        return {
            "state": response,
            "timestamp": response.get("timestamp", "")
        }
    except NetworkError as e:
        return {"status": "error", "error": f"RPC connection failed: {e}"}
