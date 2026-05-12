"""
Global Marketplace Domain Models
Domain models for global marketplace operations, multi-region support, and cross-chain integration
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, SQLModel


class MarketplaceStatus(StrEnum):
    """Global marketplace offer status"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class RegionStatus(StrEnum):
    """Global marketplace region status"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    DEPRECATED = "deprecated"


class MarketplaceRegion(SQLModel, table=True):
    """Global marketplace region configuration"""

    __tablename__ = "marketplace_regions"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"region_{uuid4().hex[:8]}", primary_key=True)
    region_code: str = Field(index=True, unique=True)  # us-east-1, eu-west-1, etc.
    region_name: str = Field(index=True)
    geographic_area: str = Field(default="global")

    # Configuration
    base_currency: str = Field(default="USD")
    timezone: str = Field(default="UTC")
    language: str = Field(default="en")

    # Load balancing
    load_factor: float = Field(default=1.0, ge=0.1, le=10.0)
    max_concurrent_requests: int = Field(default=1000)
    priority_weight: float = Field(default=1.0, ge=0.1, le=10.0)

    # Status and health
    status: RegionStatus = Field(default=RegionStatus.ACTIVE)
    health_score: float = Field(default=1.0, ge=0.0, le=1.0)
    last_health_check: datetime | None = Field(default=None)

    # API endpoints
    api_endpoint: str = Field(default="")
    websocket_endpoint: str = Field(default="")
    blockchain_rpc_endpoints: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))

    # Performance metrics
    average_response_time: float = Field(default=0.0)
    request_rate: float = Field(default=0.0)
    error_rate: float = Field(default=0.0)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Indexes
    __table_args__ = {
        "extend_existing": True,
    }
    # Indexes are created separately via SQLAlchemy Index objects


class GlobalMarketplaceConfig(SQLModel, table=True):
    """Global marketplace configuration settings"""

    __tablename__ = "global_marketplace_configs"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"config_{uuid4().hex[:8]}", primary_key=True)
    config_key: str = Field(index=True, unique=True)
    config_value: str = Field(default="")  # Changed from Any to str
    config_type: str = Field(default="string")  # string, number, boolean, json

    # Configuration metadata
    description: str = Field(default="")
    category: str = Field(default="general")
    is_public: bool = Field(default=False)
    is_encrypted: bool = Field(default=False)

    # Validation rules
    min_value: float | None = Field(default=None)
    max_value: float | None = Field(default=None)
    allowed_values: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_modified_by: str | None = Field(default=None)

    # Indexes
    __table_args__ = {
        "extend_existing": True,
    }


class GlobalMarketplaceOffer(SQLModel, table=True):
    """Global marketplace offer with multi-region support"""

    __tablename__ = "global_marketplace_offers"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"offer_{uuid4().hex[:8]}", primary_key=True)
    original_offer_id: str = Field(index=True)  # Reference to original marketplace offer

    # Global offer data
    agent_id: str = Field(index=True)
    service_type: str = Field(index=True)  # gpu, compute, storage, etc.
    resource_specification: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Pricing (multi-currency support)
    base_price: float = Field(default=0.0)
    currency: str = Field(default="USD")
    price_per_region: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    dynamic_pricing_enabled: bool = Field(default=False)

    # Availability
    total_capacity: int = Field(default=0)
    available_capacity: int = Field(default=0)
    regions_available: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Global status
    global_status: MarketplaceStatus = Field(default=MarketplaceStatus.ACTIVE)
    region_statuses: dict[str, MarketplaceStatus] = Field(default_factory=dict, sa_column=Column(JSON))

    # Quality metrics
    global_rating: float = Field(default=0.0, ge=0.0, le=5.0)
    total_transactions: int = Field(default=0)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)

    # Cross-chain support
    supported_chains: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    cross_chain_pricing: dict[int, float] = Field(default_factory=dict, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = Field(default=None)

    # Indexes
    __table_args__ = {
        "extend_existing": True,
    }


class GlobalMarketplaceTransaction(SQLModel, table=True):
    """Global marketplace transaction with cross-chain support"""

    __tablename__ = "global_marketplace_transactions"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"tx_{uuid4().hex[:8]}", primary_key=True)
    transaction_hash: str | None = Field(index=True)

    # Transaction participants
    buyer_id: str = Field(index=True)
    seller_id: str = Field(index=True)
    offer_id: str = Field(index=True)

    # Transaction details
    service_type: str = Field(index=True)
    quantity: int = Field(default=1)
    unit_price: float = Field(default=0.0)
    total_amount: float = Field(default=0.0)
    currency: str = Field(default="USD")

    # Cross-chain information
    source_chain: int | None = Field(default=None)
    target_chain: int | None = Field(default=None)
    bridge_transaction_id: str | None = Field(default=None)
    cross_chain_fee: float = Field(default=0.0)

    # Regional information
    source_region: str = Field(default="global")
    target_region: str = Field(default="global")
    regional_fees: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))

    # Transaction status
    status: str = Field(default="pending")  # pending, confirmed, completed, failed, cancelled
    payment_status: str = Field(default="pending")  # pending, paid, refunded
    delivery_status: str = Field(default="pending")  # pending, delivered, failed

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confirmed_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)

    # Transaction metadata
    transaction_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Indexes
    __table_args__ = {
        "extend_existing": True,
        # # # "indexes": [
#    #        # Index(        Index("idx_global_tx_buyer", "buyer_id"),)
#    #        # Index(        Index("idx_global_tx_seller", "seller_id"),)
#    #        # Index(        Index("idx_global_tx_offer", "offer_id"),)
#    #        # Index(        Index("idx_global_tx_status", "status"),)
#    #        # Index(        Index("idx_global_tx_created", "created_at"),)
#    #        # Index(        Index("idx_global_tx_chain", "source_chain", "target_chain"),)
###        ]
    }


class GlobalMarketplaceAnalytics(SQLModel, table=True):
    """Global marketplace analytics and metrics"""

    __tablename__ = "global_marketplace_analytics"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"analytics_{uuid4().hex[:8]}", primary_key=True)

    # Analytics period
    period_type: str = Field(default="hourly")  # hourly, daily, weekly, monthly
    period_start: datetime = Field(index=True)
    period_end: datetime = Field(index=True)
    region: str | None = Field(default="global", index=True)

    # Marketplace metrics
    total_offers: int = Field(default=0)
    total_transactions: int = Field(default=0)
    total_volume: float = Field(default=0.0)
    average_price: float = Field(default=0.0)

    # Performance metrics
    average_response_time: float = Field(default=0.0)
    success_rate: float = Field(default=0.0)
    error_rate: float = Field(default=0.0)

    # User metrics
    active_buyers: int = Field(default=0)
    active_sellers: int = Field(default=0)
    new_users: int = Field(default=0)

    # Cross-chain metrics
    cross_chain_transactions: int = Field(default=0)
    cross_chain_volume: float = Field(default=0.0)
    supported_chains: list[int] = Field(default_factory=list, sa_column=Column(JSON))

    # Regional metrics
    regional_distribution: dict[str, int] = Field(default_factory=dict, sa_column=Column(JSON))
    regional_performance: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))

    # Additional analytics data
    analytics_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Indexes
    __table_args__ = {
        "extend_existing": True,
        # # # "indexes": [
#    #        # Index(        Index("idx_global_analytics_period", "period_type", "period_start"),)
#    #        # Index(        Index("idx_global_analytics_region", "region"),)
#    #        # Index(        Index("idx_global_analytics_created", "created_at"),)
###        ]
    }


class GlobalMarketplaceGovernance(SQLModel, table=True):
    """Global marketplace governance and rules"""

    __tablename__ = "global_marketplace_governance"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"gov_{uuid4().hex[:8]}", primary_key=True)

    # Governance rule
    rule_type: str = Field(index=True)  # pricing, security, compliance, quality
    rule_name: str = Field(index=True)
    rule_description: str = Field(default="")

    # Rule configuration
    rule_parameters: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    conditions: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Scope and applicability
    global_scope: bool = Field(default=True)
    applicable_regions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    applicable_services: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Enforcement
    is_active: bool = Field(default=True)
    enforcement_level: str = Field(default="warning")  # warning, restriction, ban
    penalty_parameters: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Governance metadata
    created_by: str = Field(default="")
    approved_by: str | None = Field(default=None)
    version: int = Field(default=1)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effective_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = Field(default=None)

    # Indexes
    __table_args__ = {
        "extend_existing": True,
        # # # "indexes": [
#    #        # Index(        Index("idx_global_gov_rule_type", "rule_type"),)
#    #        # Index(        Index("idx_global_gov_active", "is_active"),)
#    #        # Index(        Index("idx_global_gov_effective", "effective_from", "expires_at"),)
###        ]
    }


# Request/Response Models for API
class GlobalMarketplaceOfferRequest(SQLModel):
    """Request model for creating global marketplace offers"""

    agent_id: str
    service_type: str
    resource_specification: dict[str, Any]
    base_price: float
    currency: str = "USD"
    total_capacity: int
    regions_available: list[str] = []
    supported_chains: list[int] = []
    dynamic_pricing_enabled: bool = False
    expires_at: datetime | None = None


class GlobalMarketplaceTransactionRequest(SQLModel):
    """Request model for creating global marketplace transactions"""

    buyer_id: str
    offer_id: str
    quantity: int = 1
    source_region: str = "global"
    target_region: str = "global"
    payment_method: str = "crypto"
    source_chain: int | None = None
    target_chain: int | None = None


class GlobalMarketplaceAnalyticsRequest(SQLModel):
    """Request model for global marketplace analytics"""

    period_type: str = "daily"
    start_date: datetime
    end_date: datetime
    region: str | None = "global"
    metrics: list[str] = []
    include_cross_chain: bool = False
    include_regional: bool = False


# Response Models
class GlobalMarketplaceOfferResponse(SQLModel):
    """Response model for global marketplace offers"""

    id: str
    agent_id: str
    service_type: str
    resource_specification: dict[str, Any]
    base_price: float
    currency: str
    price_per_region: dict[str, float]
    total_capacity: int
    available_capacity: int
    regions_available: list[str]
    global_status: MarketplaceStatus
    global_rating: float
    total_transactions: int
    success_rate: float
    supported_chains: list[int]
    cross_chain_pricing: dict[int, float]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None


class GlobalMarketplaceTransactionResponse(SQLModel):
    """Response model for global marketplace transactions"""

    id: str
    transaction_hash: str | None
    buyer_id: str
    seller_id: str
    offer_id: str
    service_type: str
    quantity: int
    unit_price: float
    total_amount: float
    currency: str
    source_chain: int | None
    target_chain: int | None
    cross_chain_fee: float
    source_region: str
    target_region: str
    status: str
    payment_status: str
    delivery_status: str
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None
    completed_at: datetime | None


class GlobalMarketplaceAnalyticsResponse(SQLModel):
    """Response model for global marketplace analytics"""

    period_type: str
    period_start: datetime
    period_end: datetime
    region: str
    total_offers: int
    total_transactions: int
    total_volume: float
    average_price: float
    average_response_time: float
    success_rate: float
    active_buyers: int
    active_sellers: int
    cross_chain_transactions: int
    cross_chain_volume: float
    regional_distribution: dict[str, int]
    regional_performance: dict[str, float]
    generated_at: datetime
