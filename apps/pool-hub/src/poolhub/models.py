from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from uuid import uuid4


class Base(DeclarativeBase):
    pass


class Miner(Base):
    __tablename__ = "miners"

    miner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    api_key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow)
    last_seen_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    addr: Mapped[str] = mapped_column(String(256))
    proto: Mapped[str] = mapped_column(String(32))
    gpu_vram_gb: Mapped[float] = mapped_column(Float)
    gpu_name: Mapped[Optional[str]] = mapped_column(String(128))
    cpu_cores: Mapped[int] = mapped_column(Integer)
    ram_gb: Mapped[float] = mapped_column(Float)
    max_parallel: Mapped[int] = mapped_column(Integer)
    base_price: Mapped[float] = mapped_column(Float)
    tags: Mapped[Dict[str, str]] = mapped_column(JSONB, default=dict)
    capabilities: Mapped[List[str]] = mapped_column(JSONB, default=list)
    trust_score: Mapped[float] = mapped_column(Float, default=0.5)
    region: Mapped[Optional[str]] = mapped_column(String(64))

    status: Mapped["MinerStatus"] = relationship(back_populates="miner", cascade="all, delete-orphan", uselist=False)
    feedback: Mapped[List["Feedback"]] = relationship(back_populates="miner", cascade="all, delete-orphan")


class MinerStatus(Base):
    __tablename__ = "miner_status"

    miner_id: Mapped[str] = mapped_column(ForeignKey("miners.miner_id", ondelete="CASCADE"), primary_key=True)
    queue_len: Mapped[int] = mapped_column(Integer, default=0)
    busy: Mapped[bool] = mapped_column(Boolean, default=False)
    avg_latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    temp_c: Mapped[Optional[int]] = mapped_column(Integer)
    mem_free_gb: Mapped[Optional[float]] = mapped_column(Float)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    miner: Mapped[Miner] = relationship(back_populates="status")


class MatchRequest(Base):
    __tablename__ = "match_requests"

    id: Mapped[PGUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requirements: Mapped[Dict[str, object]] = mapped_column(JSONB, nullable=False)
    hints: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    top_k: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow)

    results: Mapped[List["MatchResult"]] = relationship(back_populates="request", cascade="all, delete-orphan")


class MatchResult(Base):
    __tablename__ = "match_results"

    id: Mapped[PGUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[PGUUID] = mapped_column(ForeignKey("match_requests.id", ondelete="CASCADE"), index=True)
    miner_id: Mapped[str] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float)
    explain: Mapped[Optional[str]] = mapped_column(Text)
    eta_ms: Mapped[Optional[int]] = mapped_column(Integer)
    price: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow)

    request: Mapped[MatchRequest] = relationship(back_populates="results")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[PGUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    miner_id: Mapped[str] = mapped_column(ForeignKey("miners.miner_id", ondelete="CASCADE"), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    fail_code: Mapped[Optional[str]] = mapped_column(String(64))
    tokens_spent: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow)

    miner: Mapped[Miner] = relationship(back_populates="feedback")
