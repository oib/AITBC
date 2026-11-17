"""#2186 DEV3-BLOCK-SCOPED-RUNG-1 — v26 makes bridge block-scoping a property of the block version.

Below the rung the node-local ``block_scoped_preregistered_transactions`` setting decides
(fleet: true; env-false refused at construction, tests patch the attribute). At or above
``state_transition_v26_height`` the deferral is unconditional. Unarmed (the shipped state)
the rung changes nothing: the setting decides at every height and no DB is touched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus.poa_tx_pipeline import _TxPipelineMixin
from aitbc_chain.models import Block
from aitbc_chain.state.state_transition import (
    block_scoped_preregistered,
    block_scoped_preregistered_for_next_block,
    get_block_version_for_height,
)
from sqlmodel import Session

CHAIN = "bc-2"
RUNG = 100
NOW = datetime(2026, 11, 17, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None)


class _NoDb:
    """A session that fails the test if the dormant path touches the database."""

    def exec(self, *_a, **_k):
        raise AssertionError("dormant rung must not query the database")


@pytest.fixture
def unarmed(monkeypatch):
    monkeypatch.setattr(settings, "state_transition_v26_height", None)


@pytest.fixture
def armed(monkeypatch):
    monkeypatch.setattr(settings, "state_transition_v26_height", RUNG)


def _seed_head(engine, height: int) -> None:
    with Session(engine) as s:
        s.add(
            Block(
                chain_id=CHAIN,
                height=height,
                hash=f"0x{height:x}",
                parent_hash="0xp",
                proposer="0xprop",
                timestamp=NOW,
                tx_count=0,
                state_root="0x00",
                bridge_state_root="0x00",
                aux_state_root="",
                signature="sig",
            )
        )
        s.commit()


# --- dormant (the shipped state) -------------------------------------------------


@pytest.mark.parametrize("flag", [True, False])
@pytest.mark.parametrize("version", [1, 14, 25])
def test_dormant_setting_decides_below_rung(unarmed, monkeypatch, flag, version) -> None:
    monkeypatch.setattr(settings, "block_scoped_preregistered_transactions", flag)
    assert block_scoped_preregistered(version) is flag


@pytest.mark.parametrize("flag", [True, False])
def test_dormant_rpc_decision_is_the_setting_and_touches_no_db(unarmed, monkeypatch, flag) -> None:
    monkeypatch.setattr(settings, "block_scoped_preregistered_transactions", flag)
    assert block_scoped_preregistered_for_next_block(_NoDb(), CHAIN) is flag


def test_dormant_resolver_never_returns_26(unarmed) -> None:
    assert all(get_block_version_for_height(h) < 26 for h in (1, 100, 10**9))


# --- flag-off / flag-on divergence ------------------------------------------------


def test_armed_rung_overrides_flag_off(armed, monkeypatch) -> None:
    """The divergence the rung removes: a flag-off node and a flag-on node agree at/above the rung."""
    results = set()
    for flag in (True, False):
        monkeypatch.setattr(settings, "block_scoped_preregistered_transactions", flag)
        results.add(block_scoped_preregistered(26))
    assert results == {True}


def test_armed_rung_keeps_flag_in_charge_below(armed, monkeypatch) -> None:
    monkeypatch.setattr(settings, "block_scoped_preregistered_transactions", False)
    assert block_scoped_preregistered(25) is False


# --- rung boundary ----------------------------------------------------------------


def test_resolver_boundary(armed) -> None:
    assert get_block_version_for_height(RUNG - 1) < 26
    assert get_block_version_for_height(RUNG) == 26
    assert get_block_version_for_height(RUNG + 1) == 26


@pytest.mark.parametrize(("head", "expected"), [(RUNG - 3, False), (RUNG - 2, False), (RUNG - 1, True), (RUNG, True)])
def test_rpc_decision_follows_the_height_the_block_will_have(armed, engine, monkeypatch, head, expected) -> None:
    """RPC deferral flips exactly when the sealing block (head + 1) reaches the rung."""
    monkeypatch.setattr(settings, "block_scoped_preregistered_transactions", False)
    _seed_head(engine, head)
    with Session(engine) as s:
        assert block_scoped_preregistered_for_next_block(s, CHAIN) is expected


def test_rpc_decision_on_empty_chain_uses_height_one(armed, engine, monkeypatch) -> None:
    monkeypatch.setattr(settings, "block_scoped_preregistered_transactions", False)
    with Session(engine) as s:
        assert block_scoped_preregistered_for_next_block(s, CHAIN) is False


# --- replay / proposer path --------------------------------------------------------


class _Reached(Exception):
    pass


def _credit_gate(version: int, monkeypatch) -> bool:
    """Run the proposer's BRIDGE_RELEASE gate; _Reached means the tx was taken block-scoped."""
    import aitbc_chain.consensus.poa_tx_pipeline as mod

    def _boom():
        raise _Reached

    monkeypatch.setattr(mod._poa, "get_state_transition", _boom)
    pipeline = object.__new__(_TxPipelineMixin)
    ctx = SimpleNamespace(block_version=version)
    tx = SimpleNamespace(content={"amount": 1}, tx_hash="0xt")
    try:
        return pipeline._seq_block_scoped_credit(ctx, tx, "BRIDGE_RELEASE", 0, 0)
    except _Reached:
        return True


def test_replay_below_rung_with_flag_off_is_not_deferred(monkeypatch) -> None:
    """Replay of pre-rung history on a flag-off test node keeps the legacy path."""
    monkeypatch.setattr(settings, "block_scoped_preregistered_transactions", False)
    assert _credit_gate(25, monkeypatch) is False


def test_replay_at_rung_with_flag_off_is_deferred(monkeypatch) -> None:
    monkeypatch.setattr(settings, "block_scoped_preregistered_transactions", False)
    assert _credit_gate(26, monkeypatch) is True


def test_flag_on_deferred_at_every_version(monkeypatch) -> None:
    monkeypatch.setattr(settings, "block_scoped_preregistered_transactions", True)
    assert all(_credit_gate(v, monkeypatch) is True for v in (14, 25, 26))
