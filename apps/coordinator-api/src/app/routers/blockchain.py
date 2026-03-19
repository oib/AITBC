from __future__ import annotations

from fastapi import APIRouter, HTTPException
from aitbc.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["blockchain"])


@router.get("/status")
async def blockchain_status():
    """Get blockchain status."""
    try:
        import httpx
        from ..config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip('/')
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{rpc_url}/rpc/head", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "connected",
                    "height": data.get("height", 0),
                    "hash": data.get("hash", ""),
                    "timestamp": data.get("timestamp", ""),
                    "tx_count": data.get("tx_count", 0)
                }
            else:
                return {
                    "status": "error",
                    "error": f"RPC returned {response.status_code}"
                }
    except Exception as e:
        logger.error(f"Blockchain status error: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/sync-status")
async def blockchain_sync_status():
    """Get blockchain synchronization status."""
    try:
        import httpx
        from ..config import settings

        rpc_url = settings.blockchain_rpc_url.rstrip('/')
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{rpc_url}/rpc/sync", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "syncing" if data.get("syncing", False) else "synced",
                    "current_height": data.get("current_height", 0),
                    "target_height": data.get("target_height", 0),
                    "sync_percentage": data.get("sync_percentage", 100.0),
                    "last_block": data.get("last_block", {})
                }
            else:
                return {
                    "status": "error",
                    "error": f"RPC returned {response.status_code}",
                    "syncing": False,
                    "current_height": 0,
                    "target_height": 0,
                    "sync_percentage": 0.0
                }
    except Exception as e:
        logger.error(f"Blockchain sync status error: {e}")
        return {
            "status": "error",
            "error": str(e),
            "syncing": False,
            "current_height": 0,
            "target_height": 0,
            "sync_percentage": 0.0
        }
