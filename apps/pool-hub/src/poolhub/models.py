from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Any
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from uuid import uuid4


class ServiceType(str, Enum):
    """Supported service types"""

    WHISPER = "whisper"
    STABLE_DIFFUSION = "stable_diffusion"
    LLM_INFERENCE = "llm_inference"
    FFMPEG = "ffmpeg"
    BLENDER = "blender"


class Base(DeclarativeBase):
    pass


class Miner(Base):
    __tablename__ = "miners"

    miner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    api_key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.now(datetime.UTC)
    )
    last_seen_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    addr: Mapped[str] = mapped_column(String(256))
    proto: Mapped[str] = mapped_column(String(32))
    gpu_vram_gb: Mapped[float] = mapped_column(Float)
    gpu_name: Mapped[Optional[str]] = mapped_column(String(128))
    cpu_cores: Mapped[int] = mapped_column(Integer)
    ram_gb: Mapped[float] = mapped_column(Float)
    max_parallel: Mapped[int] = mapped_column(Integer)
    base_price: Mapped[float] = mapped_column(Float)
    tags: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict)
    capabilities: Mapped[List[str]] = mapped_column(JSON, default=list)
    trust_score: Mapped[float] = mapped_column(Float, default=0.5)
    region: Mapped[Optional[str]] = mapped_column(String(64))

    status: Mapped["MinerStatus"] = relationship(
        back_populates="miner", cascade="all, delete-orphan", uselist=False
    )
    feedback: Mapped[List["Feedback"]] = relationship(
        back_populates="miner", cascade="all, delete-orphan"
    )


class MinerStatus(Base):
    __tablename__ = "miner_status"

    miner_id: Mapped[str] = mapped_column(
        ForeignKey("miners.miner_id", ondelete="CASCADE"), primary_key=True
    )
    queue_len: Mapped[int] = mapped_column(Integer, default=0)
    busy: Mapped[bool] = mapped_column(Boolean, default=False)
    avg_latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    temp_c: Mapped[Optional[int]] = mapped_column(Integer)
    mem_free_gb: Mapped[Optional[float]] = mapped_column(Float)
    uptime_pct: Mapped[Optional[float]] = mapped_column(Float)  # SLA metric
    last_heartbeat_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.now(datetime.UTC), onupdate=dt.datetime.now(datetime.UTC)
    )

    miner: Mapped[Miner] = relationship(back_populates="status")


class MatchRequest(Base):
    __tablename__ = "match_requests"

    id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requirements: Mapped[Dict[str, object]] = mapped_column(JSON, nullable=False)
    hints: Mapped[Dict[str, object]] = mapped_column(JSON, default=dict)
    top_k: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.now(datetime.UTC)
    )

    results: Mapped[List["MatchResult"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class MatchResult(Base):
    __tablename__ = "match_results"

    id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    request_id: Mapped[PGUUID] = mapped_column(
        ForeignKey("match_requests.id", ondelete="CASCADE"), index=True
    )
    miner_id: Mapped[str] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float)
    explain: Mapped[Optional[str]] = mapped_column(Text)
    eta_ms: Mapped[Optional[int]] = mapped_column(Integer)
    price: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.now(datetime.UTC)
    )

    request: Mapped[MatchRequest] = relationship(back_populates="results")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    miner_id: Mapped[str] = mapped_column(
        ForeignKey("miners.miner_id", ondelete="CASCADE"), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    fail_code: Mapped[Optional[str]] = mapped_column(String(64))
    tokens_spent: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.now(datetime.UTC)
    )

    miner: Mapped[Miner] = relationship(back_populates="feedback")


class ServiceConfig(Base):
    """Service configuration for a miner"""

    __tablename__ = "service_configs"

    id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    miner_id: Mapped[str] = mapped_column(
        ForeignKey("miners.miner_id", ondelete="CASCADE"), nullable=False
    )
    service_type: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    pricing: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    capabilities: Mapped[List[str]] = mapped_column(JSON, default=list)
    max_concurrent: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.now(datetime.UTC)
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.now(datetime.UTC), onupdate=dt.datetime.now(datetime.UTC)
    )

    # Add unique constraint for miner_id + service_type
    __table_args__ = ({"schema": None},)

    miner: Mapped[Miner] = relationship(backref="service_configs")


class SLAMetric(Base):
    """SLA metrics tracking for miners"""

    __tablename__ = "sla_metrics"

    id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    miner_id: Mapped[str] = mapped_column(
        ForeignKey("miners.miner_id", ondelete="CASCADE"), nullable=False
    )
    metric_type: Mapped[str] = mapped_column(String(32), nullable=False)  # uptime, response_time, completion_rate, capacity
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    is_violation: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.now(datetime.UTC)
    )
    meta_data: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict)

    miner: Mapped[Miner] = relationship(backref="sla_metrics")


class SLAViolation(Base):
    """SLA violation tracking"""

    __tablename__ = "sla_violations"

    id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    miner_id: Mapped[str] = mapped_column(
        ForeignKey("miners.miner_id", ondelete="CASCADE"), nullable=False
    )
    violation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # critical, high, medium, low
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    violation_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    resolved_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.now(datetime.UTC)
    )
    meta_data: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict)

    miner: Mapped[Miner] = relationship(backref="sla_violations")


class CapacitySnapshot(Base):
    """Capacity planning snapshots"""

    __tablename__ = "capacity_snapshots"

    id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    total_miners: Mapped[int] = mapped_column(Integer, nullable=False)
    active_miners: Mapped[int] = mapped_column(Integer, nullable=False)
    total_parallel_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    total_queue_length: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity_utilization_pct: Mapped[float] = mapped_column(Float, nullable=False)
    forecast_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    recommended_scaling: Mapped[str] = mapped_column(String(32), nullable=False)
    scaling_reason: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.now(datetime.UTC)
    )
    meta_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
