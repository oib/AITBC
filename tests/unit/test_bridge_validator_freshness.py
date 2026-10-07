"""Fixture test for _check_validator_set_freshness (A36-1).

Proves the freshness gate as coded: it takes the NEWEST ``registered_at``
of any row for the chain — no epoch logic — and fails closed once that
newest row is older than ``bridge_validator_set_grace_period`` (7200 s).
An in-memory chain DB with a stub exposing only ``_session_for`` drives
the real mixin method.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, create_engine

from aitbc_chain.base_models import BridgeValidator
from aitbc_chain.cross_chain.bridge_validator import BridgeValidatorMixin


class _Stub(BridgeValidatorMixin):
    """Minimal stand-in for CrossChainBridge: a session factory over a
    fixture sqlite engine. The method under test needs nothing else."""

    def __init__(self, engine):
        self._engine = engine

    @contextmanager
    def _session_for(self, chain_id: str = ""):
        with Session(self._engine) as session:
            yield session


def _stub_with(rows: list[tuple[str, int, datetime]]) -> _Stub:
    engine = create_engine("sqlite://")
    BridgeValidator.__table__.create(engine)
    with Session(engine) as s:
        for _i, (addr, epoch, ts) in enumerate(rows, 1):
            s.add(
                BridgeValidator(
                    chain_id="c",
                    address=addr,
                    public_key="0x04",
                    epoch=epoch,
                    is_active=True,
                    registered_at=ts,
                )
            )
        s.commit()
    return _Stub(engine)


NOW = datetime.now(UTC)


def test_registered_three_hours_ago_fails() -> None:
    stub = _stub_with([("0xA", 0, NOW - timedelta(hours=3))])
    assert stub._check_validator_set_freshness("c") is False


def test_registered_one_hour_ago_passes() -> None:
    stub = _stub_with([("0xA", 0, NOW - timedelta(hours=1))])
    assert stub._check_validator_set_freshness("c") is True


def test_newer_epoch_row_refreshes_set() -> None:
    """An old epoch-0 pair plus a fresh epoch-1 row: newest registered_at
    wins — the set is fresh even though the old rows are ancient."""
    stub = _stub_with(
        [
            ("0xA", 0, NOW - timedelta(days=21)),
            ("0xB", 0, NOW - timedelta(days=21)),
            ("0xC", 1, NOW - timedelta(minutes=30)),
        ]
    )
    assert stub._check_validator_set_freshness("c") is True


def test_stale_old_epoch_still_fails_with_stale_new_epoch() -> None:
    """If the NEWEST row is stale, all-epoch staleness fails — the docstring's
    'no newer epoch exists' is misleading: epochs are never inspected."""
    stub = _stub_with(
        [
            ("0xA", 0, NOW - timedelta(days=21)),
            ("0xC", 1, NOW - timedelta(hours=5)),
        ]
    )
    assert stub._check_validator_set_freshness("c") is False


def test_empty_table_passes_freshness() -> None:
    """No rows → 'fresh enough'; the vset-None check fails it downstream."""
    stub = _stub_with([])
    assert stub._check_validator_set_freshness("c") is True
