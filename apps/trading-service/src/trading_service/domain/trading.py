"""
Agent-to-Agent Trading Protocol Domain Models
Implements SQLModel definitions for P2P trading, matching, negotiation, and settlement
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, SQLModel


class TradeStatus(StrEnum):
    """Trade status enumeration"""

    OPEN = "open"
    MATCHING = "matching"
    NEGOTIATING = "negotiating"
    AGREED = "agreed"
    SETTLING = "settling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TradeType(StrEnum):
    """Trade type enumeration"""

    AI_POWER = "ai_power"
    COMPUTE_RESOURCES = "compute_resources"
    DATA_SERVICES = "data_services"
    MODEL_SERVICES = "model_services"
    INFERENCE_TASKS = "inference_tasks"
    TRAINING_TASKS = "training_tasks"


class NegotiationStatus(StrEnum):
    """Negotiation status enumeration"""

    PENDING = "pending"
    ACTIVE = "active"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTERED = "countered"
    EXPIRED = "expired"


class SettlementType(StrEnum):
    """Settlement type enumeration"""

    IMMEDIATE = "immediate"
    ESCROW = "escrow"
    MILESTONE = "milestone"
    SUBSCRIPTION = "subscription"


class TradeRequest(SQLModel, table=True):
    """P2P trade request from buyer agent"""

    __tablename__ = "trade_requests"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:8]}", primary_key=True)
    request_id: str = Field(unique=True, index=True)

    buyer_agent_id: str = Field(index=True)
    trade_type: TradeType
    title: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)

    requirements: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    specifications: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    constraints: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    budget_range: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    preferred_terms: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    negotiation_flexible: bool = Field(default=True)

    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_hours: int | None = None
    urgency_level: str = Field(default="normal")

    preferred_regions: list[str] = Field(default=[], sa_column=Column(JSON))
    excluded_regions: list[str] = Field(default=[], sa_column=Column(JSON))
    service_level_required: str = Field(default="standard")

    status: TradeStatus = Field(default=TradeStatus.OPEN)
    priority: int = Field(default=5, ge=1, le=10)

    match_count: int = Field(default=0)
    negotiation_count: int = Field(default=0)
    best_match_score: float = Field(default=0.0)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    tags: list[str] = Field(default=[], sa_column=Column(JSON))
    trading_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class TradeMatch(SQLModel, table=True):
    """Trade match between buyer request and seller offer"""

    __tablename__ = "trade_matches"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"match_{uuid4().hex[:8]}", primary_key=True)
    match_id: str = Field(unique=True, index=True)

    request_id: str = Field(index=True, foreign_key="trade_requests.request_id")
    buyer_agent_id: str = Field(index=True)
    seller_agent_id: str = Field(index=True)

    match_score: float = Field(ge=0, le=100)
    confidence_level: float = Field(ge=0, le=1)

    price_compatibility: float = Field(ge=0, le=100)
    timing_compatibility: float = Field(ge=0, le=100)
    specification_compatibility: float = Field(ge=0, le=100)
    reputation_compatibility: float = Field(ge=0, le=100)
    geographic_compatibility: float = Field(ge=0, le=100)

    seller_offer: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    proposed_terms: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    status: TradeStatus = Field(default=TradeStatus.MATCHING)
    buyer_response: str | None = None
    seller_response: str | None = None

    negotiation_initiated: bool = Field(default=False)
    negotiation_initiator: str | None = None
    initial_terms: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    last_interaction: datetime | None = None

    match_factors: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    interaction_history: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class TradeNegotiation(SQLModel, table=True):
    """Negotiation process between buyer and seller"""

    __tablename__ = "trade_negotiations"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"neg_{uuid4().hex[:8]}", primary_key=True)
    negotiation_id: str = Field(unique=True, index=True)

    match_id: str = Field(index=True, foreign_key="trade_matches.match_id")
    buyer_agent_id: str = Field(index=True)
    seller_agent_id: str = Field(index=True)

    status: NegotiationStatus = Field(default=NegotiationStatus.PENDING)
    negotiation_round: int = Field(default=1)
    max_rounds: int = Field(default=5)

    current_terms: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    initial_terms: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    final_terms: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    price_range: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    service_level_agreements: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    delivery_terms: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    payment_terms: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    concession_count: int = Field(default=0)
    counter_offer_count: int = Field(default=0)
    agreement_score: float = Field(default=0.0, ge=0, le=100)

    ai_assisted: bool = Field(default=True)
    negotiation_strategy: str = Field(default="balanced")
    auto_accept_threshold: float = Field(default=85.0, ge=0, le=100)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    last_offer_at: datetime | None = None

    negotiation_history: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    ai_recommendations: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class TradeAgreement(SQLModel, table=True):
    """Final trade agreement between buyer and seller"""

    __tablename__ = "trade_agreements"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"agree_{uuid4().hex[:8]}", primary_key=True)
    agreement_id: str = Field(unique=True, index=True)

    negotiation_id: str = Field(index=True, foreign_key="trade_negotiations.negotiation_id")
    buyer_agent_id: str = Field(index=True)
    seller_agent_id: str = Field(index=True)

    trade_type: TradeType
    title: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)

    agreed_terms: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    specifications: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    service_level_agreement: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    total_price: float = Field(ge=0)
    currency: str = Field(default="AITBC")
    payment_schedule: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    settlement_type: SettlementType

    delivery_timeline: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    performance_metrics: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    quality_standards: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    terms_and_conditions: str = Field(default="", max_length=5000)
    compliance_requirements: list[str] = Field(default=[], sa_column=Column(JSON))
    dispute_resolution: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    status: TradeStatus = Field(default=TradeStatus.AGREED)
    execution_status: str = Field(default="pending")
    completion_percentage: float = Field(default=0.0, ge=0, le=100)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    signed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    completed_at: datetime | None = None

    agreement_document: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    attachments: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class TradeSettlement(SQLModel, table=True):
    """Trade settlement and payment processing"""

    __tablename__ = "trade_settlements"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"settle_{uuid4().hex[:8]}", primary_key=True)
    settlement_id: str = Field(unique=True, index=True)

    agreement_id: str = Field(index=True, foreign_key="trade_agreements.agreement_id")
    buyer_agent_id: str = Field(index=True)
    seller_agent_id: str = Field(index=True)

    settlement_type: SettlementType
    total_amount: float = Field(ge=0)
    currency: str = Field(default="AITBC")

    payment_status: str = Field(default="pending")
    transaction_id: str | None = None
    transaction_hash: str | None = None
    block_number: int | None = None

    escrow_enabled: bool = Field(default=False)
    escrow_address: str | None = None
    escrow_release_conditions: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    milestone_payments: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    completed_milestones: list[str] = Field(default=[], sa_column=Column(JSON))

    platform_fee: float = Field(default=0.0)
    processing_fee: float = Field(default=0.0)
    gas_fee: float = Field(default=0.0)
    net_amount_seller: float = Field(ge=0)

    status: TradeStatus = Field(default=TradeStatus.SETTLING)
    initiated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: datetime | None = None
    completed_at: datetime | None = None
    refunded_at: datetime | None = None

    dispute_raised: bool = Field(default=False)
    dispute_details: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    resolution_details: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    settlement_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    audit_trail: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class TradeFeedback(SQLModel, table=True):
    """Trade feedback and rating system"""

    __tablename__ = "trade_feedback"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"feedback_{uuid4().hex[:8]}", primary_key=True)

    agreement_id: str = Field(index=True, foreign_key="trade_agreements.agreement_id")
    reviewer_agent_id: str = Field(index=True)
    reviewed_agent_id: str = Field(index=True)
    reviewer_role: str = Field(default="buyer")

    overall_rating: float = Field(ge=1.0, le=5.0)
    communication_rating: float = Field(ge=1.0, le=5.0)
    performance_rating: float = Field(ge=1.0, le=5.0)
    timeliness_rating: float = Field(ge=1.0, le=5.0)
    value_rating: float = Field(ge=1.0, le=5.0)

    feedback_text: str = Field(default="", max_length=1000)
    feedback_tags: list[str] = Field(default=[], sa_column=Column(JSON))

    trade_category: str = Field(default="general")
    trade_complexity: str = Field(default="medium")
    trade_duration: int | None = None

    verified_trade: bool = Field(default=True)
    moderation_status: str = Field(default="approved")
    moderator_notes: str = Field(default="", max_length=500)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trade_completed_at: datetime

    feedback_context: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    performance_metrics: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class TradingAnalytics(SQLModel, table=True):
    """P2P trading system analytics and metrics"""

    __tablename__ = "trading_analytics"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"analytics_{uuid4().hex[:8]}", primary_key=True)

    period_type: str = Field(default="daily")
    period_start: datetime
    period_end: datetime

    total_trades: int = Field(default=0)
    completed_trades: int = Field(default=0)
    failed_trades: int = Field(default=0)
    cancelled_trades: int = Field(default=0)

    total_trade_volume: float = Field(default=0.0)
    average_trade_value: float = Field(default=0.0)
    total_platform_fees: float = Field(default=0.0)

    trade_type_distribution: dict[str, int] = Field(default={}, sa_column=Column(JSON))

    active_buyers: int = Field(default=0)
    active_sellers: int = Field(default=0)
    new_agents: int = Field(default=0)

    average_matching_time: float = Field(default=0.0)
    average_negotiation_time: float = Field(default=0.0)
    average_settlement_time: float = Field(default=0.0)
    success_rate: float = Field(default=0.0, ge=0, le=100.0)

    regional_distribution: dict[str, int] = Field(default={}, sa_column=Column(JSON))

    average_rating: float = Field(default=0.0, ge=1.0, le=5.0)
    dispute_rate: float = Field(default=0.0, ge=0, le=100.0)
    repeat_trade_rate: float = Field(default=0.0, ge=0, le=100.0)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    analytics_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    trends_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
