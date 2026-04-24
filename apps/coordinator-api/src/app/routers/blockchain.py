from __future__ import annotations

from fastapi import APIRouter

from aitbc import get_logger, AITBCHTTPClient, NetworkError

logger = get_logger(__name__)


router = APIRouter(tags=["blockchain"])


@router.get("/status")
async def blockchain_status():
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
        logger.error(f"Blockchain status error: {e}")
        return {"status": "error", "error": f"RPC connection failed: {e}"}


@router.get("/sync-status")
async def blockchain_sync_status():
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
        logger.error(f"Blockchain sync status error: {e}")
        return {"status": "error", "error": f"RPC connection failed: {e}"}
    except Exception as e:
        logger.error(f"Blockchain sync status error: {e}")
        return {"status": "error", "error": "Failed to get sync status"}
