"""
Global Marketplace Domain Models
Domain models for global marketplace operations, multi-region support, and cross-chain integration
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

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
    region_code: str = Field(index=True, unique=True)
    region_name: str = Field(index=True)
    geographic_area: str = Field(default="global")

    base_currency: str = Field(default="USD")
    timezone: str = Field(default="UTC")
    language: str = Field(default="en")

    load_factor: float = Field(default=1.0, ge=0.1, le=10.0)
    max_concurrent_requests: int = Field(default=1000)
    priority_weight: float = Field(default=1.0, ge=0.1, le=10.0)

    status: RegionStatus = Field(default=RegionStatus.ACTIVE)
    health_score: float = Field(default=1.0, ge=0.0, le=1.0)
    last_health_check: datetime | None = Field(default=None)

    api_endpoint: str = Field(default="")
    websocket_endpoint: str = Field(default="")
    blockchain_rpc_endpoints: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))

    average_response_time: float = Field(default=0.0)
    request_rate: float = Field(default=0.0)
    error_rate: float = Field(default=0.0)

    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))


class GlobalMarketplaceConfig(SQLModel, table=True):
    """Global marketplace configuration settings"""

    __tablename__ = "global_marketplace_configs"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"config_{uuid4().hex[:8]}", primary_key=True)
    config_key: str = Field(index=True, unique=True)
    config_value: str = Field(default="")
    config_type: str = Field(default="string")

    description: str = Field(default="")
    category: str = Field(default="general")
    is_public: bool = Field(default=False)
    is_encrypted: bool = Field(default=False)

    min_value: float | None = Field(default=None)
    max_value: float | None = Field(default=None)
    allowed_values: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    last_modified_by: str | None = Field(default=None)


class GlobalMarketplaceOffer(SQLModel, table=True):
    """Global marketplace offer with multi-region support"""

    __tablename__ = "global_marketplace_offers"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"offer_{uuid4().hex[:8]}", primary_key=True)
    original_offer_id: str = Field(index=True)

    agent_id: str = Field(index=True)
    service_type: str = Field(index=True)
    resource_specification: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    base_price: float = Field(default=0.0)
    currency: str = Field(default="USD")
    price_per_region: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    dynamic_pricing_enabled: bool = Field(default=False)

    total_capacity: int = Field(default=0)
    available_capacity: int = Field(default=0)
    regions_available: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    global_status: MarketplaceStatus = Field(default=MarketplaceStatus.ACTIVE)
    region_statuses: dict[str, MarketplaceStatus] = Field(default_factory=dict, sa_column=Column(JSON))

    global_rating: float = Field(default=0.0, ge=0.0, le=5.0)
    total_transactions: int = Field(default=0)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)

    supported_chains: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    cross_chain_pricing: dict[int, float] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    expires_at: datetime | None = Field(default=None)


class GlobalMarketplaceTransaction(SQLModel, table=True):
    """Global marketplace transaction with cross-chain support"""

    __tablename__ = "global_marketplace_transactions"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"tx_{uuid4().hex[:8]}", primary_key=True)
    transaction_hash: str | None = Field(index=True)

    buyer_id: str = Field(index=True)
    seller_id: str = Field(index=True)
    offer_id: str = Field(index=True)

    service_type: str = Field(index=True)
    quantity: int = Field(default=1)
    unit_price: float = Field(default=0.0)
    total_amount: float = Field(default=0.0)
    currency: str = Field(default="USD")

    source_chain: int | None = Field(default=None)
    target_chain: int | None = Field(default=None)
    bridge_transaction_id: str | None = Field(default=None)
    cross_chain_fee: float = Field(default=0.0)

    source_region: str = Field(default="global")
    target_region: str = Field(default="global")
    regional_fees: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))

    status: str = Field(default="pending")
    payment_status: str = Field(default="pending")
    delivery_status: str = Field(default="pending")

    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    confirmed_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)

    transaction_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
