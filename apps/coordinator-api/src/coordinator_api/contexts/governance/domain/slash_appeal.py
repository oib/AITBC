"""Slashing appeal and evidence workflow for OpenClaw governance."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column, text
from sqlmodel import Field, SQLModel


class SlashAppealStatus(StrEnum):
    """Lifecycle status of a slash appeal."""

    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class SlashAppeal(SQLModel, table=True):
    """A provider's appeal against a slashing event."""

    __tablename__ = "slash_appeal"
    __table_args__ = {"extend_existing": True}

    id: str = Field(
        default_factory=lambda: f"sa_{uuid4().hex[:10]}",
        max_length=32,
        primary_key=True,
    )
    bond_id: str = Field(default="", max_length=255, index=True)
    provider_id: str = Field(default="", max_length=255, index=True)
    slash_event_id: str = Field(default="", max_length=255, index=True)
    reason: str = Field(default="", max_length=255)
    evidence: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default=text("'[]'")),
    )
    status: str = Field(default=SlashAppealStatus.SUBMITTED.value, max_length=20, index=True)
    reviewer_notes: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
