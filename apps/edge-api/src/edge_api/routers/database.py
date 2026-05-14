"""Database operations router for Edge API Service"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.database_service import DatabaseService

router = APIRouter()


class InitDatabaseRequest(BaseModel):
    """Request model for initializing a database"""
    database_id: str
    island_id: str
    capacity_gb: int


def get_database_service() -> DatabaseService:
    """Dependency injection for database service"""
    return DatabaseService()


@router.post("/init")
async def init_database(request: InitDatabaseRequest, svc: DatabaseService = Depends(get_database_service)):
    """Initialize edge database"""
    result = await svc.init_database(request.database_id, request.island_id, request.capacity_gb)
    return result


@router.get("/")
async def list_databases(island_id: str = Query(None), svc: DatabaseService = Depends(get_database_service)):
    """List databases, optionally filtered by island_id"""
    databases = await svc.list_databases(island_id)
    return {"databases": databases, "total": len(databases)}


@router.get("/{database_id}")
async def get_database(database_id: str, svc: DatabaseService = Depends(get_database_service)):
    """Get database details"""
    db = await svc.get_database(database_id)
    if db is None:
        raise HTTPException(status_code=404, detail=f"Database {database_id} not found")
    return db


@router.delete("/{database_id}")
async def delete_database(database_id: str, svc: DatabaseService = Depends(get_database_service)):
    """Delete database"""
    success = await svc.delete_database(database_id)
    if success:
        return {"message": f"Database {database_id} deleted"}
    else:
        raise HTTPException(status_code=404, detail=f"Database {database_id} not found")


@router.post("/{database_id}/sync")
async def sync_database(database_id: str, svc: DatabaseService = Depends(get_database_service)):
    """Sync database from source"""
    result = await svc.sync_database(database_id)
    return result
