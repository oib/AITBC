"""
Cross-Chain Reputation Extensions
Extends the existing reputation system with cross-chain capabilities
"""

from datetime import date, datetime
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, Index, SQLModel


class CrossChainReputationConfig(SQLModel, table=True):
    """Chain-specific reputation configuration for cross-chain aggregation"""

    __tablename__ = "cross_chain_reputation_configs"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"config_{uuid4().hex[:8]}", primary_key=True)
    chain_id: int = Field(index=True, unique=True)

    # Weighting configuration
    chain_weight: float = Field(default=1.0)  # Weight in cross-chain aggregation
    base_reputation_bonus: float = Field(default=0.0)  # Base reputation for new agents

    # Scoring configuration
    transaction_success_weight: float = Field(default=0.1)
    transaction_failure_weight: float = Field(default=-0.2)
    dispute_penalty_weight: float = Field(default=-0.3)

    # Thresholds
    minimum_transactions_for_score: int = Field(default=5)
    reputation_decay_rate: float = Field(default=0.01)  # Daily decay rate
    anomaly_detection_threshold: float = Field(default=0.3)  # Score change threshold

    # Configuration metadata
    is_active: bool = Field(default=True)
    configuration_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CrossChainReputationAggregation(SQLModel, table=True):
    """Aggregated cross-chain reputation data"""

    __tablename__ = "cross_chain_reputation_aggregations"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"agg_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True)

    # Aggregated scores
    aggregated_score: float = Field(index=True, ge=0.0, le=1.0)
    weighted_score: float = Field(default=0.0, ge=0.0, le=1.0)
    normalized_score: float = Field(default=0.0, ge=0.0, le=1.0)

    # Chain breakdown
    chain_count: int = Field(default=0)
    active_chains: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    chain_scores: dict[int, float] = Field(default_factory=dict, sa_column=Column(JSON))
    chain_weights: dict[int, float] = Field(default_factory=dict, sa_column=Column(JSON))

    # Consistency metrics
    score_variance: float = Field(default=0.0)
    score_range: float = Field(default=0.0)
    consistency_score: float = Field(default=1.0, ge=0.0, le=1.0)

    # Verification status
    verification_status: str = Field(default="pending")  # pending, verified, failed
    verification_details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Timestamps
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_cross_chain_agg_agent", "agent_id"),
        Index("idx_cross_chain_agg_score", "aggregated_score"),
        Index("idx_cross_chain_agg_updated", "last_updated"),
        Index("idx_cross_chain_agg_status", "verification_status"),
    )


class CrossChainReputationEvent(SQLModel, table=True):
    """Cross-chain reputation events and synchronizations"""

    __tablename__ = "cross_chain_reputation_events"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"event_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True)
    source_chain_id: int = Field(index=True)
    target_chain_id: int | None = Field(index=True)

    # Event details
    event_type: str = Field(max_length=50)  # aggregation, migration, verification, etc.
    impact_score: float = Field(ge=-1.0, le=1.0)
    description: str = Field(default="")

    # Cross-chain data
    source_reputation: float | None = Field(default=None)
    target_reputation: float | None = Field(default=None)
    reputation_change: float | None = Field(default=None)

    # Event metadata
    event_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    source: str = Field(default="system")  # system, user, oracle, etc.
    verified: bool = Field(default=False)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: datetime | None = None

    # Indexes
    __table_args__ = (
        Index("idx_cross_chain_event_agent", "agent_id"),
        Index("idx_cross_chain_event_chains", "source_chain_id", "target_chain_id"),
        Index("idx_cross_chain_event_type", "event_type"),
        Index("idx_cross_chain_event_created", "created_at"),
    )


