"""Edge database service for Edge API Service"""

from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlmodel import Session

from aitbc import get_logger

from ..schemas.database import EdgeDatabase
from ..storage import get_session

logger = get_logger(__name__)


class DatabaseService:
    """Service for edge database operations"""

    def __init__(self):
        pass

    async def init_edge_database(self, island_id: str, capacity_gb: int) -> Dict:
        """Initialize edge database for an island"""
        async with get_session() as session:
            # Check if database already exists for this island
            existing = await session.execute(
                select(EdgeDatabase).where(EdgeDatabase.island_id == island_id)
            )
            existing_db = existing.first()

            if existing_db:
                return {
                    "success": False,
                    "message": "Database already exists for this island",
                    "database_id": existing_db[0].database_id,
                    "status": existing_db[0].status,
                }

            # Create new edge database
            database_id = f"edge_db_{uuid4().hex[:8]}"
            edge_db = EdgeDatabase(
                database_id=database_id,
                island_id=island_id,
                capacity_gb=capacity_gb,
                used_gb=0,
                status="initialized",
                sync_status="idle",
                records_synced=0,
            )

            session.add(edge_db)
            await session.commit()
            await session.refresh(edge_db)

            logger.info(f"Initialized edge database {database_id} for island {island_id}")

            return {
                "success": True,
                "database_id": edge_db.database_id,
                "island_id": edge_db.island_id,
                "capacity_gb": edge_db.capacity_gb,
                "status": edge_db.status,
                "created_at": edge_db.created_at.isoformat(),
            }

    async def get_edge_database(self, island_id: str) -> Optional[Dict]:
        """Get edge database status for an island"""
        async with get_session() as session:
            result = await session.execute(
                select(EdgeDatabase).where(EdgeDatabase.island_id == island_id)
            )
            edge_db = result.first()

            if not edge_db:
                return None

            db = edge_db[0]
            return {
                "database_id": db.database_id,
                "island_id": db.island_id,
                "capacity_gb": db.capacity_gb,
                "used_gb": db.used_gb,
                "status": db.status,
                "created_at": db.created_at.isoformat(),
                "updated_at": db.updated_at.isoformat(),
                "last_sync_at": db.last_sync_at.isoformat() if db.last_sync_at else None,
                "sync_status": db.sync_status,
                "records_synced": db.records_synced,
                "extra_data": db.extra_data,
            }

    async def get_edge_database_by_id(self, database_id: str) -> Optional[Dict]:
        """Get edge database status by database ID"""
        async with get_session() as session:
            result = await session.execute(
                select(EdgeDatabase).where(EdgeDatabase.database_id == database_id)
            )
            edge_db = result.first()

            if not edge_db:
                return None

            db = edge_db[0]
            return {
                "database_id": db.database_id,
                "island_id": db.island_id,
                "capacity_gb": db.capacity_gb,
                "used_gb": db.used_gb,
                "status": db.status,
                "created_at": db.created_at.isoformat(),
                "updated_at": db.updated_at.isoformat(),
                "last_sync_at": db.last_sync_at.isoformat() if db.last_sync_at else None,
                "sync_status": db.sync_status,
                "records_synced": db.records_synced,
                "extra_data": db.extra_data,
            }

    async def delete_edge_database(self, database_id: str) -> Dict:
        """Delete edge database"""
        async with get_session() as session:
            result = await session.execute(
                select(EdgeDatabase).where(EdgeDatabase.database_id == database_id)
            )
            edge_db = result.first()

            if not edge_db:
                return {
                    "success": False,
                    "message": f"Database {database_id} not found",
                }

            db = edge_db[0]
            await session.delete(db)
            await session.commit()

            logger.info(f"Deleted edge database {database_id}")

            return {
                "success": True,
                "message": f"Database {database_id} deleted successfully",
                "database_id": database_id,
            }

    async def sync_edge_database(self, database_id: str) -> Dict:
        """Sync edge database to main network"""
        async with get_session() as session:
            result = await session.execute(
                select(EdgeDatabase).where(EdgeDatabase.database_id == database_id)
            )
            edge_db = result.first()

            if not edge_db:
                return {
                    "success": False,
                    "message": f"Database {database_id} not found",
                }

            db = edge_db[0]

            # Update sync status
            db.sync_status = "syncing"
            db.updated_at = datetime.now(timezone.utc)
            await session.commit()

            try:
                # Simulate sync operation - in reality would sync to blockchain/main network
                # For now, we'll just update the sync metadata
                db.sync_status = "idle"
                db.last_sync_at = datetime.now(timezone.utc)
                db.records_synced += 100  # Simulate syncing 100 records
                db.updated_at = datetime.now(timezone.utc)
                await session.commit()

                logger.info(f"Synced edge database {database_id}")

                return {
                    "success": True,
                    "message": f"Database {database_id} synced successfully",
                    "database_id": database_id,
                    "last_sync_at": db.last_sync_at.isoformat(),
                    "records_synced": db.records_synced,
                }
            except Exception as e:
                db.sync_status = "error"
                db.status = "error"
                db.updated_at = datetime.now(timezone.utc)
                await session.commit()

                logger.error(f"Failed to sync database {database_id}: {e}")

                return {
                    "success": False,
                    "message": f"Sync failed: {str(e)}",
                    "database_id": database_id,
                }

    async def list_all_databases(self) -> list[Dict]:
        """List all edge databases"""
        async with get_session() as session:
            result = await session.execute(select(EdgeDatabase))
            databases = result.all()

            return [
                {
                    "database_id": db[0].database_id,
                    "island_id": db[0].island_id,
                    "capacity_gb": db[0].capacity_gb,
                    "used_gb": db[0].used_gb,
                    "status": db[0].status,
                    "sync_status": db[0].sync_status,
                    "records_synced": db[0].records_synced,
                    "created_at": db[0].created_at.isoformat(),
                }
                for db in databases
            ]
