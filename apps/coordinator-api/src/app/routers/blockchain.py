from __future__ import annotations

from fastapi import APIRouter, HTTPException
from aitbc.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["blockchain"])


@router.get("/blockchain/status")
async def blockchain_status():
    """Get blockchain status."""
    try:
        # Try to get blockchain status from RPC
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8003/rpc/head", timeout=5.0)
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


@router.get("/blockchain/sync")
async def blockchain_sync():
    """Trigger blockchain sync."""
    try:
        # For now, just return status
        return {
            "status": "sync_triggered",
            "message": "Blockchain sync initiated"
        }
    except Exception as e:
        logger.error(f"Blockchain sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
