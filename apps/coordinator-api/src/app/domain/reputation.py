"""
Agent Reputation and Trust System Domain Models
Implements SQLModel definitions for agent reputation, trust scores, and economic metrics
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from uuid import uuid4
from enum import Enum

from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import DateTime, Float, Integer, Text


class ReputationLevel(str, Enum):
    """Agent reputation level enumeration"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    MASTER = "master"


class TrustScoreCategory(str, Enum):
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
    agent_id: str = Field(index=True, foreign_key="ai_agent_workflows.id")
    
    # Core reputation metrics
    trust_score: float = Field(default=500.0, ge=0, le=1000)  # 0-1000 scale
    reputation_level: ReputationLevel = Field(default=ReputationLevel.BEGINNER)
    performance_rating: float = Field(default=3.0, ge=1.0, le=5.0)  # 1-5 stars
    reliability_score: float = Field(default=50.0, ge=0, le=100.0)  # 0-100%
    community_rating: float = Field(default=3.0, ge=1.0, le=5.0)  # 1-5 stars
    
    # Economic metrics
    total_earnings: float = Field(default=0.0)  # Total AITBC earned
    transaction_count: int = Field(default=0)  # Total transactions
    success_rate: float = Field(default=0.0, ge=0, le=100.0)  # Success percentage
    dispute_count: int = Field(default=0)  # Number of disputes
    dispute_won_count: int = Field(default=0)  # Disputes won
    
    # Activity metrics
    jobs_completed: int = Field(default=0)
    jobs_failed: int = Field(default=0)
    average_response_time: float = Field(default=0.0)  # milliseconds
    uptime_percentage: float = Field(default=0.0, ge=0, le=100.0)
    
    # Geographic and service info
    geographic_region: str = Field(default="", max_length=50)
    service_categories: List[str] = Field(default=[], sa_column=Column(JSON))
    specialization_tags: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    
    # Additional metadata
    reputation_history: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    achievements: List[str] = Field(default=[], sa_column=Column(JSON))
    certifications: List[str] = Field(default=[], sa_column=Column(JSON))


class TrustScoreCalculation(SQLModel, table=True):
    """Trust score calculation records and factors"""
    
    __tablename__ = "trust_score_calculations"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"trust_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True, foreign_key="agent_reputation.id")
    
    # Calculation details
    category: TrustScoreCategory
    base_score: float = Field(ge=0, le=1000)
    weight_factor: float = Field(default=1.0, ge=0, le=10)
    adjusted_score: float = Field(ge=0, le=1000)
    
    # Contributing factors
    performance_factor: float = Field(default=1.0)
    reliability_factor: float = Field(default=1.0)
    community_factor: float = Field(default=1.0)
    security_factor: float = Field(default=1.0)
    economic_factor: float = Field(default=1.0)
    
    # Calculation metadata
    calculation_method: str = Field(default="weighted_average")
    confidence_level: float = Field(default=0.8, ge=0, le=1.0)
    
    # Timestamps
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
    effective_period: int = Field(default=86400)  # seconds
    
    # Additional data
    calculation_details: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class ReputationEvent(SQLModel, table=True):
    """Reputation-changing events and transactions"""
    
    __tablename__ = "reputation_events"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"event_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True, foreign_key="agent_reputation.id")
    
    # Event details
    event_type: str = Field(max_length=50)  # "job_completed", "dispute_resolved", etc.
    event_subtype: str = Field(default="", max_length=50)
    impact_score: float = Field(ge=-100, le=100)  # Positive or negative impact
    
    # Scoring details
    trust_score_before: float = Field(ge=0, le=1000)
    trust_score_after: float = Field(ge=0, le=1000)
    reputation_level_before: Optional[ReputationLevel] = None
    reputation_level_after: Optional[ReputationLevel] = None
    
    # Event context
    related_transaction_id: Optional[str] = None
    related_job_id: Optional[str] = None
    related_dispute_id: Optional[str] = None
    
    # Event metadata
    event_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    verification_status: str = Field(default="pending")  # pending, verified, rejected
    
    # Timestamps
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class AgentEconomicProfile(SQLModel, table=True):
    """Detailed economic profile for agents"""
    
    __tablename__ = "agent_economic_profiles"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"econ_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True, foreign_key="agent_reputation.id")
    
    # Earnings breakdown
    daily_earnings: float = Field(default=0.0)
    weekly_earnings: float = Field(default=0.0)
    monthly_earnings: float = Field(default=0.0)
    yearly_earnings: float = Field(default=0.0)
    
    # Performance metrics
    average_job_value: float = Field(default=0.0)
    peak_hourly_rate: float = Field(default=0.0)
    utilization_rate: float = Field(default=0.0, ge=0, le=100.0)
    
    # Market position
    market_share: float = Field(default=0.0, ge=0, le=100.0)
    competitive_ranking: int = Field(default=0)
    price_tier: str = Field(default="standard")  # budget, standard, premium
    
    # Risk metrics
    default_risk_score: float = Field(default=0.0, ge=0, le=100.0)
    volatility_score: float = Field(default=0.0, ge=0, le=100.0)
    liquidity_score: float = Field(default=0.0, ge=0, le=100.0)
    
    # Timestamps
    profile_date: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    # Historical data
    earnings_history: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    performance_history: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class CommunityFeedback(SQLModel, table=True):
    """Community feedback and ratings for agents"""
    
    __tablename__ = "community_feedback"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"feedback_{uuid4().hex[:8]}", primary_key=True)
    agent_id: str = Field(index=True, foreign_key="agent_reputation.id")
    
    # Feedback details
    reviewer_id: str = Field(index=True)
    reviewer_type: str = Field(default="client")  # client, provider, peer
    
    # Ratings
    overall_rating: float = Field(ge=1.0, le=5.0)
    performance_rating: float = Field(ge=1.0, le=5.0)
    communication_rating: float = Field(ge=1.0, le=5.0)
    reliability_rating: float = Field(ge=1.0, le=5.0)
    value_rating: float = Field(ge=1.0, le=5.0)
    
    # Feedback content
    feedback_text: str = Field(default="", max_length=1000)
    feedback_tags: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Verification
    verified_transaction: bool = Field(default=False)
    verification_weight: float = Field(default=1.0, ge=0.1, le=10.0)
    
    # Moderation
    moderation_status: str = Field(default="approved")  # approved, pending, rejected
    moderator_notes: str = Field(default="", max_length=500)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    helpful_votes: int = Field(default=0)
    
    # Additional metadata
    feedback_context: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class ReputationLevelThreshold(SQLModel, table=True):
    """Configuration for reputation level thresholds"""
    
    __tablename__ = "reputation_level_thresholds"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"threshold_{uuid4().hex[:8]}", primary_key=True)
    level: ReputationLevel
    
    # Threshold requirements
    min_trust_score: float = Field(ge=0, le=1000)
    min_performance_rating: float = Field(ge=1.0, le=5.0)
    min_reliability_score: float = Field(ge=0, le=100.0)
    min_transactions: int = Field(default=0)
    min_success_rate: float = Field(ge=0, le=100.0)
    
    # Benefits and restrictions
    max_concurrent_jobs: int = Field(default=1)
    priority_boost: float = Field(default=1.0)
    fee_discount: float = Field(default=0.0, ge=0, le=100.0)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)
    
    # Additional configuration
    level_requirements: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    level_benefits: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
