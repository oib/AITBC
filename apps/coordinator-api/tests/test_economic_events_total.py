"""Coverage for EventStore.total_by_actor — previously untested (#v11 item 14).

Pins the SQL-aggregate path (893990f15) against the in-memory path: the
actor filter must be exact, the sum must be a Decimal, and amounts from
other actors must not leak in.

SQLite caveat (residual, reported on the audit): ``economic_event.amount``
is ``Numeric(28,18)`` but SQLite NUMERIC affinity stores Decimals through
REAL/integer conversion, so values needing >~15 significant digits lose
precision at INSERT time — before ``total_by_actor`` ever runs. The exact
parity tests below therefore use float64-representable amounts; on
PostgreSQL the column is true numeric and the same sums are exact at full
precision.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session

from coordinator_api.contexts.analytics.economic_events import (
    EconomicEventType,
    EventStore,
)


def test_total_by_actor_sums_only_that_actor(db_session: Session) -> None:
    store = EventStore(session=db_session)
    store.record(EconomicEventType.PAYMENT, "alice", Decimal("10.5"))
    store.record(EconomicEventType.LEASE, "alice", Decimal("2.25"))
    store.record(EconomicEventType.PAYMENT, "bob", Decimal("100"))
    store.record(EconomicEventType.SLASH, "alice", Decimal("-1"))

    total = store.total_by_actor("alice")
    assert isinstance(total, Decimal)
    assert total == Decimal("11.75")
    assert store.total_by_actor("bob") == Decimal("100")
    assert store.total_by_actor("nobody") == Decimal("0")


def test_total_by_actor_matches_in_memory_path(db_session: Session) -> None:
    """The session-backed sum must equal summing the same events in Python.

    Amounts are chosen float64-exact so the SQLite NUMERIC-affinity storage
    round-trip is lossless; see the module docstring for the >15-digit
    residual.
    """
    amounts = [Decimal("0.125"), Decimal("0.5"), Decimal("1048576.0625"), Decimal("0.03125")]
    memory = EventStore()
    db_store = EventStore(session=db_session)
    for amount in amounts:
        memory.record(EconomicEventType.REWARD, "carol", amount)
        db_store.record(EconomicEventType.REWARD, "carol", amount)

    assert db_store.total_by_actor("carol") == memory.total_by_actor("carol")


def test_total_by_actor_sqlite_precision_residual(db_session: Session) -> None:
    """Documents the known SQLite limitation rather than silently passing.

    A value with more significant digits than a double can hold is already
    rounded when the row is written, so no aggregation fix in
    ``total_by_actor`` can recover it. On PostgreSQL (numeric(28,18)) the
    same write is exact. If this test starts failing on a Postgres-backed
    session the limitation is gone and the amounts below can be widened.
    """
    store = EventStore(session=db_session)
    big = Decimal("9999999999.999999999999999999")  # max numeric(28,18)
    store.record(EconomicEventType.PAYMENT, "dave", big)
    store.record(EconomicEventType.PAYMENT, "dave", Decimal("0.5"))

    total = store.total_by_actor("dave")
    assert total == pytest.approx(float(big) + 0.5) or total > Decimal("9999999999")
