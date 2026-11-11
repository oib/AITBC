"""
Community and Developer Ecosystem Models
Database models for agent agent community, third-party solutions, and innovation labs
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class DeveloperTier(StrEnum):
    NOVICE = "novice"
    BUILDER = "builder"
    EXPERT = "expert"
    MASTER = "master"
    PARTNER = "partner"


class SolutionStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


class LabStatus(StrEnum):
    PROPOSED = "proposed"
    FUNDING = "funding"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class HackathonStatus(StrEnum):
    ANNOUNCED = "announced"
    REGISTRATION = "registration"
    ONGOING = "ongoing"
    JUDGING = "judging"
    COMPLETED = "completed"


class DeveloperProfile(SQLModel, table=True):
    """Profile for a developer in the agent community"""

    __tablename__ = "developer_profiles"

    developer_id: str = Field(primary_key=True, default_factory=lambda: f"dev_{uuid.uuid4().hex[:8]}")
    user_id: str = Field(index=True)
    username: str = Field(unique=True)
    bio: str | None = None

    tier: DeveloperTier = Field(default=DeveloperTier.NOVICE)
    reputation_score: float = Field(default=0.0)
    total_earnings: Decimal = Field(default=Decimal("0.0"), max_digits=20, decimal_places=8)

    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    github_handle: str | None = None
    website: str | None = None

    joined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Hackathon(SQLModel, table=True):
    """Innovation challenge or hackathon"""

    __tablename__ = "hackathons"

    hackathon_id: str = Field(primary_key=True, default_factory=lambda: f"hack_{uuid.uuid4().hex[:8]}")
    title: str = Field(max_length=200)
    description: str = Field(max_length=255)
    theme: str

    sponsor: str = Field(default="AITBC Foundation")
    prize_pool: float = Field(default=0.0)
    prize_currency: str = Field(default="AITBC")

    status: HackathonStatus = Field(default=HackathonStatus.ANNOUNCED)
    participants: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # List of developer_ids
    submissions: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))

    registration_start: datetime
    registration_end: datetime
    event_start: datetime
    event_end: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "DeveloperProfile",
    "DeveloperTier",
    "Hackathon",
    "HackathonStatus",
    "LabStatus",
    "SolutionStatus",
]
