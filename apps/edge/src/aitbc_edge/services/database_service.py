from datetime import datetime
from typing import Any

from sqlmodel import delete, select

from ..schemas.database import EdgeDatabase
from ..storage import get_session


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
                    "database": existing_db.database_id
                }

            # Create new database record
            db = EdgeDatabase(
                database_id=database_id,
                island_id=island_id,
                capacity_gb=capacity_gb,
                used_gb=0,
                status="initialized",
                sync_status="idle",
                records_synced=0
            )
            session.add(db)
            await session.commit()

            return {
                "success": True,
                "message": f"Database {database_id} initialized",
                "database": database_id,
                "id": db.id
            }

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
                    "extra_data": db.extra_data
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
        """Sync database from source"""
        async with get_session() as session:
            result = await session.execute(select(EdgeDatabase).where(EdgeDatabase.database_id == database_id))
            db = result.scalar_one_or_none()

            if not db:
                return {
                    "success": False,
                    "message": f"Database {database_id} not found"
                }

            # Update sync status in single transaction
            db.sync_status = "syncing"
            db.updated_at = datetime.utcnow()

            # Simulate sync process (in production, this would actually sync data)
            db.sync_status = "idle"
            db.last_sync_at = datetime.utcnow()
            db.records_synced = db.records_synced + 100  # Simulated
            db.updated_at = datetime.utcnow()

            await session.commit()

            return {
                "success": True,
                "message": f"Database {database_id} synced",
                "records_synced": db.records_synced
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
                    "created_at": db.created_at.isoformat() if db.created_at else None
                }
                for db in databases
            ]
