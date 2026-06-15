"""Island-related schemas for Edge API Service"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, String
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel


class IslandStatus(StrEnum):
    """Island membership status"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    BRIDGING = "bridging"
    JOINED = "joined"


class IslandMembership(SQLModel, table=True):
    """Island membership in edge API database"""

    __tablename__ = "island_memberships"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"membership_{uuid4().hex[:8]}", primary_key=True)
    island_id: str = Field(sa_column=Column(String, index=True))
    island_name: str = Field(sa_column=Column(String))
    chain_id: str = Field(sa_column=Column(String, index=True))
    status: IslandStatus = Field(
        default=IslandStatus.ACTIVE, sa_column=Column(SQLEnum(IslandStatus, values_only=True), index=True)
    )
    role: str = Field(default="compute-provider", sa_column=Column(String))  # compute-provider, consumer, hub
    joined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    peer_count: int = Field(default=0)

    # Additional metadata
    extra_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=True))


class BridgeRequest(SQLModel, table=True):
    """Bridge request for island connectivity"""

    __tablename__ = "bridge_requests"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"bridge_req_{uuid4().hex[:8]}", primary_key=True)
    request_id: str = Field(sa_column=Column(String, index=True))
    source_island_id: str = Field(sa_column=Column(String))
    target_island_id: str = Field(sa_column=Column(String))
    source_node_id: str = Field(sa_column=Column(String))
    status: str = Field(default="pending", sa_column=Column(String, index=True))  # pending, approved, rejected
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
