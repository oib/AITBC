"""Dispute resolution persistence (#2161).

The ``DisputeResolutionService`` keeps ``DisputeCase`` objects in memory as
the hot cache; these tables are the write-through store so open disputes —
evidence, arbitrator votes, refund/payout amounts — survive a
coordinator-api restart. Status/outcome are stored as their enum string
values; timestamps are stored as naive UTC (SQLite drops tzinfo) and
rehydrated as aware UTC by the service.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Column
from sqlmodel import Field, SQLModel


class DisputeCaseRow(SQLModel, table=True):
    """One row per filed dispute (mirrors ``DisputeCase``)."""

    __tablename__ = "dispute_cases"
    __table_args__ = {"extend_existing": True}

    dispute_id: str = Field(primary_key=True, max_length=64)
    job_id: str = Field(index=True, max_length=128)
    client: str = Field(max_length=128)
    provider: str = Field(max_length=128)
    amount: int = Field(sa_column=Column(BigInteger, nullable=False))
    reason: str = Field(default="")
    filed_by: str = Field(max_length=128)
    status: str = Field(default="pending", index=True, max_length=32)
    outcome: str | None = Field(default=None, max_length=32)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    evidence_deadline: datetime | None = Field(default=None)
    voting_deadline: datetime | None = Field(default=None)
    resolved_at: datetime | None = Field(default=None)
    refund_amount: int = Field(default=0, sa_column=Column(BigInteger, nullable=False, default=0))
    payout_amount: int = Field(default=0, sa_column=Column(BigInteger, nullable=False, default=0))


class DisputeEvidenceRow(SQLModel, table=True):
    """One evidence entry; ``id`` orders entries within a dispute."""

    __tablename__ = "dispute_evidence"
    __table_args__ = {"extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    dispute_id: str = Field(foreign_key="dispute_cases.dispute_id", index=True, max_length=64)
    submitted_by: str = Field(max_length=128)
    evidence_type: str = Field(max_length=64)
    description: str = Field(default="")
    ipfs_hash: str | None = Field(default=None, max_length=128)
    tx_hash: str | None = Field(default=None, max_length=128)
    timestamp: datetime


class DisputeVoteRow(SQLModel, table=True):
    """One arbitrator vote; ``id`` orders votes within a dispute."""

    __tablename__ = "dispute_votes"
    __table_args__ = {"extend_existing": True}

    id: int | None = Field(default=None, primary_key=True)
    dispute_id: str = Field(foreign_key="dispute_cases.dispute_id", index=True, max_length=64)
    arbitrator: str = Field(max_length=128)
    outcome: str = Field(max_length=32)
    reasoning: str = Field(default="")
    stake_amount: int = Field(sa_column=Column(BigInteger, nullable=False))
    timestamp: datetime


class DisputeArbitratorRow(SQLModel, table=True):
    """A registered arbitrator address."""

    __tablename__ = "dispute_arbitrators"
    __table_args__ = {"extend_existing": True}

    address: str = Field(primary_key=True, max_length=128)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
