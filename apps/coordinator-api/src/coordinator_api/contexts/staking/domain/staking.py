"""
Staking Domain Models

Migrated from the flat domain/bounty.py to contexts/staking/domain/ in v0.5.14.
These staking models (StakeStatus, PerformanceTier, AgentStake, AgentMetrics,
StakingPool) were originally in bounty.py but are staking-specific. Table names
are unchanged — no DB migration required.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


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


class AgentStake(SQLModel, table=True):
    """Staking position on an AI agent wallet"""

    __tablename__ = "agent_stakes"
    __table_args__ = {"extend_existing": True}

    stake_id: str = Field(primary_key=True, default_factory=lambda: f"stake_{uuid.uuid4().hex[:8]}")
    staker_address: str = Field(index=True)
    agent_wallet: str = Field(index=True)

    # Stake details
    amount: Decimal = Field(index=True)
    lock_period: int = Field(default=30)  # days
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime

    # Status and rewards
    status: StakeStatus = Field(default=StakeStatus.ACTIVE, index=True)
    accumulated_rewards: Decimal = Field(default=Decimal("0.0"))
    last_reward_time: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # APY and performance
    current_apy: Decimal = Field(default=Decimal("5.0"))  # percentage
    agent_tier: PerformanceTier = Field(default=PerformanceTier.BRONZE)
    performance_multiplier: Decimal = Field(default=Decimal("1.0"))

    # Configuration
    auto_compound: bool = Field(default=False)
    unbonding_time: datetime | None = Field(default=None)

    # Penalties and bonuses
    early_unbond_penalty: Decimal = Field(default=Decimal("0.0"))
    lock_bonus_multiplier: Decimal = Field(default=Decimal("1.0"))

    # Metadata
    stake_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class AgentMetrics(SQLModel, table=True):
    """Performance metrics for AI agents"""

    __tablename__ = "agent_metrics"
    __table_args__ = {"extend_existing": True}

    agent_wallet: str = Field(primary_key=True, index=True)

    # Staking metrics
    total_staked: Decimal = Field(default=Decimal("0.0"))
    staker_count: int = Field(default=0)
    total_rewards_distributed: Decimal = Field(default=Decimal("0.0"))

    # Performance metrics
    average_accuracy: Decimal = Field(default=Decimal("0.0"))
    total_submissions: int = Field(default=0)
    successful_submissions: int = Field(default=0)
    success_rate: Decimal = Field(default=Decimal("0.0"))

    # Tier and scoring
    current_tier: PerformanceTier = Field(default=PerformanceTier.BRONZE)
    tier_score: Decimal = Field(default=Decimal("60.0"))
    reputation_score: Decimal = Field(default=Decimal("0.0"))

    # Timing
    last_update_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    first_submission_time: datetime | None = Field(default=None)

    # Additional metrics
    average_response_time: Decimal | None = Field(default=None)
    total_compute_time: Decimal | None = Field(default=None)
    energy_efficiency_score: Decimal | None = Field(default=None)

    # Historical data
    weekly_accuracy: list[Decimal] = Field(default_factory=list, sa_column=Column(JSON))
    monthly_earnings: list[Decimal] = Field(default_factory=list, sa_column=Column(JSON))

    # Metadata
    agent_meta_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Relationships
    # DISABLED:     stakes: List[AgentStake] = Relationship(back_populates="agent_metrics")


class StakingPool(SQLModel, table=True):
    """Staking pool for an agent"""

    __tablename__ = "staking_pools"
    __table_args__ = {"extend_existing": True}

    agent_wallet: str = Field(primary_key=True, index=True)

    # Pool metrics
    total_staked: Decimal = Field(default=Decimal("0.0"))
    total_rewards: Decimal = Field(default=Decimal("0.0"))
    pool_apy: Decimal = Field(default=Decimal("5.0"))

    # Staker information
    staker_count: int = Field(default=0)
    active_stakers: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Distribution
    last_distribution_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    distribution_frequency: int = Field(default=1)  # days

    # Pool configuration
    min_stake_amount: Decimal = Field(default=Decimal("360000.0"))
    max_stake_amount: Decimal = Field(default=Decimal("360000000.0"))
    auto_compound_enabled: bool = Field(default=False)

    # Performance tracking
    pool_performance_score: Decimal = Field(default=Decimal("0.0"))
    volatility_score: Decimal = Field(default=Decimal("0.0"))

    # Metadata
    pool_meta_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


__all__ = [
    "AgentMetrics",
    "AgentStake",
    "PerformanceTier",
    "StakeStatus",
    "StakingPool",
]
