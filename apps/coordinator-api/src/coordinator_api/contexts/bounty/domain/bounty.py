"""
Bounty System Domain Models

Migrated from the flat domain/bounty.py to contexts/bounty/domain/ in v0.5.14.
Staking models (StakeStatus, PerformanceTier, AgentStake, AgentMetrics,
StakingPool) were split to contexts/staking/domain/staking.py.
EcosystemMetrics was split to contexts/ecosystem/domain/ecosystem.py.
Table names are unchanged — no DB migration required.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class BountyStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    COMPLETED = "completed"
    EXPIRED = "expired"
    DISPUTED = "disputed"


class BountyTier(StrEnum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class SubmissionStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    DISPUTED = "disputed"


class Bounty(SQLModel, table=True):
    """AI agent bounty with ZK-proof verification requirements"""

    __tablename__ = "bounties"
    __table_args__ = {"extend_existing": True}

    bounty_id: str = Field(primary_key=True, default_factory=lambda: f"bounty_{uuid.uuid4().hex[:8]}")
    title: str = Field(index=True)
    description: str = Field(index=True)
    reward_amount: Decimal = Field(index=True)
    creator_id: str = Field(index=True)
    tier: BountyTier = Field(default=BountyTier.BRONZE)
    status: BountyStatus = Field(default=BountyStatus.CREATED, index=True)

    # Performance requirements
    performance_criteria: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    min_accuracy: Decimal = Field(default=Decimal("90.0"))
    max_response_time: int | None = Field(default=None)  # milliseconds

    # Timing
    deadline: datetime = Field(index=True)
    creation_time: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)

    # Limits
    max_submissions: int = Field(default=100)
    submission_count: int = Field(default=0)

    # Configuration
    requires_zk_proof: bool = Field(default=True)
    auto_verify_threshold: Decimal = Field(default=Decimal("95.0"))

    # Winner information
    winning_submission_id: str | None = Field(default=None)
    winner_address: str | None = Field(default=None)

    # Fees
    creation_fee: Decimal = Field(default=Decimal("0.0"))
    success_fee: Decimal = Field(default=Decimal("0.0"))
    platform_fee: Decimal = Field(default=Decimal("0.0"))

    # Metadata
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    category: str | None = Field(default=None)
    difficulty: str | None = Field(default=None)

    # Relationships
    # DISABLED:     submissions: List["BountySubmission"] = Relationship(back_populates="bounty")


class BountySubmission(SQLModel, table=True):
    """Submission for a bounty with ZK-proof and performance metrics"""

    __tablename__ = "bounty_submissions"
    __table_args__ = {"extend_existing": True}

    submission_id: str = Field(primary_key=True, default_factory=lambda: f"sub_{uuid.uuid4().hex[:8]}")
    bounty_id: str = Field(foreign_key="bounties.bounty_id", index=True)
    submitter_address: str = Field(index=True)

    # Performance metrics
    accuracy: Decimal = Field(index=True)
    response_time: int | None = Field(default=None)  # milliseconds
    compute_power: Decimal | None = Field(default=None)
    energy_efficiency: Decimal | None = Field(default=None)

    # ZK-proof data
    zk_proof: dict[str, Any] | None = Field(default_factory=dict, sa_column=Column(JSON))
    performance_hash: str = Field(index=True)

    # Status and verification
    status: SubmissionStatus = Field(default=SubmissionStatus.PENDING, index=True)
    verification_time: datetime | None = Field(default=None)
    verifier_address: str | None = Field(default=None)

    # Dispute information
    dispute_reason: str | None = Field(default=None)
    dispute_time: datetime | None = Field(default=None)
    dispute_resolved: bool = Field(default=False)

    # Timing
    submission_time: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)

    # Metadata
    submission_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    test_results: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Relationships
    # DISABLED:     bounty: Bounty = Relationship(back_populates="submissions")


class BountyIntegration(SQLModel, table=True):
    """Integration between performance verification and bounty completion"""

    __tablename__ = "bounty_integrations"
    __table_args__ = {"extend_existing": True}

    integration_id: str = Field(primary_key=True, default_factory=lambda: f"int_{uuid.uuid4().hex[:8]}")

    # Mapping information
    performance_hash: str = Field(index=True)
    bounty_id: str = Field(foreign_key="bounties.bounty_id", index=True)
    submission_id: str = Field(foreign_key="bounty_submissions.submission_id", index=True)

    # Status and timing
    status: BountyStatus = Field(default=BountyStatus.CREATED)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processed_at: datetime | None = Field(default=None)

    # Processing information
    processing_attempts: int = Field(default=0)
    error_message: str | None = Field(default=None)
    gas_used: int | None = Field(default=None)

    # Verification results
    auto_verified: bool = Field(default=False)
    verification_threshold_met: bool = Field(default=False)
    performance_score: float | None = Field(default=None)

    # Metadata
    integration_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class BountyStats(SQLModel, table=True):
    """Aggregated bounty statistics"""

    __tablename__ = "bounty_stats"
    __table_args__ = {"extend_existing": True}

    stats_id: str = Field(primary_key=True, default_factory=lambda: f"stats_{uuid.uuid4().hex[:8]}")

    # Time period
    period_start: datetime = Field(index=True)
    period_end: datetime = Field(index=True)
    period_type: str = Field(default="daily")  # daily, weekly, monthly

    # Bounty counts
    total_bounties: int = Field(default=0)
    active_bounties: int = Field(default=0)
    completed_bounties: int = Field(default=0)
    expired_bounties: int = Field(default=0)
    disputed_bounties: int = Field(default=0)

    # Financial metrics
    total_value_locked: float = Field(default=0.0)
    total_rewards_paid: float = Field(default=0.0)
    total_fees_collected: float = Field(default=0.0)
    average_reward: float = Field(default=0.0)

    # Performance metrics
    success_rate: float = Field(default=0.0)
    average_completion_time: float | None = Field(default=None)  # hours
    average_accuracy: float | None = Field(default=None)

    # Participant metrics
    unique_creators: int = Field(default=0)
    unique_submitters: int = Field(default=0)
    total_submissions: int = Field(default=0)

    # Tier distribution
    tier_distribution: dict[str, int] = Field(default_factory=dict, sa_column=Column(JSON))

    # Metadata
    stats_meta_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


__all__ = [
    "Bounty",
    "BountyIntegration",
    "BountyStats",
    "BountyStatus",
    "BountySubmission",
    "BountyTier",
    "SubmissionStatus",
]
