"""Edge database operations router for Edge API Service"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..services.database_service import DatabaseService

router = APIRouter()
db_service = DatabaseService()


@router.post("/init")
async def init_edge_database(island_id: str = Query(...), capacity_gb: int = Query(..., ge=1)):
    """Initialize edge database for an island"""
    result = await db_service.init_edge_database(island_id, capacity_gb)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.get("/")
async def get_edge_database(island_id: Optional[str] = Query(None), database_id: Optional[str] = Query(None)):
    """Get edge database status by island_id or database_id"""
    if database_id:
        result = await db_service.get_edge_database_by_id(database_id)
    elif island_id:
        result = await db_service.get_edge_database(island_id)
    else:
        # List all databases if no filter provided
        return {"databases": await db_service.list_all_databases()}

    if result is None:
        raise HTTPException(status_code=404, detail="Database not found")
    return result


@router.delete("/")
async def delete_edge_database(database_id: str = Query(...)):
    """Delete edge database by database_id"""
    result = await db_service.delete_edge_database(database_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result


@router.post("/sync")
async def sync_edge_database(database_id: str = Query(...)):
    """Sync edge database to main network"""
    result = await db_service.sync_edge_database(database_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result
