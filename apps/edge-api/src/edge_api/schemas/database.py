"""Edge database-related schemas for Edge API Service"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class EdgeDatabase(SQLModel, table=True):
    """Edge database instance"""
    
    __tablename__ = "edge_databases"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"edge_db_{uuid4().hex[:8]}", primary_key=True)
    database_id: str = Field(index=True)
    island_id: str = Field(index=True)
    capacity_gb: int
    used_gb: int = Field(default=0)
    status: str = Field(default="initialized", index=True)  # initialized, active, syncing, error
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Sync information
    last_sync_at: datetime | None = Field(default=None)
    sync_status: str = Field(default="idle")  # idle, syncing, error
    records_synced: int = Field(default=0)
    
    # Database metadata
    extra_data: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=True))
