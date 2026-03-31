"""Persistent SQLModel tables for the GPU marketplace."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class GPUArchitecture(StrEnum):
    TURING = "turing"  # RTX 20 series
    AMPERE = "ampere"  # RTX 30 series
    ADA_LOVELACE = "ada_lovelace"  # RTX 40 series
    PASCAL = "pascal"  # GTX 10 series
    VOLTA = "volta"  # Titan V, Tesla V100
    UNKNOWN = "unknown"


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
    capabilities: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    average_rating: float = Field(default=0.0)
    total_reviews: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)


class ConsumerGPUProfile(SQLModel, table=True):
    """Consumer GPU optimization profiles for edge computing"""

    __tablename__ = "consumer_gpu_profiles"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"cgp_{uuid4().hex[:8]}", primary_key=True)
    gpu_model: str = Field(index=True)
    architecture: GPUArchitecture = Field(default=GPUArchitecture.UNKNOWN)
    consumer_grade: bool = Field(default=True)
    edge_optimized: bool = Field(default=False)

    # Hardware specifications
    cuda_cores: int | None = Field(default=None)
    memory_gb: int | None = Field(default=None)
    memory_bandwidth_gbps: float | None = Field(default=None)
    tensor_cores: int | None = Field(default=None)
    base_clock_mhz: int | None = Field(default=None)
    boost_clock_mhz: int | None = Field(default=None)

    # Edge optimization metrics
    power_consumption_w: float | None = Field(default=None)
    thermal_design_power_w: float | None = Field(default=None)
    noise_level_db: float | None = Field(default=None)

    # Performance characteristics
    fp32_tflops: float | None = Field(default=None)
    fp16_tflops: float | None = Field(default=None)
    int8_tops: float | None = Field(default=None)

    # Edge-specific optimizations
    low_latency_mode: bool = Field(default=False)
    mobile_optimized: bool = Field(default=False)
    thermal_throttling_resistance: float | None = Field(default=None)

    # Compatibility flags
    supported_cuda_versions: list = Field(default_factory=list, sa_column=Column(JSON, nullable=True))
    supported_tensorrt_versions: list = Field(default_factory=list, sa_column=Column(JSON, nullable=True))
    supported_ollama_models: list = Field(default_factory=list, sa_column=Column(JSON, nullable=True))

    # Pricing and availability
    market_price_usd: float | None = Field(default=None)
    edge_premium_multiplier: float = Field(default=1.0)
    availability_score: float = Field(default=1.0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EdgeGPUMetrics(SQLModel, table=True):
    """Real-time edge GPU performance metrics"""

    __tablename__ = "edge_gpu_metrics"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"egm_{uuid4().hex[:8]}", primary_key=True)
    gpu_id: str = Field(foreign_key="gpu_registry.id")

    # Latency metrics
    network_latency_ms: float = Field()
    compute_latency_ms: float = Field()
    total_latency_ms: float = Field()

    # Resource utilization
    gpu_utilization_percent: float = Field()
    memory_utilization_percent: float = Field()
    power_draw_w: float = Field()
    temperature_celsius: float = Field()

    # Edge-specific metrics
    thermal_throttling_active: bool = Field(default=False)
    power_limit_active: bool = Field(default=False)
    clock_throttling_active: bool = Field(default=False)

    # Geographic and network info
    region: str = Field()
    city: str | None = Field(default=None)
    isp: str | None = Field(default=None)
    connection_type: str | None = Field(default=None)

    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)


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
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class GPUReview(SQLModel, table=True):
    """Reviews for GPUs."""

    __tablename__ = "gpu_reviews"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"rv_{uuid4().hex[:10]}", primary_key=True)
    gpu_id: str = Field(index=True)
    user_id: str = Field(default="")
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)
