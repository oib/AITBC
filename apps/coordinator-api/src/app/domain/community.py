"""
Community and Developer Ecosystem Models
Database models for OpenClaw agent community, third-party solutions, and innovation labs
"""

import uuid
from datetime import datetime
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
    """Profile for a developer in the OpenClaw community"""

    __tablename__ = "developer_profiles"

    developer_id: str = Field(primary_key=True, default_factory=lambda: f"dev_{uuid.uuid4().hex[:8]}")
    user_id: str = Field(index=True)
    username: str = Field(unique=True)
    bio: str | None = None

    tier: DeveloperTier = Field(default=DeveloperTier.NOVICE)
    reputation_score: float = Field(default=0.0)
    total_earnings: float = Field(default=0.0)

    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    github_handle: str | None = None
    website: str | None = None

    joined_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    last_active: datetime = Field(default_factory=datetime.now(datetime.UTC))


class AgentSolution(SQLModel, table=True):
    """A third-party agent solution available in the developer marketplace"""

    __tablename__ = "agent_solutions"

    solution_id: str = Field(primary_key=True, default_factory=lambda: f"sol_{uuid.uuid4().hex[:8]}")
    developer_id: str = Field(foreign_key="developer_profiles.developer_id")

    title: str
    description: str
    version: str = Field(default="1.0.0")

    capabilities: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    frameworks: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    price_model: str = Field(default="free")  # free, one_time, subscription, usage_based
    price_amount: float = Field(default=0.0)
    currency: str = Field(default="AITBC")

    status: SolutionStatus = Field(default=SolutionStatus.DRAFT)
    downloads: int = Field(default=0)
    average_rating: float = Field(default=0.0)
    review_count: int = Field(default=0)

    solution_meta_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    published_at: datetime | None = None


class InnovationLab(SQLModel, table=True):
    """Research program or innovation lab for agent development"""

    __tablename__ = "innovation_labs"

    lab_id: str = Field(primary_key=True, default_factory=lambda: f"lab_{uuid.uuid4().hex[:8]}")
    title: str
    description: str
    research_area: str

    lead_researcher_id: str = Field(foreign_key="developer_profiles.developer_id")
    members: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # List of developer_ids

    status: LabStatus = Field(default=LabStatus.PROPOSED)
    funding_goal: float = Field(default=0.0)
    current_funding: float = Field(default=0.0)

    milestones: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    publications: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    target_completion: datetime | None = None


class CommunityPost(SQLModel, table=True):
    """A post in the community support/collaboration platform"""

    __tablename__ = "community_posts"

    post_id: str = Field(primary_key=True, default_factory=lambda: f"post_{uuid.uuid4().hex[:8]}")
    author_id: str = Field(foreign_key="developer_profiles.developer_id")

    title: str
    content: str
    category: str = Field(default="discussion")  # discussion, question, showcase, tutorial
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    upvotes: int = Field(default=0)
    views: int = Field(default=0)
    is_resolved: bool = Field(default=False)

    parent_post_id: str | None = Field(default=None, foreign_key="community_posts.post_id")

    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))


class Hackathon(SQLModel, table=True):
    """Innovation challenge or hackathon"""

    __tablename__ = "hackathons"

    hackathon_id: str = Field(primary_key=True, default_factory=lambda: f"hack_{uuid.uuid4().hex[:8]}")
    title: str
    description: str
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
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
