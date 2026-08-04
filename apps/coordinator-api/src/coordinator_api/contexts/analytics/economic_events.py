"""Economic event log for OpenClaw analytics and audit.

ponytail: `EventStore` works both in-memory and with a database session. The
SQLModel is registered with SQLModel.metadata and has a matching Alembic
migration; passing a session persists events, while omitting one keeps the
original in-memory behaviour for unit tests and simple consumers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlmodel import Field, Session, SQLModel, select


class EconomicEventType(StrEnum):
    """Types of economic events captured for audit."""

    LEASE = "lease"
    PAYMENT = "payment"
    SLASH = "slash"
    REBALANCE = "rebalance"
    STAKE = "stake"
    UNSTAKE = "unstake"
    REWARD = "reward"


class EconomicEvent(SQLModel, table=True):
    """A persisted economic event captured for audit and analytics."""

    __tablename__ = "economic_event"

    event_id: str = Field(
        default_factory=lambda: f"evt-{uuid4().hex[:8]}",
        sa_column=sa.Column("event_id", sa.String(length=32), nullable=False, primary_key=True),
    )
    event_type: EconomicEventType = Field(
        sa_column=sa.Column("event_type", sa.String(length=20), nullable=False, index=True),
    )
    actor_id: str = Field(sa_column=sa.Column("actor_id", sa.String(length=255), nullable=False, index=True))
    amount: Decimal = Field(
        default=Decimal("0"),
        sa_column=sa.Column("amount", sa.Numeric(28, 18), nullable=False, server_default=sa.text("'0'")),
    )
    chain_id: str = Field(sa_column=sa.Column("chain_id", sa.String(length=64), nullable=False))
    meta: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


class EventStore:
    """Store for economic events. Works in-memory or backed by a database session."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self._events: list[EconomicEvent] = []

    def record(
        self,
        event_type: EconomicEventType,
        actor_id: str,
        amount: Decimal,
        chain_id: str = "ait-hub",
        meta: dict[str, Any] | None = None,
    ) -> EconomicEvent:
        """Record a new economic event."""
        event = EconomicEvent(
            event_type=event_type,
            actor_id=actor_id,
            amount=amount,
            chain_id=chain_id,
            meta=meta or {},
        )
        if self._session is None:
            self._events.append(event)
        else:
            self._session.add(event)
            self._session.commit()
            self._session.refresh(event)
        return event

    def list(
        self,
        *,
        actor_id: str | None = None,
        event_type: EconomicEventType | None = None,
        limit: int = 100,
    ) -> list[EconomicEvent]:
        """Return events, optionally filtered."""
        if self._session is None:
            events = self._events[:]
        else:
            stmt = select(EconomicEvent).order_by(EconomicEvent.created_at.desc())  # type: ignore[attr-defined]
            if actor_id:
                stmt = stmt.where(EconomicEvent.actor_id == actor_id)
            if event_type:
                stmt = stmt.where(EconomicEvent.event_type == event_type)
            events = list(self._session.execute(stmt.limit(limit)).scalars().all())
            return events

        if actor_id:
            events = [e for e in events if e.actor_id == actor_id]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def total_by_actor(self, actor_id: str) -> Decimal:
        """Sum absolute event amounts for an actor."""
        if self._session is None:
            events = self._events
        else:
            stmt = select(EconomicEvent).where(EconomicEvent.actor_id == actor_id)
            events = list(self._session.execute(stmt).scalars().all())
        return sum((e.amount for e in events if e.actor_id == actor_id), Decimal("0"))
