"""OpenClaw DAO economic parameter proposal domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class EconomicProposalStatus(StrEnum):
    """Lifecycle status of an economic parameter proposal."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACTIVE = "active"
    PASSED = "passed"
    REJECTED = "rejected"
    EXECUTED = "executed"


class EconomicParameterProposal(SQLModel, table=True):
    """A DAO proposal to change an OpenClaw economic parameter."""

    __tablename__ = "economic_parameter_proposal"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    proposer_id: str = Field(sa_column=sa.Column("proposer_id", sa.String(length=255), nullable=False, index=True))
    parameter_name: str = Field(sa_column=sa.Column("parameter_name", sa.String(length=255), nullable=False, index=True))
    unit: str | None = Field(default=None, sa_column=sa.Column("unit", sa.String(length=64), nullable=True))
    current_value: Decimal = Field(
        default=Decimal("0"),
        sa_column=sa.Column("current_value", sa.Numeric(28, 18), nullable=False, server_default=sa.text("'0'")),
    )
    proposed_value: Decimal = Field(
        default=Decimal("0"),
        sa_column=sa.Column("proposed_value", sa.Numeric(28, 18), nullable=False, server_default=sa.text("'0'")),
    )
    status: EconomicProposalStatus = Field(
        default=EconomicProposalStatus.DRAFT,
        sa_column=sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="draft",
            index=True,
        ),
    )
    votes_for: float = Field(
        default=0.0, sa_column=sa.Column("votes_for", sa.Float(), nullable=False, server_default=sa.text("'0.0'"))
    )
    votes_against: float = Field(
        default=0.0, sa_column=sa.Column("votes_against", sa.Float(), nullable=False, server_default=sa.text("'0.0'"))
    )
    votes_abstain: float = Field(
        default=0.0, sa_column=sa.Column("votes_abstain", sa.Float(), nullable=False, server_default=sa.text("'0.0'"))
    )
    quorum: float = Field(
        default=0.0, sa_column=sa.Column("quorum", sa.Float(), nullable=False, server_default=sa.text("'0.0'"))
    )
    passing_threshold: float = Field(
        default=0.5, sa_column=sa.Column("passing_threshold", sa.Float(), nullable=False, server_default=sa.text("'0.5'"))
    )
    voting_starts: datetime | None = Field(
        default=None, sa_column=sa.Column("voting_starts", sa.DateTime(timezone=True), nullable=True)
    )
    voting_ends: datetime | None = Field(
        default=None, sa_column=sa.Column("voting_ends", sa.DateTime(timezone=True), nullable=True)
    )
    executed_at: datetime | None = Field(
        default=None, sa_column=sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True)
    )
    proposal_metadata: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=sa.Column("proposal_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
