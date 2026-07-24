"""Economic event log for OpenClaw analytics and audit.

ponytail: This is an in-memory event store skeleton. Persisting these events to
a database table is a future step; for v0.12.0 the audit surface is the
reconciliation script that reads the event stream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4


class EconomicEventType(StrEnum):
    """Types of economic events captured for audit."""

    LEASE = "lease"
    PAYMENT = "payment"
    SLASH = "slash"
    REBALANCE = "rebalance"
    STAKE = "stake"
    UNSTAKE = "unstake"
    REWARD = "reward"


@dataclass
class EconomicEvent:
    """A single economic event captured for audit and analytics."""

    event_id: str
    event_type: EconomicEventType
    actor_id: str
    amount: Decimal
    chain_id: str
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventStore:
    """In-memory store for economic events."""

    def __init__(self) -> None:
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
            event_id=f"evt-{uuid4().hex[:8]}",
            event_type=event_type,
            actor_id=actor_id,
            amount=amount,
            chain_id=chain_id,
            meta=meta or {},
        )
        self._events.append(event)
        return event

    def list(
        self,
        *,
        actor_id: str | None = None,
        event_type: EconomicEventType | None = None,
        limit: int = 100,
    ) -> list[EconomicEvent]:
        """Return events, optionally filtered."""
        events = self._events[:]
        if actor_id:
            events = [e for e in events if e.actor_id == actor_id]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def total_by_actor(self, actor_id: str) -> Decimal:
        """Sum absolute event amounts for an actor."""
        return sum((e.amount for e in self._events if e.actor_id == actor_id), Decimal("0"))
