"""Pending automatic bond slashes awaiting the appeal window (#2976).

``BondSlashingService.slash`` no longer submits ``BOND_SLASH`` inline for the
windowed conditions (``downtime``/``bad_result``): detection writes a durable
``pending_bond_slash`` row, freezes the bond's eligibility via the #2966
``suspension_event_id`` meta flag, and the sweeper executes the row once
``window_ends_at`` passes. ``fraud`` and the ``BOND_SLASH_WINDOW_ENABLED=false``
kill-switch keep the immediate inline path — a fraud appeal window would be the
authority appealing to itself.

All timestamps are stored as naive UTC (``DATETIME`` columns carry no
timezone); compare them against ``datetime.now(UTC).replace(tzinfo=None)``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Column, Index, Text, text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Naive UTC now — matches the ``DATETIME(timezone=False)`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class PendingBondSlashStatus(StrEnum):
    """Lifecycle of a queued automatic slash."""

    PENDING = "pending"
    EXECUTING = "executing"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PendingBondSlash(SQLModel, table=True):
    """A detected slash violation inside its appeal window.

    ``bond_id`` is the chain bond id (``ProviderBond.bond_id``) — the same
    identifier slash appeals and the chain point-read use — while ``bond_pk``
    pins the local ``ProviderBond.id`` row the detection resolved, so the
    executor's CAS snapshot does not depend on provider_id uniqueness.
    ``slash_amount_units``/``pre_slash_amount_units`` are whole-AIT / compute-unit
    snapshots taken at detection: the penalty is fixed when the violation is
    found, not recomputed at execution.
    """

    __tablename__ = "pending_bond_slash"
    __table_args__ = (
        # The sweeper's hot query: due rows in window order.
        Index("ix_pending_bond_slash_status_window", "status", "window_ends_at"),
        Index("ix_pending_bond_slash_bond", "bond_id"),
        # #2995: at most one OPEN row per (job, condition) — the sweeper
        # re-detects the same stale job every pass; terminal rows never block.
        Index(
            "uq_pending_bond_slash_open_job_condition",
            "job_id",
            "condition",
            unique=True,
            sqlite_where=text("status IN ('pending', 'executing')"),
            postgresql_where=text("status IN ('pending', 'executing')"),
        ),
        {"extend_existing": True},
    )

    id: str = Field(
        default_factory=lambda: f"ps_{uuid4().hex[:12]}",
        max_length=40,
        primary_key=True,
    )
    job_id: str = Field(default="", max_length=255, index=True)
    bond_id: str = Field(default="", max_length=255)
    bond_pk: str = Field(default="", max_length=40)
    provider_id: str = Field(default="", max_length=255, index=True)
    condition: str = Field(default="", max_length=32)
    slash_rate: str = Field(default="", max_length=32)
    # Whole-AIT slash amount snapshotted at detection (what _build_slash_tx
    # receives before ait_to_units conversion).
    slash_amount_units: int = Field(default=0)
    # Chain compute-units of bond.amount at detection — the pre-slash baseline
    # the stale-executing reconcile compares the point-read against.
    pre_slash_amount_units: int = Field(default=0)
    evidence: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default=text("''")),
    )
    # The suspension event this row was detected under — the first pending row
    # on an unsuspended bond IS the event (its own id); later compound rows
    # record the already-live event. Empty only if detection raced a lift.
    suspension_event_id: str = Field(default="", max_length=64)
    detected_at: datetime = Field(default_factory=utcnow, nullable=False)
    window_ends_at: datetime = Field(nullable=False)
    status: str = Field(default=PendingBondSlashStatus.PENDING.value, max_length=16)
    appeal_id: str = Field(default="", max_length=40)
    submitted_tx_hash: str = Field(default="", max_length=128)
    # Bounded executor retries: each claim increments; >= _MAX_ATTEMPTS the row
    # lands FAILED and an error is logged for operator attention.
    attempts: int = Field(default=0)
    claimed_at: datetime | None = Field(default=None)
    last_error: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)
