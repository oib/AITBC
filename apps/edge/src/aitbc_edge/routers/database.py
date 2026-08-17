"""Database operations router for Edge API Service"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..services.database_service import SYNC_NOT_IMPLEMENTED, DatabaseService, SyncNotImplementedError

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
async def init_database(
    request: InitDatabaseRequest, svc: Annotated[DatabaseService, Depends(get_database_service)]
) -> dict[str, Any]:
    """Initialize edge database"""
    result = await svc.init_database(request.database_id, request.island_id, request.capacity_gb)
    return result


@router.get("/")
async def list_databases(
    svc: Annotated[DatabaseService, Depends(get_database_service)],
    island_id: str | None = None,
) -> dict[str, Any]:
    """List databases, optionally filtered by island_id"""
    databases = await svc.list_databases(island_id)
    return {"databases": databases, "total": len(databases)}


@router.get("/{database_id}")
async def get_database(database_id: str, svc: Annotated[DatabaseService, Depends(get_database_service)]) -> dict[str, Any]:
    """Get database details"""
    db = await svc.get_database(database_id)
    if db is None:
        raise HTTPException(status_code=404, detail=f"Database {database_id} not found")
    return db


@router.delete("/{database_id}")
async def delete_database(database_id: str, svc: Annotated[DatabaseService, Depends(get_database_service)]) -> dict[str, str]:
    """Delete database"""
    success = await svc.delete_database(database_id)
    if success:
        return {"message": f"Database {database_id} deleted"}
    else:
        raise HTTPException(status_code=404, detail=f"Database {database_id} not found")


@router.post("/{database_id}/sync")
async def sync_database(database_id: str, svc: Annotated[DatabaseService, Depends(get_database_service)]) -> dict[str, Any]:
    """Sync database from source. Not implemented — see ``SYNC_NOT_IMPLEMENTED``.

    501 is the honest answer: the route is defined, the functionality is not.
    """
    try:
        return await svc.sync_database(database_id)
    except SyncNotImplementedError as e:
        # The constant, not str(e). tests/security/test_http_exception_hardening.py forbids
        # detail=str(...) on any 5xx: an exception's text is not vetted for what it reveals,
        # and 501 is 5xx. Here the two strings happen to be identical, which is exactly why
        # the blanket rule is the right one -- it does not depend on the reader checking.
        raise HTTPException(status_code=501, detail=SYNC_NOT_IMPLEMENTED) from e
