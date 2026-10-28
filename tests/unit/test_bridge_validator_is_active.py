"""Regression tests for #674: load_validator_set must honour is_active.

Before the fix, ``load_validator_set`` selected ``bridge_validators`` rows by
``chain_id`` + latest epoch only — a deactivated row (``is_active=False``)
still loaded, counted in ``vset.total``, and stayed eligible as a signer in
threshold verification. That made deactivation cosmetic: the phantom-set
incident could only be remediated by hard DELETE.

These tests drive the real mixin method against an in-memory sqlite DB.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import patch

from sqlmodel import Session, create_engine

from aitbc.bridge.validators import ValidatorSetRegistry
from aitbc_chain.base_models import BridgeValidator
from aitbc_chain.cross_chain.bridge_validator import BridgeValidatorMixin

CHAIN = "c"


class _DBStub(BridgeValidatorMixin):
    """Same stub shape as test_bridge_registry_accumulation: rows only in
    the DB, an empty in-memory registry to be rebuilt by the loader."""

    def __init__(self, engine):
        self._engine = engine
        self._validator_registry = ValidatorSetRegistry()
        self._validator_cache_loaded: set = set()

    @contextmanager
    def _session_for(self, chain_id: str = ""):
        with Session(self._engine) as session:
            yield session


def _stub_with(rows: list[tuple[str, int, bool]]) -> _DBStub:
    """rows: (address, epoch, is_active)."""
    engine = create_engine("sqlite://")
    BridgeValidator.__table__.create(engine)
    with Session(engine) as s:
        for addr, epoch, active in rows:
            s.add(
                BridgeValidator(
                    chain_id=CHAIN,
                    address=addr,
                    public_key="0x04",
                    epoch=epoch,
                    is_active=active,
                    registered_at=datetime.now(UTC),
                )
            )
        s.commit()
    return _DBStub(engine)


def test_inactive_rows_do_not_load() -> None:
    """A deactivated row in the selected epoch is excluded from the set and
    from ``total`` — it cannot count toward the multisig threshold."""
    stub = _stub_with(
        [
            ("0xAA", 1, True),
            ("0xBB", 1, True),
            ("0xCC", 1, True),
            ("0xPHANTOM", 1, False),
        ]
    )
    with patch("aitbc_chain.cross_chain.bridge_validator.settings") as s:
        s.bridge_multisig_threshold = 3
        vset = stub.load_validator_set(CHAIN)
    assert vset is not None
    assert {v.address for v in vset.validators} == {"0xAA", "0xBB", "0xCC"}
    assert vset.total == 3
    assert "0xPHANTOM" not in vset.addresses


def test_all_inactive_explicit_epoch_returns_none() -> None:
    """An epoch whose rows are all deactivated loads as no set — fail closed
    rather than verifying against ghosts."""
    stub = _stub_with(
        [
            ("0xAA", 1, True),
            ("0xBB", 2, False),
            ("0xCC", 2, False),
        ]
    )
    assert stub.load_validator_set(CHAIN, epoch=2) is None


def test_latest_epoch_resolution_ignores_fully_inactive_epochs() -> None:
    """With epoch=None the loader picks the latest epoch that still has
    active rows; a newer all-deactivated epoch does not shadow the set that
    is still authoritative."""
    stub = _stub_with(
        [
            ("0xAA", 1, True),
            ("0xBB", 1, True),
            ("0xCC", 2, False),
        ]
    )
    vset = stub.load_validator_set(CHAIN)
    assert vset is not None
    assert vset.epoch == 1
    assert {v.address for v in vset.validators} == {"0xAA", "0xBB"}


def test_everything_inactive_returns_none() -> None:
    stub = _stub_with([("0xAA", 1, False)])
    assert stub.load_validator_set(CHAIN) is None
    assert stub.load_validator_set(CHAIN, epoch=1) is None


def test_mixed_epochs_only_active_rows_load() -> None:
    """Explicit epoch load keeps active rows of that epoch and drops its
    deactivated rows even when other epochs are fully active."""
    stub = _stub_with(
        [
            ("0xAA", 1, True),
            ("0xOLD", 1, False),
            ("0xBB", 2, True),
            ("0xCC", 2, True),
        ]
    )
    vset = stub.load_validator_set(CHAIN, epoch=1)
    assert vset is not None
    assert {v.address for v in vset.validators} == {"0xAA"}
    assert vset.total == 1
