import os
from typing import Any

from sqlmodel import delete, select

from ..schemas.database import EdgeDatabase
from ..storage import get_session

# V23-17: there is no sync implementation behind this service. sync_database used to set
# last_sync_at to now, advance records_synced by a literal 100 and answer
# {"success": True} -- committing the fiction to the database, where monitoring, schedulers
# and operators read last_sync_at to decide whether a replica is current. The counter
# climbing by 100 a call also made it look like progress.
#
# Nothing is written in either mode now. A database must not hold fabricated sync state, so
# this flag controls only whether the endpoint refuses or returns a labelled placeholder;
# it does not re-enable the writes.
ALLOW_SIMULATED_SYNC = os.getenv("EDGE_ALLOW_SIMULATED_SYNC", "false").lower() == "true"

SYNC_NOT_IMPLEMENTED = (
    "Edge database sync is not implemented. This endpoint previously reported success, "
    "advanced records_synced by a fixed 100 and stamped last_sync_at, without moving any "
    "data. Set EDGE_ALLOW_SIMULATED_SYNC=true to receive a labelled placeholder response; "
    "no sync state is written to the database in either mode."
)


class SyncNotImplementedError(NotImplementedError):
    """Raised when a sync is requested and there is no sync implementation to run."""


class DatabaseService:
    """Service for edge database operations"""

    async def init_database(self, database_id: str, island_id: str, capacity_gb: int) -> dict[str, Any]:
        """Initialize edge database"""
        async with get_session() as session:
            # Check if database already exists
            result = await session.execute(select(EdgeDatabase).where(EdgeDatabase.database_id == database_id))
            existing_db = result.scalar_one_or_none()

            if existing_db:
                return {
                    "success": False,
                    "message": f"Database {database_id} already exists",
                    "database": existing_db.database_id,
                }

            # Create new database record
            db = EdgeDatabase(
                database_id=database_id,
                island_id=island_id,
                capacity_gb=capacity_gb,
                used_gb=0,
                status="initialized",
                sync_status="idle",
                records_synced=0,
            )
            session.add(db)
            await session.commit()

            return {"success": True, "message": f"Database {database_id} initialized", "database": database_id, "id": db.id}

    async def get_database(self, database_id: str) -> dict[str, Any] | None:
        """Get database details"""
        async with get_session() as session:
            result = await session.execute(select(EdgeDatabase).where(EdgeDatabase.database_id == database_id))
            db = result.scalar_one_or_none()

            if db:
                return {
                    "id": db.id,
                    "database_id": db.database_id,
                    "island_id": db.island_id,
                    "capacity_gb": db.capacity_gb,
                    "used_gb": db.used_gb,
                    "status": db.status,
                    "created_at": db.created_at.isoformat() if db.created_at else None,
                    "updated_at": db.updated_at.isoformat() if db.updated_at else None,
                    "last_sync_at": db.last_sync_at.isoformat() if db.last_sync_at else None,
                    "sync_status": db.sync_status,
                    "records_synced": db.records_synced,
                    "extra_data": db.extra_data,
                }
            return None

    async def delete_database(self, database_id: str) -> bool:
        """Delete database"""
        async with get_session() as session:
            stmt = delete(EdgeDatabase).where(EdgeDatabase.database_id == database_id)  # type: ignore[arg-type]
            result = await session.execute(stmt)
            await session.commit()
            return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    async def sync_database(self, database_id: str) -> dict[str, Any]:
        """Sync a database from its source. Not implemented — see ``SYNC_NOT_IMPLEMENTED``.

        Raises:
            SyncNotImplementedError: Unless ``EDGE_ALLOW_SIMULATED_SYNC`` is set, in which
                case a labelled placeholder is returned instead. No sync state is written
                to the database in either case.
        """
        async with get_session() as session:
            result = await session.execute(select(EdgeDatabase).where(EdgeDatabase.database_id == database_id))
            db = result.scalar_one_or_none()

            if not db:
                return {"success": False, "message": f"Database {database_id} not found"}

            if not ALLOW_SIMULATED_SYNC:
                raise SyncNotImplementedError(SYNC_NOT_IMPLEMENTED)

            # Report what a sync would have claimed without recording it. last_sync_at and
            # records_synced are returned unchanged and uncommitted, so nothing reading
            # this database can mistake the call for a completed sync.
            return {
                "success": True,
                "simulated": True,
                "message": f"Simulated sync for {database_id}: no data was transferred",
                "notice": SYNC_NOT_IMPLEMENTED,
                "records_synced": db.records_synced,
                "last_sync_at": db.last_sync_at.isoformat() if db.last_sync_at else None,
            }

    async def list_databases(self, island_id: str | None = None) -> list[dict[str, Any]]:
        """List databases, optionally filtered by island_id"""
        async with get_session() as session:
            if island_id:
                result = await session.execute(select(EdgeDatabase).where(EdgeDatabase.island_id == island_id))
            else:
                result = await session.execute(select(EdgeDatabase))
            databases = result.scalars().all()

            return [
                {
                    "id": db.id,
                    "database_id": db.database_id,
                    "island_id": db.island_id,
                    "capacity_gb": db.capacity_gb,
                    "used_gb": db.used_gb,
                    "status": db.status,
                    "sync_status": db.sync_status,
                    "records_synced": db.records_synced,
                    "created_at": db.created_at.isoformat() if db.created_at else None,
                }
                for db in databases
            ]
