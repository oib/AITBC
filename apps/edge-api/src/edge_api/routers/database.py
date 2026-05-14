"""Edge database operations router for Edge API Service"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..services.database_service import DatabaseService

router = APIRouter()


class InitDatabaseRequest(BaseModel):
    """Request model for initializing a database"""
    db_name: str
    db_type: str = Field(default="postgresql")
    config: dict = Field(default_factory=dict)


class SyncDatabaseRequest(BaseModel):
    """Request model for syncing a database"""
    source_url: str = Field(default=None)


def get_database_service() -> DatabaseService:
    """Dependency injection for database service"""
    return DatabaseService()


@router.post("/init")
async def init_database(request: InitDatabaseRequest, svc: DatabaseService = Depends(get_database_service)):
    """Initialize edge database"""
    result = await svc.init_database(request.db_name, request.db_type, request.config)
    return result


@router.get("/{db_id}")
async def get_database(db_id: str, svc: DatabaseService = Depends(get_database_service)):
    """Get database details"""
    db = await svc.get_database(db_id)
    if db is None:
        raise HTTPException(status_code=404, detail=f"Database {db_id} not found")
    return db


@router.delete("/{db_id}")
async def delete_database(db_id: str, svc: DatabaseService = Depends(get_database_service)):
    """Delete database"""
    success = await svc.delete_database(db_id)
    if success:
        return {"message": f"Database {db_id} deleted"}
    else:
        raise HTTPException(status_code=404, detail=f"Database {db_id} not found")


@router.post("/{db_id}/sync")
async def sync_database(db_id: str, request: SyncDatabaseRequest, svc: DatabaseService = Depends(get_database_service)):
    """Sync database from source"""
    result = await svc.sync_database(db_id, request.source_url)
    return result
