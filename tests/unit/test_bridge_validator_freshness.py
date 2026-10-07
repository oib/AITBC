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


def test_current_epoch_does_not_decay() -> None:
    """A37-1: a set registered once at the latest epoch stays fresh forever
    — supersession, not wall time, ends validity."""
    stub = _stub_with([("0xA", 0, NOW - timedelta(hours=3))])
    assert stub._check_validator_set_freshness("c") is True
    assert stub._check_validator_set_freshness("c", epoch=0) is True


def test_superseded_epoch_stale_after_grace() -> None:
    """A37-1: an epoch superseded more than grace ago fails closed."""
    stub = _stub_with(
        [
            ("0xA", 0, NOW - timedelta(days=30)),
            ("0xB", 1, NOW - timedelta(hours=3)),
        ]
    )
    assert stub._check_validator_set_freshness("c", epoch=0) is False
    assert stub._check_validator_set_freshness("c", epoch=1) is True


def test_superseded_epoch_fresh_within_grace() -> None:
    """A37-1: an epoch superseded within the grace window still verifies —
    in-flight proofs against the lock-time set survive a rotation."""
    stub = _stub_with(
        [
            ("0xA", 0, NOW - timedelta(days=30)),
            ("0xB", 1, NOW - timedelta(hours=1)),
        ]
    )
    assert stub._check_validator_set_freshness("c", epoch=0) is True


def test_unknown_future_epoch_is_not_fresh() -> None:
    stub = _stub_with([("0xA", 1, NOW)])
    assert stub._check_validator_set_freshness("c", epoch=5) is False


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


def test_stale_superseded_epoch_fails_regardless_of_latest_age() -> None:
    """A37-1: what 'stale' means now — epoch 0 was superseded 5h ago
    (>grace), so epoch-0 verification fails while the current epoch-1
    set stays fresh no matter its own registered_at age."""
    stub = _stub_with(
        [
            ("0xA", 0, NOW - timedelta(days=21)),
            ("0xC", 1, NOW - timedelta(hours=5)),
        ]
    )
    assert stub._check_validator_set_freshness("c") is True
    assert stub._check_validator_set_freshness("c", epoch=0) is False


def test_empty_table_passes_freshness() -> None:
    """No rows → 'fresh enough'; the vset-None check fails it downstream."""
    stub = _stub_with([])
    assert stub._check_validator_set_freshness("c") is True
