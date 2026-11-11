"""
Agent Reputation and Trust System Domain Models
Implements SQLModel definitions for agent reputation, trust scores, and economic metrics
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import JSON, Column, Field, SQLModel

# The agent_id is intentionally a free-form identifier (miner id, agent workflow id,
# or any other provider key). It is not a foreign key because live job completion
# creates reputation profiles for miners that are not registered as AI agent workflows.

if TYPE_CHECKING:
    from aitbc_shared.models import ReputationDTO


class ReputationLevel(StrEnum):
    """Agent reputation level enumeration"""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    MASTER = "master"


class TrustScoreCategory(StrEnum):
    """Trust score calculation categories"""

    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    COMMUNITY = "community"
    SECURITY = "security"
    ECONOMIC = "economic"


class AgentReputation(SQLModel, table=True):
    """Agent reputation profile and metrics"""

    __tablename__ = "agent_reputation"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"rep_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True)

    # Core reputation metrics
    trust_score: float = Field(default=500.0, ge=0, le=1000)  # 0-1000 scale
    reputation_level: ReputationLevel = Field(default=ReputationLevel.BEGINNER)
    performance_rating: float = Field(default=3.0, ge=1.0, le=5.0)  # 1-5 stars
    reliability_score: float = Field(default=50.0, ge=0, le=100.0)  # 0-100%
    community_rating: float = Field(default=3.0, ge=1.0, le=5.0)  # 1-5 stars

    # Economic metrics
    total_earnings: Decimal = Field(default=Decimal("0.0"), max_digits=20, decimal_places=8)  # Total AITBC earned
    transaction_count: int = Field(default=0)  # Total transactions
    success_rate: float = Field(default=0.0, ge=0, le=100.0)  # Success percentage
    dispute_count: int = Field(default=0)  # Number of disputes
    dispute_won_count: int = Field(default=0)  # Disputes won

    # Activity metrics
    jobs_completed: int = Field(default=0)
    jobs_failed: int = Field(default=0)
    average_response_time: float = Field(default=0.0)  # milliseconds
    uptime_percentage: float = Field(default=0.0, ge=0, le=100.0)
    community_contributions: int = Field(default=0)  # Number of community contributions

    # Geographic and service info
    geographic_region: str = Field(default="", max_length=50)
    service_categories: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    specialization_tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Cross-chain reputation metrics
    aggregated_score: float = Field(default=0.0)
    chain_count: int = Field(default=0)
    active_chains: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    consistency_score: float = Field(default=0.0)
    chain_scores: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)

    # Additional metadata
    reputation_history: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    achievements: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    certifications: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    def to_dto(self) -> "ReputationDTO":
        """Project this ORM row into a context-agnostic :class:`ReputationDTO`.

        Cross-context consumers (certification, partnership, badge) should call
        this (via ``ReputationService.get_reputation_dto``) rather than
        importing ``AgentReputation`` directly, so they depend only on the DTO
        and not on the reputation context's ORM layer.
        """
        from aitbc_shared.models import ReputationDTO

        return ReputationDTO(
            agent_id=self.agent_id,
            trust_score=self.trust_score,
            reputation_level=self.reputation_level.value if self.reputation_level else "beginner",
            performance_rating=self.performance_rating,
            reliability_score=self.reliability_score,
            community_rating=self.community_rating,
            total_earnings=self.total_earnings,
            transaction_count=self.transaction_count,
            success_rate=self.success_rate,
            dispute_count=self.dispute_count,
            dispute_won_count=self.dispute_won_count,
            jobs_completed=self.jobs_completed,
            jobs_failed=self.jobs_failed,
            average_response_time=self.average_response_time,
            uptime_percentage=self.uptime_percentage,
            community_contributions=self.community_contributions,
            geographic_region=self.geographic_region,
            service_categories=list(self.service_categories or []),
            specialization_tags=list(self.specialization_tags or []),
            certifications=list(self.certifications or []),
            created_at=self.created_at,
            updated_at=self.updated_at,
            last_activity=self.last_activity,
        )


class ReputationEvent(SQLModel, table=True):
    """Reputation-changing events and transactions"""

    __tablename__ = "reputation_events"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"event_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True)

    # Event details
    event_type: str = Field(max_length=50)  # "job_completed", "dispute_resolved", etc.
    event_subtype: str = Field(default="", max_length=50)
    impact_score: float = Field(ge=-100, le=100)  # Positive or negative impact

    # Scoring details
    trust_score_before: float = Field(ge=0, le=1000)
    trust_score_after: float = Field(ge=0, le=1000)
    reputation_level_before: ReputationLevel | None = None
    reputation_level_after: ReputationLevel | None = None

    # Event context
    related_transaction_id: str | None = None
    related_job_id: str | None = None
    related_dispute_id: str | None = None

    # Event metadata
    event_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    verification_status: str = Field(default="pending")  # pending, verified, rejected

    # Timestamps
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processed_at: datetime | None = None
    expires_at: datetime | None = None


class CommunityFeedback(SQLModel, table=True):
    """Community feedback and ratings for agents"""

    __tablename__ = "community_feedback"
    __table_args__ = (
        # One review per (reviewer, job): feedback must be anchored to a
        # completed job, and this constraint stops a single job underwriting
        # unlimited ratings. Rows with a NULL job_id (legacy, admin) never
        # collide — NULLs are distinct in unique indexes.
        UniqueConstraint("reviewer_id", "job_id", name="uq_community_feedback_reviewer_job"),
        {"extend_existing": True},
    )

    id: str = Field(default_factory=lambda: f"feedback_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True)

    # Feedback details
    reviewer_id: str = Field(index=True)
    reviewer_type: str = Field(default="client")  # client, provider, peer
    # The completed job this review is anchored to (reviewer + job unique above).
    job_id: str | None = Field(default=None, index=True)

    # Ratings
    overall_rating: float = Field(ge=1.0, le=5.0)
    performance_rating: float = Field(ge=1.0, le=5.0)
    communication_rating: float = Field(ge=1.0, le=5.0)
    reliability_rating: float = Field(ge=1.0, le=5.0)
    value_rating: float = Field(ge=1.0, le=5.0)

    # Feedback content
    feedback_text: str = Field(default="", max_length=1000)
    feedback_tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Verification
    verified_transaction: bool = Field(default=False)
    verification_weight: float = Field(default=1.0, ge=0.1, le=10.0)

    # Moderation
    moderation_status: str = Field(default="approved", index=True)  # approved, pending, rejected
    moderator_notes: str = Field(default="", max_length=500)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    helpful_votes: int = Field(default=0)

    # Additional metadata
    feedback_context: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


__all__ = [
    "AgentReputation",
    "CommunityFeedback",
    "ReputationEvent",
    "ReputationLevel",
    "TrustScoreCategory",
]
