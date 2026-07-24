"""Grant proposal domain models for DAO grant disbursement."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, Numeric
from sqlmodel import Field, SQLModel


class GrantStatus(StrEnum):
    """Lifecycle status of a grant proposal."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MilestoneStatus(StrEnum):
    """Lifecycle status of a grant milestone."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


class GrantProposal(SQLModel, table=True):
    """A DAO grant proposal submitted by a developer."""

    __tablename__ = "grant_proposal"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    developer_id: str = Field(foreign_key="developer.id", index=True)
    title: str = Field()
    description: str = Field()
    requested_amount: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(28, 18)))
    approved_amount: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(28, 18)))
    disbursed_amount: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(28, 18)))
    status: GrantStatus = Field(default=GrantStatus.DRAFT)
    votes_for: float = Field(default=0.0)
    votes_against: float = Field(default=0.0)
    votes_abstain: float = Field(default=0.0)
    quorum: float = Field(default=0.0)
    passing_threshold: float = Field(default=0.5)
    voting_starts: datetime | None = None
    voting_ends: datetime | None = None
    executed_at: datetime | None = None
    proposal_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GrantMilestone(SQLModel, table=True):
    """A milestone within a grant proposal."""

    __tablename__ = "grant_milestone"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    grant_id: str = Field(foreign_key="grant_proposal.id", index=True)
    title: str = Field()
    description: str = Field()
    amount: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(28, 18)))
    status: MilestoneStatus = Field(default=MilestoneStatus.PENDING)
    due_date: datetime | None = None
    completed_at: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