class ReputationMetrics(SQLModel, table=True):
    """Aggregated reputation metrics for analytics"""

    __tablename__ = "reputation_metrics"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"metrics_{uuid4().hex[:8]}", primary_key=True)
    chain_id: int = Field(index=True)
    metric_date: date = Field(index=True)

    # Aggregated metrics
    total_agents: int = Field(default=0)
    average_reputation: float = Field(default=0.0)
    reputation_distribution: dict[str, int] = Field(default_factory=dict, sa_column=Column(JSON))

    # Performance metrics
    total_transactions: int = Field(default=0)
    success_rate: float = Field(default=0.0)
    dispute_rate: float = Field(default=0.0)

    # Distribution metrics
    level_distribution: dict[str, int] = Field(default_factory=dict, sa_column=Column(JSON))
    score_distribution: dict[str, int] = Field(default_factory=dict, sa_column=Column(JSON))

    # Cross-chain metrics
    cross_chain_agents: int = Field(default=0)
    average_consistency_score: float = Field(default=0.0)
    chain_diversity_score: float = Field(default=0.0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# Request/Response Models for Cross-Chain API
class CrossChainReputationRequest(SQLModel):
    """Request model for cross-chain reputation operations"""

    agent_id: str
    chain_ids: list[int] | None = None
    include_history: bool = False
    include_metrics: bool = False
    aggregation_method: str = "weighted"  # weighted, average, normalized


class CrossChainReputationUpdateRequest(SQLModel):
    """Request model for cross-chain reputation updates"""

    agent_id: str
    chain_id: int
    reputation_score: float = Field(ge=0.0, le=1.0)
    transaction_data: dict[str, Any] = Field(default_factory=dict)
    source: str = "system"
    description: str = ""


class CrossChainAggregationRequest(SQLModel):
    """Request model for cross-chain aggregation"""

    agent_ids: list[str]
    chain_ids: list[int] | None = None
    aggregation_method: str = "weighted"
    force_recalculate: bool = False


class CrossChainVerificationRequest(SQLModel):
    """Request model for cross-chain reputation verification"""

    agent_id: str
    threshold: float = Field(default=0.5)
    verification_method: str = "consistency"  # consistency, weighted, minimum
    include_details: bool = False


# Response Models
class CrossChainReputationResponse(SQLModel):
    """Response model for cross-chain reputation"""

    agent_id: str
    chain_reputations: dict[int, dict[str, Any]]
    aggregated_score: float
    weighted_score: float
    normalized_score: float
    chain_count: int
    active_chains: list[int]
    consistency_score: float
    verification_status: str
    last_updated: datetime
    meta_data: dict[str, Any] = Field(default_factory=dict)


class CrossChainAnalyticsResponse(SQLModel):
    """Response model for cross-chain analytics"""

    chain_id: int | None
    total_agents: int
    cross_chain_agents: int
    average_reputation: float
    average_consistency_score: float
    chain_diversity_score: float
    reputation_distribution: dict[str, int]
    level_distribution: dict[str, int]
    score_distribution: dict[str, int]
    performance_metrics: dict[str, Any]
    cross_chain_metrics: dict[str, Any]
    generated_at: datetime


class ReputationAnomalyResponse(SQLModel):
    """Response model for reputation anomalies"""

    agent_id: str
    chain_id: int
    anomaly_type: str
    detected_at: datetime
    description: str
    severity: str
    previous_score: float
    current_score: float
    score_change: float
    confidence: float
    meta_data: dict[str, Any] = Field(default_factory=dict)


class CrossChainLeaderboardResponse(SQLModel):
    """Response model for cross-chain reputation leaderboard"""

    agents: list[CrossChainReputationResponse]
    total_count: int
    page: int
    page_size: int
    chain_filter: int | None
    sort_by: str
    sort_order: str
    last_updated: datetime


class ReputationVerificationResponse(SQLModel):
    """Response model for reputation verification"""

    agent_id: str
    threshold: float
    is_verified: bool
    verification_score: float
    chain_verifications: dict[int, bool]
    verification_details: dict[str, Any]
    consistency_analysis: dict[str, Any]
    verified_at: datetime
