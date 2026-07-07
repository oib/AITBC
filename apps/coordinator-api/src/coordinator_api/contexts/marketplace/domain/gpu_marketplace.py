"""Persistent SQLModel tables for the GPU marketplace."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class GPURegistry(SQLModel, table=True):
    """Registered GPUs available in the marketplace."""

    __tablename__ = "gpu_registry"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"gpu_{uuid4().hex[:8]}", primary_key=True)
    miner_id: str = Field(index=True)
    model: str = Field(index=True)
    memory_gb: int = Field(default=0)
    cuda_version: str = Field(default="")
    region: str = Field(default="", index=True)
    price_per_hour: float = Field(default=0.0)
    status: str = Field(default="available", index=True)  # available, booked, offline
    capabilities: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    average_rating: float = Field(default=0.0)
    total_reviews: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False, index=True)


class GPUBooking(SQLModel, table=True):
    """Active and historical GPU bookings."""

    __tablename__ = "gpu_bookings"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"bk_{uuid4().hex[:10]}", primary_key=True)
    gpu_id: str = Field(index=True)
    client_id: str = Field(default="", index=True)
    job_id: str | None = Field(default=None, index=True)
    duration_hours: float = Field(default=0.0)
    total_cost: float = Field(default=0.0)
    status: str = Field(default="active", index=True)  # active, completed, cancelled
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


class GPUReview(SQLModel, table=True):
    """Reviews for GPUs."""

    __tablename__ = "gpu_reviews"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"rv_{uuid4().hex[:10]}", primary_key=True)
    gpu_id: str = Field(index=True)
    user_id: str = Field(default="")
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False, index=True)


class PriceHistory(SQLModel, table=True):
    """Historical price data for ML training and analysis."""

    __tablename__ = "price_history"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"ph_{uuid4().hex[:10]}", primary_key=True)
    resource_id: str = Field(index=True)
    resource_type: str = Field(default="gpu")
    price: float = Field(default=0.0)
    demand_level: float = Field(default=0.5)
    supply_level: float = Field(default=0.5)
    confidence: float = Field(default=0.8)
    strategy_used: str = Field(default="market_balance")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False, index=True)


class SearchHistory(SQLModel, table=True):
    """Track user search patterns for ML-based recommendations."""

    __tablename__ = "search_history"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"sh_{uuid4().hex[:10]}", primary_key=True)
    user_id: str = Field(index=True)
    search_query: str = Field(default="")
    filters: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    results_count: int = Field(default=0)
    clicked_resource_id: str | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False, index=True)


class ResourceEmbedding(SQLModel, table=True):
    """Vector embeddings for GPU resources for similarity search."""

    __tablename__ = "resource_embeddings"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"re_{uuid4().hex[:10]}", primary_key=True)
    resource_id: str = Field(index=True, unique=True)
    embedding: list[float] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    model_version: str = Field(default="v1.0")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


class UserProfile(SQLModel, table=True):
    """User preferences and behavior for personalized recommendations."""

    __tablename__ = "user_profiles"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"up_{uuid4().hex[:10]}", primary_key=True)
    user_id: str = Field(index=True, unique=True)
    preferred_gpu_models: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    preferred_regions: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    price_range_min: float = Field(default=0.0)
    price_range_max: float = Field(default=1000.0)
    min_memory_gb: int = Field(default=0)
    preferred_capabilities: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


class TrendData(SQLModel, table=True):
    """Historical trend data."""

    __tablename__ = "trend_data"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"td_{uuid4().hex[:10]}", primary_key=True)
    period_hours: int = Field(default=24)
    total_bookings: int = Field(default=0)
    bookings_per_hour: float = Field(default=0.0)
    avg_price: float = Field(default=0.0)
    avg_utilization: float = Field(default=0.0)
    trend_direction: str = Field(default="stable")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False, index=True)


class AnalyticsEvent(SQLModel, table=True):
    """Track marketplace events."""

    __tablename__ = "analytics_events"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"ae_{uuid4().hex[:10]}", primary_key=True)
    event_type: str = Field(index=True)
    resource_id: str = Field(index=True)
    user_id: str | None = Field(default=None, index=True)
    event_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False, index=True)


class ExternalProvider(SQLModel, table=True):
    """External provider configurations."""

    __tablename__ = "external_providers"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"ep_{uuid4().hex[:10]}", primary_key=True)
    provider_name: str = Field(index=True, unique=True)
    provider_type: str = Field(default="aws")  # aws, gcp, azure
    api_key: str = Field(default="")
    api_secret: str = Field(default="")
    region: str = Field(default="")
    enabled: bool = Field(default=True)
    sync_interval_minutes: int = Field(default=60)
    last_sync: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


class ProviderMapping(SQLModel, table=True):
    """Map external resources to internal resources."""

    __tablename__ = "provider_mappings"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"pm_{uuid4().hex[:10]}", primary_key=True)
    provider_id: str = Field(index=True)
    external_resource_id: str = Field(index=True)
    internal_resource_id: str = Field(index=True)
    mapping_type: str = Field(default="gpu")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


class SyncStatus(SQLModel, table=True):
    """Track synchronization status."""

    __tablename__ = "sync_status"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"ss_{uuid4().hex[:10]}", primary_key=True)
    provider_id: str = Field(index=True)
    status: str = Field(default="pending")  # pending, in_progress, completed, failed
    resources_synced: int = Field(default=0)
    resources_failed: int = Field(default=0)
    error_message: str | None = Field(default=None)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    completed_at: datetime | None = Field(default=None)


class Plugin(SQLModel, table=True):
    """Plugin metadata and configuration."""

    __tablename__ = "plugins"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"pl_{uuid4().hex[:10]}", primary_key=True)
    plugin_name: str = Field(index=True, unique=True)
    plugin_version: str = Field(default="1.0.0")
    plugin_type: str = Field(default="extension")  # extension, integration, analytics
    enabled: bool = Field(default=True)
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    description: str = Field(default="")
    author: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


class PluginConfig(SQLModel, table=True):
    """Plugin-specific configurations."""

    __tablename__ = "plugin_configs"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"pc_{uuid4().hex[:10]}", primary_key=True)
    plugin_id: str = Field(index=True)
    config_key: str = Field(index=True)
    config_value: str = Field(default="")
    config_type: str = Field(default="string")  # string, number, boolean, json
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
