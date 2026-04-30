"""
Agent Reward System Domain Models
Implements SQLModel definitions for performance-based rewards, incentives, and distributions
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, SQLModel


class RewardTier(StrEnum):
    """Reward tier enumeration"""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    DIAMOND = "diamond"


class RewardType(StrEnum):
    """Reward type enumeration"""

    PERFORMANCE_BONUS = "performance_bonus"
    LOYALTY_BONUS = "loyalty_bonus"
    REFERRAL_BONUS = "referral_bonus"
    MILESTONE_BONUS = "milestone_bonus"
    COMMUNITY_BONUS = "community_bonus"
    SPECIAL_BONUS = "special_bonus"


class RewardStatus(StrEnum):
    """Reward status enumeration"""

    PENDING = "pending"
    APPROVED = "approved"
    DISTRIBUTED = "distributed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class RewardTierConfig(SQLModel, table=True):
    """Reward tier configuration and thresholds"""

    __tablename__ = "reward_tier_configs"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"tier_{uuid4().hex[:8]}", primary_key=True)
    tier: RewardTier

    # Threshold requirements
    min_trust_score: float = Field(ge=0, le=1000)
    min_performance_rating: float = Field(ge=1.0, le=5.0)
    min_monthly_earnings: float = Field(ge=0)
    min_transaction_count: int = Field(ge=0)
    min_success_rate: float = Field(ge=0, le=100.0)

    # Reward multipliers and benefits
    base_multiplier: float = Field(default=1.0, ge=1.0)
    performance_bonus_multiplier: float = Field(default=1.0, ge=1.0)
    loyalty_bonus_multiplier: float = Field(default=1.0, ge=1.0)
    referral_bonus_multiplier: float = Field(default=1.0, ge=1.0)

    # Tier benefits
    max_concurrent_jobs: int = Field(default=1)
    priority_boost: float = Field(default=1.0)
    fee_discount: float = Field(default=0.0, ge=0, le=100.0)
    support_level: str = Field(default="basic")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    is_active: bool = Field(default=True)

    # Additional configuration
    tier_requirements: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    tier_benefits: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class AgentRewardProfile(SQLModel, table=True):
    """Agent reward profile and earnings tracking"""

    __tablename__ = "agent_reward_profiles"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"reward_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True, foreign_key="agent_reputation.id")

    # Current tier and status
    current_tier: RewardTier = Field(default=RewardTier.BRONZE)
    tier_progress: float = Field(default=0.0, ge=0, le=100.0)  # Progress to next tier

    # Earnings tracking
    base_earnings: float = Field(default=0.0)
    bonus_earnings: float = Field(default=0.0)
    total_earnings: float = Field(default=0.0)
    lifetime_earnings: float = Field(default=0.0)

    # Performance metrics for rewards
    performance_score: float = Field(default=0.0)
    loyalty_score: float = Field(default=0.0)
    referral_count: int = Field(default=0)
    community_contributions: int = Field(default=0)

    # Reward history
    rewards_distributed: int = Field(default=0)
    last_reward_date: datetime | None = None
    current_streak: int = Field(default=0)  # Consecutive reward periods
    longest_streak: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    last_activity: datetime = Field(default_factory=datetime.now(datetime.UTC))

    # Additional metadata
    reward_preferences: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    achievement_history: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class RewardCalculation(SQLModel, table=True):
    """Reward calculation records and factors"""

    __tablename__ = "reward_calculations"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"calc_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True, foreign_key="agent_reward_profiles.id")

    # Calculation details
    reward_type: RewardType
    base_amount: float = Field(ge=0)
    tier_multiplier: float = Field(default=1.0, ge=1.0)

    # Bonus factors
    performance_bonus: float = Field(default=0.0)
    loyalty_bonus: float = Field(default=0.0)
    referral_bonus: float = Field(default=0.0)
    community_bonus: float = Field(default=0.0)
    special_bonus: float = Field(default=0.0)

    # Final calculation
    total_reward: float = Field(ge=0)
    effective_multiplier: float = Field(default=1.0, ge=1.0)

    # Calculation metadata
    calculation_period: str = Field(default="daily")  # daily, weekly, monthly
    reference_date: datetime = Field(default_factory=datetime.now(datetime.UTC))
    trust_score_at_calculation: float = Field(ge=0, le=1000)
    performance_metrics: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    # Timestamps
    calculated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    expires_at: datetime | None = None

    # Additional data
    calculation_details: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class RewardDistribution(SQLModel, table=True):
    """Reward distribution records and transactions"""

    __tablename__ = "reward_distributions"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"dist_{uuid4().hex[:8]}", primary_key=True)
    calculation_id: str = Field(index=True, foreign_key="reward_calculations.id")
    agent_id: str = Field(index=True, foreign_key="agent_reward_profiles.id")

    # Distribution details
    reward_amount: float = Field(ge=0)
    reward_type: RewardType
    distribution_method: str = Field(default="automatic")  # automatic, manual, batch

    # Transaction details
    transaction_id: str | None = None
    transaction_hash: str | None = None
    transaction_status: str = Field(default="pending")

    # Status tracking
    status: RewardStatus = Field(default=RewardStatus.PENDING)
    processed_at: datetime | None = None
    confirmed_at: datetime | None = None

    # Distribution metadata
    batch_id: str | None = None
    priority: int = Field(default=5, ge=1, le=10)  # 1 = highest priority
    retry_count: int = Field(default=0)
    error_message: str | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    scheduled_at: datetime | None = None

    # Additional data
    distribution_details: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class RewardEvent(SQLModel, table=True):
    """Reward-related events and triggers"""

    __tablename__ = "reward_events"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"event_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True, foreign_key="agent_reward_profiles.id")

    # Event details
    event_type: str = Field(max_length=50)  # "tier_upgrade", "milestone_reached", etc.
    event_subtype: str = Field(default="", max_length=50)
    trigger_source: str = Field(max_length=50)  # "system", "manual", "automatic"

    # Event impact
    reward_impact: float = Field(ge=0)  # Total reward amount from this event
    tier_impact: RewardTier | None = None

    # Event context
    related_transaction_id: str | None = None
    related_calculation_id: str | None = None
    related_distribution_id: str | None = None

    # Event metadata
    event_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    verification_status: str = Field(default="pending")  # pending, verified, rejected

    # Timestamps
    occurred_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    processed_at: datetime | None = None
    expires_at: datetime | None = None

    # Additional metadata
    event_context: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class RewardMilestone(SQLModel, table=True):
    """Reward milestones and achievements"""

    __tablename__ = "reward_milestones"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"milestone_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True, foreign_key="agent_reward_profiles.id")

    # Milestone details
    milestone_type: str = Field(max_length=50)  # "earnings", "jobs", "reputation", etc.
    milestone_name: str = Field(max_length=100)
    milestone_description: str = Field(default="", max_length=500)

    # Threshold and progress
    target_value: float = Field(ge=0)
    current_value: float = Field(default=0.0, ge=0)
    progress_percentage: float = Field(default=0.0, ge=0, le=100.0)

    # Rewards
    reward_amount: float = Field(default=0.0, ge=0)
    reward_type: RewardType = Field(default=RewardType.MILESTONE_BONUS)

    # Status
    is_completed: bool = Field(default=False)
    is_claimed: bool = Field(default=False)
    completed_at: datetime | None = None
    claimed_at: datetime | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    expires_at: datetime | None = None

    # Additional data
    milestone_config: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class RewardAnalytics(SQLModel, table=True):
    """Reward system analytics and metrics"""

    __tablename__ = "reward_analytics"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"analytics_{uuid4().hex[:8]}", primary_key=True)

    # Analytics period
    period_type: str = Field(default="daily")  # daily, weekly, monthly
    period_start: datetime
    period_end: datetime

    # Aggregate metrics
    total_rewards_distributed: float = Field(default=0.0)
    total_agents_rewarded: int = Field(default=0)
    average_reward_per_agent: float = Field(default=0.0)

    # Tier distribution
    bronze_rewards: float = Field(default=0.0)
    silver_rewards: float = Field(default=0.0)
    gold_rewards: float = Field(default=0.0)
    platinum_rewards: float = Field(default=0.0)
    diamond_rewards: float = Field(default=0.0)

    # Reward type distribution
    performance_rewards: float = Field(default=0.0)
    loyalty_rewards: float = Field(default=0.0)
    referral_rewards: float = Field(default=0.0)
    milestone_rewards: float = Field(default=0.0)
    community_rewards: float = Field(default=0.0)
    special_rewards: float = Field(default=0.0)

    # Performance metrics
    calculation_count: int = Field(default=0)
    distribution_count: int = Field(default=0)
    success_rate: float = Field(default=0.0, ge=0, le=100.0)
    average_processing_time: float = Field(default=0.0)  # milliseconds

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))

    # Additional analytics data
    analytics_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
