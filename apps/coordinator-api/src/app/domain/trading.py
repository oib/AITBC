"""
Agent-to-Agent Trading Protocol Domain Models
Implements SQLModel definitions for P2P trading, matching, negotiation, and settlement
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from uuid import uuid4
from enum import Enum

from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import DateTime, Float, Integer, Text


class TradeStatus(str, Enum):
    """Trade status enumeration"""
    OPEN = "open"
    MATCHING = "matching"
    NEGOTIATING = "negotiating"
    AGREED = "agreed"
    SETTLING = "settling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TradeType(str, Enum):
    """Trade type enumeration"""
    AI_POWER = "ai_power"
    COMPUTE_RESOURCES = "compute_resources"
    DATA_SERVICES = "data_services"
    MODEL_SERVICES = "model_services"
    INFERENCE_TASKS = "inference_tasks"
    TRAINING_TASKS = "training_tasks"


class NegotiationStatus(str, Enum):
    """Negotiation status enumeration"""
    PENDING = "pending"
    ACTIVE = "active"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTERED = "countered"
    EXPIRED = "expired"


class SettlementType(str, Enum):
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
    
    # Request details
    buyer_agent_id: str = Field(index=True)
    trade_type: TradeType
    title: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    
    # Requirements and specifications
    requirements: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    specifications: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    constraints: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Pricing and terms
    budget_range: Dict[str, float] = Field(default={}, sa_column=Column(JSON))  # min, max
    preferred_terms: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    negotiation_flexible: bool = Field(default=True)
    
    # Timing and duration
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_hours: Optional[int] = None
    urgency_level: str = Field(default="normal")  # low, normal, high, urgent
    
    # Geographic and service constraints
    preferred_regions: List[str] = Field(default=[], sa_column=Column(JSON))
    excluded_regions: List[str] = Field(default=[], sa_column=Column(JSON))
    service_level_required: str = Field(default="standard")  # basic, standard, premium
    
    # Status and metadata
    status: TradeStatus = Field(default=TradeStatus.OPEN)
    priority: int = Field(default=5, ge=1, le=10)  # 1 = highest priority
    
    # Matching and negotiation
    match_count: int = Field(default=0)
    negotiation_count: int = Field(default=0)
    best_match_score: float = Field(default=0.0)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    
    # Additional metadata
    tags: List[str] = Field(default=[], sa_column=Column(JSON))
    trading_meta_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class TradeMatch(SQLModel, table=True):
    """Trade match between buyer request and seller offer"""
    
    __tablename__ = "trade_matches"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"match_{uuid4().hex[:8]}", primary_key=True)
    match_id: str = Field(unique=True, index=True)
    
    # Match participants
    request_id: str = Field(index=True, foreign_key="trade_requests.request_id")
    buyer_agent_id: str = Field(index=True)
    seller_agent_id: str = Field(index=True)
    
    # Matching details
    match_score: float = Field(ge=0, le=100)  # 0-100 compatibility score
    confidence_level: float = Field(ge=0, le=1)  # 0-1 confidence in match
    
    # Compatibility factors
    price_compatibility: float = Field(ge=0, le=100)
    timing_compatibility: float = Field(ge=0, le=100)
    specification_compatibility: float = Field(ge=0, le=100)
    reputation_compatibility: float = Field(ge=0, le=100)
    geographic_compatibility: float = Field(ge=0, le=100)
    
    # Seller offer details
    seller_offer: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    proposed_terms: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Status and interaction
    status: TradeStatus = Field(default=TradeStatus.MATCHING)
    buyer_response: Optional[str] = None  # interested, not_interested, negotiating
    seller_response: Optional[str] = None  # accepted, rejected, countered
    
    # Negotiation initiation
    negotiation_initiated: bool = Field(default=False)
    negotiation_initiator: Optional[str] = None  # buyer, seller
    initial_terms: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    last_interaction: Optional[datetime] = None
    
    # Additional data
    match_factors: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    interaction_history: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class TradeNegotiation(SQLModel, table=True):
    """Negotiation process between buyer and seller"""
    
    __tablename__ = "trade_negotiations"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"neg_{uuid4().hex[:8]}", primary_key=True)
    negotiation_id: str = Field(unique=True, index=True)
    
    # Negotiation participants
    match_id: str = Field(index=True, foreign_key="trade_matches.match_id")
    buyer_agent_id: str = Field(index=True)
    seller_agent_id: str = Field(index=True)
    
    # Negotiation details
    status: NegotiationStatus = Field(default=NegotiationStatus.PENDING)
    negotiation_round: int = Field(default=1)
    max_rounds: int = Field(default=5)
    
    # Terms and conditions
    current_terms: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    initial_terms: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    final_terms: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Negotiation parameters
    price_range: Dict[str, float] = Field(default={}, sa_column=Column(JSON))
    service_level_agreements: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    delivery_terms: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    payment_terms: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Negotiation metrics
    concession_count: int = Field(default=0)
    counter_offer_count: int = Field(default=0)
    agreement_score: float = Field(default=0.0, ge=0, le=100)
    
    # AI negotiation assistance
    ai_assisted: bool = Field(default=True)
    negotiation_strategy: str = Field(default="balanced")  # aggressive, balanced, cooperative
    auto_accept_threshold: float = Field(default=85.0, ge=0, le=100)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    last_offer_at: Optional[datetime] = None
    
    # Additional data
    negotiation_history: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    ai_recommendations: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class TradeAgreement(SQLModel, table=True):
    """Final trade agreement between buyer and seller"""
    
    __tablename__ = "trade_agreements"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"agree_{uuid4().hex[:8]}", primary_key=True)
    agreement_id: str = Field(unique=True, index=True)
    
    # Agreement participants
    negotiation_id: str = Field(index=True, foreign_key="trade_negotiations.negotiation_id")
    buyer_agent_id: str = Field(index=True)
    seller_agent_id: str = Field(index=True)
    
    # Agreement details
    trade_type: TradeType
    title: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    
    # Final terms and conditions
    agreed_terms: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    specifications: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    service_level_agreement: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Pricing and payment
    total_price: float = Field(ge=0)
    currency: str = Field(default="AITBC")
    payment_schedule: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    settlement_type: SettlementType
    
    # Delivery and performance
    delivery_timeline: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    performance_metrics: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    quality_standards: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Legal and compliance
    terms_and_conditions: str = Field(default="", max_length=5000)
    compliance_requirements: List[str] = Field(default=[], sa_column=Column(JSON))
    dispute_resolution: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Status and execution
    status: TradeStatus = Field(default=TradeStatus.AGREED)
    execution_status: str = Field(default="pending")  # pending, active, completed, failed
    completion_percentage: float = Field(default=0.0, ge=0, le=100)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    signed_at: datetime = Field(default_factory=datetime.utcnow)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Additional data
    agreement_document: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    attachments: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class TradeSettlement(SQLModel, table=True):
    """Trade settlement and payment processing"""
    
    __tablename__ = "trade_settlements"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"settle_{uuid4().hex[:8]}", primary_key=True)
    settlement_id: str = Field(unique=True, index=True)
    
    # Settlement reference
    agreement_id: str = Field(index=True, foreign_key="trade_agreements.agreement_id")
    buyer_agent_id: str = Field(index=True)
    seller_agent_id: str = Field(index=True)
    
    # Settlement details
    settlement_type: SettlementType
    total_amount: float = Field(ge=0)
    currency: str = Field(default="AITBC")
    
    # Payment processing
    payment_status: str = Field(default="pending")  # pending, processing, completed, failed
    transaction_id: Optional[str] = None
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
    
    # Escrow details (if applicable)
    escrow_enabled: bool = Field(default=False)
    escrow_address: Optional[str] = None
    escrow_release_conditions: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Milestone payments (if applicable)
    milestone_payments: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    completed_milestones: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Fees and deductions
    platform_fee: float = Field(default=0.0)
    processing_fee: float = Field(default=0.0)
    gas_fee: float = Field(default=0.0)
    net_amount_seller: float = Field(ge=0)
    
    # Status and timestamps
    status: TradeStatus = Field(default=TradeStatus.SETTLING)
    initiated_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    
    # Dispute and resolution
    dispute_raised: bool = Field(default=False)
    dispute_details: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    resolution_details: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Additional data
    settlement_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    audit_trail: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class TradeFeedback(SQLModel, table=True):
    """Trade feedback and rating system"""
    
    __tablename__ = "trade_feedback"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"feedback_{uuid4().hex[:8]}", primary_key=True)
    
    # Feedback reference
    agreement_id: str = Field(index=True, foreign_key="trade_agreements.agreement_id")
    reviewer_agent_id: str = Field(index=True)
    reviewed_agent_id: str = Field(index=True)
    reviewer_role: str = Field(default="buyer")  # buyer, seller
    
    # Ratings
    overall_rating: float = Field(ge=1.0, le=5.0)
    communication_rating: float = Field(ge=1.0, le=5.0)
    performance_rating: float = Field(ge=1.0, le=5.0)
    timeliness_rating: float = Field(ge=1.0, le=5.0)
    value_rating: float = Field(ge=1.0, le=5.0)
    
    # Feedback content
    feedback_text: str = Field(default="", max_length=1000)
    feedback_tags: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Trade specifics
    trade_category: str = Field(default="general")
    trade_complexity: str = Field(default="medium")  # simple, medium, complex
    trade_duration: Optional[int] = None  # in hours
    
    # Verification and moderation
    verified_trade: bool = Field(default=True)
    moderation_status: str = Field(default="approved")  # approved, pending, rejected
    moderator_notes: str = Field(default="", max_length=500)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    trade_completed_at: datetime
    
    # Additional data
    feedback_context: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    performance_metrics: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class TradingAnalytics(SQLModel, table=True):
    """P2P trading system analytics and metrics"""
    
    __tablename__ = "trading_analytics"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"analytics_{uuid4().hex[:8]}", primary_key=True)
    
    # Analytics period
    period_type: str = Field(default="daily")  # daily, weekly, monthly
    period_start: datetime
    period_end: datetime
    
    # Trade volume metrics
    total_trades: int = Field(default=0)
    completed_trades: int = Field(default=0)
    failed_trades: int = Field(default=0)
    cancelled_trades: int = Field(default=0)
    
    # Financial metrics
    total_trade_volume: float = Field(default=0.0)
    average_trade_value: float = Field(default=0.0)
    total_platform_fees: float = Field(default=0.0)
    
    # Trade type distribution
    trade_type_distribution: Dict[str, int] = Field(default={}, sa_column=Column(JSON))
    
    # Agent metrics
    active_buyers: int = Field(default=0)
    active_sellers: int = Field(default=0)
    new_agents: int = Field(default=0)
    
    # Performance metrics
    average_matching_time: float = Field(default=0.0)  # minutes
    average_negotiation_time: float = Field(default=0.0)  # minutes
    average_settlement_time: float = Field(default=0.0)  # minutes
    success_rate: float = Field(default=0.0, ge=0, le=100.0)
    
    # Geographic distribution
    regional_distribution: Dict[str, int] = Field(default={}, sa_column=Column(JSON))
    
    # Quality metrics
    average_rating: float = Field(default=0.0, ge=1.0, le=5.0)
    dispute_rate: float = Field(default=0.0, ge=0, le=100.0)
    repeat_trade_rate: float = Field(default=0.0, ge=0, le=100.0)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Additional analytics data
    analytics_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    trends_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
