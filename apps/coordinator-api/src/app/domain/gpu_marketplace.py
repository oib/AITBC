"""Persistent SQLModel tables for the GPU marketplace."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class GPUArchitecture(str, Enum):
    TURING = "turing"      # RTX 20 series
    AMPERE = "ampere"      # RTX 30 series
    ADA_LOVELACE = "ada_lovelace"  # RTX 40 series
    PASCAL = "pascal"      # GTX 10 series
    VOLTA = "volta"        # Titan V, Tesla V100
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
    cuda_cores: Optional[int] = Field(default=None)
    memory_gb: Optional[int] = Field(default=None)
    memory_bandwidth_gbps: Optional[float] = Field(default=None)
    tensor_cores: Optional[int] = Field(default=None)
    base_clock_mhz: Optional[int] = Field(default=None)
    boost_clock_mhz: Optional[int] = Field(default=None)

    # Edge optimization metrics
    power_consumption_w: Optional[float] = Field(default=None)
    thermal_design_power_w: Optional[float] = Field(default=None)
    noise_level_db: Optional[float] = Field(default=None)

    # Performance characteristics
    fp32_tflops: Optional[float] = Field(default=None)
    fp16_tflops: Optional[float] = Field(default=None)
    int8_tops: Optional[float] = Field(default=None)

    # Edge-specific optimizations
    low_latency_mode: bool = Field(default=False)
    mobile_optimized: bool = Field(default=False)
    thermal_throttling_resistance: Optional[float] = Field(default=None)

    # Compatibility flags
    supported_cuda_versions: list = Field(default_factory=list, sa_column=Column(JSON, nullable=True))
    supported_tensorrt_versions: list = Field(default_factory=list, sa_column=Column(JSON, nullable=True))
    supported_ollama_models: list = Field(default_factory=list, sa_column=Column(JSON, nullable=True))

    # Pricing and availability
    market_price_usd: Optional[float] = Field(default=None)
    edge_premium_multiplier: float = Field(default=1.0)
    availability_score: float = Field(default=1.0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EdgeGPUMetrics(SQLModel, table=True):
    """Real-time edge GPU performance metrics"""
    __tablename__ = "edge_gpu_metrics"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"egm_{uuid4().hex[:8]}", primary_key=True)
    gpu_id: str = Field(foreign_key="gpuregistry.id")

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
    city: Optional[str] = Field(default=None)
    isp: Optional[str] = Field(default=None)
    connection_type: Optional[str] = Field(default=None)

    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)


class GPUBooking(SQLModel, table=True):
    """Active and historical GPU bookings."""
    __tablename__ = "gpu_bookings"
    __table_args__ = {"extend_existing": True}
    
    id: str = Field(default_factory=lambda: f"bk_{uuid4().hex[:10]}", primary_key=True)
    gpu_id: str = Field(index=True)
    client_id: str = Field(default="", index=True)
    job_id: Optional[str] = Field(default=None, index=True)
    duration_hours: float = Field(default=0.0)
    total_cost: float = Field(default=0.0)
    status: str = Field(default="active", index=True)  # active, completed, cancelled
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = Field(default=None)
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
