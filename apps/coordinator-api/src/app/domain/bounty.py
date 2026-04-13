"""
Bounty System Domain Models
Database models for AI agent bounty system with ZK-proof verification
"""

import uuid
from datetime import datetime, timedelta
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


class StakeStatus(StrEnum):
    ACTIVE = "active"
    UNBONDING = "unbonding"
    COMPLETED = "completed"
    SLASHED = "slashed"


class PerformanceTier(StrEnum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    DIAMOND = "diamond"


class Bounty(SQLModel, table=True):
    """AI agent bounty with ZK-proof verification requirements"""

    __tablename__ = "bounties"

    bounty_id: str = Field(primary_key=True, default_factory=lambda: f"bounty_{uuid.uuid4().hex[:8]}")
    title: str = Field(index=True)
    description: str = Field(index=True)
    reward_amount: float = Field(index=True)
    creator_id: str = Field(index=True)
    tier: BountyTier = Field(default=BountyTier.BRONZE)
    status: BountyStatus = Field(default=BountyStatus.CREATED)

    # Performance requirements
    performance_criteria: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    min_accuracy: float = Field(default=90.0)
    max_response_time: int | None = Field(default=None)  # milliseconds

    # Timing
    deadline: datetime = Field(index=True)
    creation_time: datetime = Field(default_factory=datetime.utcnow)

    # Limits
    max_submissions: int = Field(default=100)
    submission_count: int = Field(default=0)

    # Configuration
    requires_zk_proof: bool = Field(default=True)
    auto_verify_threshold: float = Field(default=95.0)

    # Winner information
    winning_submission_id: str | None = Field(default=None)
    winner_address: str | None = Field(default=None)

    # Fees
    creation_fee: float = Field(default=0.0)
    success_fee: float = Field(default=0.0)
    platform_fee: float = Field(default=0.0)

    # Metadata
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    category: str | None = Field(default=None)
    difficulty: str | None = Field(default=None)

    # Relationships
    # DISABLED:     submissions: List["BountySubmission"] = Relationship(back_populates="bounty")

    # Indexes
    __table_args__ = {
        # # # "indexes": [
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
###        ]
    }


class BountySubmission(SQLModel, table=True):
    """Submission for a bounty with ZK-proof and performance metrics"""

    __tablename__ = "bounty_submissions"

    submission_id: str = Field(primary_key=True, default_factory=lambda: f"sub_{uuid.uuid4().hex[:8]}")
    bounty_id: str = Field(foreign_key="bounties.bounty_id", index=True)
    submitter_address: str = Field(index=True)

    # Performance metrics
    accuracy: float = Field(index=True)
    response_time: int | None = Field(default=None)  # milliseconds
    compute_power: float | None = Field(default=None)
    energy_efficiency: float | None = Field(default=None)

    # ZK-proof data
    zk_proof: dict[str, Any] | None = Field(default_factory=dict, sa_column=Column(JSON))
    performance_hash: str = Field(index=True)

    # Status and verification
    status: SubmissionStatus = Field(default=SubmissionStatus.PENDING)
    verification_time: datetime | None = Field(default=None)
    verifier_address: str | None = Field(default=None)

    # Dispute information
    dispute_reason: str | None = Field(default=None)
    dispute_time: datetime | None = Field(default=None)
    dispute_resolved: bool = Field(default=False)

    # Timing
    submission_time: datetime = Field(default_factory=datetime.utcnow)

    # Metadata
    submission_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    test_results: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Relationships
    # DISABLED:     bounty: Bounty = Relationship(back_populates="submissions")

    # Indexes
    __table_args__ = {
        # # # "indexes": [
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
###        ]
    }


class AgentStake(SQLModel, table=True):
    """Staking position on an AI agent wallet"""

    __tablename__ = "agent_stakes"

    stake_id: str = Field(primary_key=True, default_factory=lambda: f"stake_{uuid.uuid4().hex[:8]}")
    staker_address: str = Field(index=True)
    agent_wallet: str = Field(index=True)

    # Stake details
    amount: float = Field(index=True)
    lock_period: int = Field(default=30)  # days
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: datetime

    # Status and rewards
    status: StakeStatus = Field(default=StakeStatus.ACTIVE)
    accumulated_rewards: float = Field(default=0.0)
    last_reward_time: datetime = Field(default_factory=datetime.utcnow)

    # APY and performance
    current_apy: float = Field(default=5.0)  # percentage
    agent_tier: PerformanceTier = Field(default=PerformanceTier.BRONZE)
    performance_multiplier: float = Field(default=1.0)

    # Configuration
    auto_compound: bool = Field(default=False)
    unbonding_time: datetime | None = Field(default=None)

    # Penalties and bonuses
    early_unbond_penalty: float = Field(default=0.0)
    lock_bonus_multiplier: float = Field(default=1.0)

    # Metadata
    stake_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Indexes
    __table_args__ = {
        # # # "indexes": [
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
###        ]
    }


class AgentMetrics(SQLModel, table=True):
    """Performance metrics for AI agents"""

    __tablename__ = "agent_metrics"

    agent_wallet: str = Field(primary_key=True, index=True)

    # Staking metrics
    total_staked: float = Field(default=0.0)
    staker_count: int = Field(default=0)
    total_rewards_distributed: float = Field(default=0.0)

    # Performance metrics
    average_accuracy: float = Field(default=0.0)
    total_submissions: int = Field(default=0)
    successful_submissions: int = Field(default=0)
    success_rate: float = Field(default=0.0)

    # Tier and scoring
    current_tier: PerformanceTier = Field(default=PerformanceTier.BRONZE)
    tier_score: float = Field(default=60.0)
    reputation_score: float = Field(default=0.0)

    # Timing
    last_update_time: datetime = Field(default_factory=datetime.utcnow)
    first_submission_time: datetime | None = Field(default=None)

    # Additional metrics
    average_response_time: float | None = Field(default=None)
    total_compute_time: float | None = Field(default=None)
    energy_efficiency_score: float | None = Field(default=None)

    # Historical data
    weekly_accuracy: list[float] = Field(default_factory=list, sa_column=Column(JSON))
    monthly_earnings: list[float] = Field(default_factory=list, sa_column=Column(JSON))

    # Metadata
    agent_meta_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Relationships
    # DISABLED:     stakes: List[AgentStake] = Relationship(back_populates="agent_metrics")

    # Indexes
    __table_args__ = {
        # # # "indexes": [
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
###        ]
    }


class StakingPool(SQLModel, table=True):
    """Staking pool for an agent"""

    __tablename__ = "staking_pools"

    agent_wallet: str = Field(primary_key=True, index=True)

    # Pool metrics
    total_staked: float = Field(default=0.0)
    total_rewards: float = Field(default=0.0)
    pool_apy: float = Field(default=5.0)

    # Staker information
    staker_count: int = Field(default=0)
    active_stakers: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Distribution
    last_distribution_time: datetime = Field(default_factory=datetime.utcnow)
    distribution_frequency: int = Field(default=1)  # days

    # Pool configuration
    min_stake_amount: float = Field(default=100.0)
    max_stake_amount: float = Field(default=100000.0)
    auto_compound_enabled: bool = Field(default=False)

    # Performance tracking
    pool_performance_score: float = Field(default=0.0)
    volatility_score: float = Field(default=0.0)

    # Metadata
    pool_meta_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Indexes
    __table_args__ = {
        # # # "indexes": [
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
###        ]
    }


class BountyIntegration(SQLModel, table=True):
    """Integration between performance verification and bounty completion"""

    __tablename__ = "bounty_integrations"

    integration_id: str = Field(primary_key=True, default_factory=lambda: f"int_{uuid.uuid4().hex[:8]}")

    # Mapping information
    performance_hash: str = Field(index=True)
    bounty_id: str = Field(foreign_key="bounties.bounty_id", index=True)
    submission_id: str = Field(foreign_key="bounty_submissions.submission_id", index=True)

    # Status and timing
    status: BountyStatus = Field(default=BountyStatus.CREATED)
    created_at: datetime = Field(default_factory=datetime.utcnow)
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

    # Indexes
    __table_args__ = {
        # # # "indexes": [
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
###        ]
    }


class BountyStats(SQLModel, table=True):
    """Aggregated bounty statistics"""

    __tablename__ = "bounty_stats"

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

    # Indexes
    __table_args__ = {
        # # # "indexes": [
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
###        ]
    }


class EcosystemMetrics(SQLModel, table=True):
    """Ecosystem-wide metrics for dashboard"""

    __tablename__ = "ecosystem_metrics"

    metrics_id: str = Field(primary_key=True, default_factory=lambda: f"eco_{uuid.uuid4().hex[:8]}")

    # Time period
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    period_type: str = Field(default="hourly")  # hourly, daily, weekly

    # Developer metrics
    active_developers: int = Field(default=0)
    new_developers: int = Field(default=0)
    developer_earnings_total: float = Field(default=0.0)
    developer_earnings_average: float = Field(default=0.0)

    # Agent metrics
    total_agents: int = Field(default=0)
    active_agents: int = Field(default=0)
    agent_utilization_rate: float = Field(default=0.0)
    average_agent_performance: float = Field(default=0.0)

    # Staking metrics
    total_staked: float = Field(default=0.0)
    total_stakers: int = Field(default=0)
    average_apy: float = Field(default=0.0)
    staking_rewards_total: float = Field(default=0.0)

    # Bounty metrics
    active_bounties: int = Field(default=0)
    bounty_completion_rate: float = Field(default=0.0)
    average_bounty_reward: float = Field(default=0.0)
    bounty_volume_total: float = Field(default=0.0)

    # Treasury metrics
    treasury_balance: float = Field(default=0.0)
    treasury_inflow: float = Field(default=0.0)
    treasury_outflow: float = Field(default=0.0)
    dao_revenue: float = Field(default=0.0)

    # Token metrics
    token_circulating_supply: float = Field(default=0.0)
    token_staked_percentage: float = Field(default=0.0)
    token_burn_rate: float = Field(default=0.0)

    # Metadata
    metrics_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Indexes
    __table_args__ = {
        # # # "indexes": [
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
#            # {"name": "...", "columns": [...]},
###        ]
    }


# Update relationships
# DISABLED: AgentStake.agent_metrics = Relationship(back_populates="stakes")
