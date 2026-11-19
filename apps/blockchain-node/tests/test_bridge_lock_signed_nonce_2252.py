"""#2252 — a BRIDGE_LOCK keeps its signed nonce from the v27 rung.

Locks carry ``bridge_signature`` (not ``signature``), so ``use_account_nonce_override``
rewrote their envelope nonce to the account's live nonce before the authority
signature was checked. ``bridge_lock_message`` signs the nonce, so a second lock
sharing a nonce with an earlier sealed one (block-scoped preregistration lets two
locks be created with the same nonce) failed verification after the first sealed.
v27 keeps the signed nonce for ``bridge_signature`` txs; below it nothing changes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import Session

_tests_dir = str(Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from test_tx_nonce_per_block_invariants import (  # noqa: E402
    ADDR_R,
    ADDR_S,
    CHAIN,
    FEE,
    NONCE0,
    KEY_S,
    _account_scalars,
    _apply_data,
    _bridge_lock_tx,
    fixture_db,  # noqa: F401 - pytest fixture
)

from aitbc_chain.base_models import ChainParameter  # noqa: E402
from aitbc_chain.config import settings  # noqa: E402
from aitbc_chain.state.state_transition import StateTransition, use_account_nonce_override  # noqa: E402
from aitbc_chain.state.state_transition_txmeta import get_block_version_for_height  # noqa: E402

PRE, RUNG = 26, 27


def _apply_like_caller(st: StateTransition, session: Session, tx: dict[str, Any], version: int):
    """Mirror the proposer/importer: normalise value, then rewrite the nonce to the
    account's live nonce exactly when ``use_account_nonce_override`` says so."""
    data = _apply_data(tx)
    if use_account_nonce_override(data, version):
        data["nonce"] = _account_scalars(session)[0]
    return st.apply_transaction_guarded(session, CHAIN, data, data["tx_hash"], block_version=version, block_height=1)


def _authority(session: Session) -> None:
    session.add(ChainParameter(chain_id=CHAIN, parameter="bridge_release_authority", value=ADDR_S, applied_height=None))
    session.flush()


class TestOverrideHelper:
    @pytest.mark.parametrize(
        ("version", "tx", "expected"),
        [
            (PRE, {"type": "BRIDGE_LOCK", "bridge_signature": "0x1"}, True),
            (RUNG, {"type": "BRIDGE_LOCK", "bridge_signature": "0x1"}, False),
            (RUNG, {"type": "bridge_lock", "bridge_signature": "0x1"}, False),
            (RUNG, {"type": "BRIDGE_LOCK", "payload": {"bridge_signature": "0x1"}}, False),
            (RUNG, {"payload": {"type": "BRIDGE_LOCK", "bridge_signature": "0x1"}}, False),
            (RUNG + 1, {"type": "BRIDGE_LOCK", "bridge_signature": "0x1"}, False),
            (RUNG, {"type": "BRIDGE_LOCK"}, True),
            (RUNG, {"type": "BRIDGE_LOCK", "payload": {}}, True),
            (RUNG, {"type": "BRIDGE_LOCK", "payload": "not-a-dict"}, True),
            (RUNG, {"type": "BRIDGE_LOCK", "bridge_signature": ""}, True),
            (RUNG, {"signature": "0x1"}, False),
            (6, {"type": "BRIDGE_LOCK", "bridge_signature": "0x1"}, True),
            # #2252 ruling: field presence alone must not take the lock nonce path
            (RUNG, {"bridge_signature": "0x1"}, True),
            (RUNG, {"type": "TRANSFER", "bridge_signature": "0x1"}, True),
            (RUNG, {"type": "BRIDGE_RELEASE", "bridge_signature": "0x1"}, True),
            (RUNG, {"type": "BRIDGE_REFUND", "payload": {"bridge_signature": "0x1"}}, True),
            (RUNG, {"type": "MESSAGE", "bridge_signature": "0x1"}, True),
        ],
    )
    def test_table(self, version, tx, expected):
        assert use_account_nonce_override(tx, version) is expected

    def test_rung_selected_only_when_armed(self, monkeypatch):
        monkeypatch.setattr(settings, "state_transition_v27_height", None)
        assert get_block_version_for_height(10**9) < RUNG
        monkeypatch.setattr(settings, "state_transition_v27_height", 100)
        assert get_block_version_for_height(99) < RUNG
        assert get_block_version_for_height(100) == RUNG


class TestTwoLocksSharingANonce:
    def _two_locks(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return (
            _bridge_lock_tx(transfer_id="n2252-a", amount=100, label="n2252-a", nonce=NONCE0),
            _bridge_lock_tx(transfer_id="n2252-b", amount=100, label="n2252-b", nonce=NONCE0),
        )

    def test_pre_rung_second_lock_dies_on_the_rewritten_nonce(self, fixture_db):  # noqa: F811
        engine, _ = fixture_db
        st = StateTransition()
        lock_a, lock_b = self._two_locks()
        with Session(engine) as session:
            _authority(session)
            ok, err = _apply_like_caller(st, session, lock_a, PRE)
            assert ok, err
            session.flush()
            ok_b, err_b = _apply_like_caller(st, session, lock_b, PRE)
            assert not ok_b and "bridge_signature" in err_b

    def test_rung_both_locks_seal_and_nonce_advances_per_lock(self, fixture_db):  # noqa: F811
        engine, _ = fixture_db
        st = StateTransition()
        lock_a, lock_b = self._two_locks()
        with Session(engine) as session:
            _authority(session)
            for lock in (lock_a, lock_b):
                ok, err = _apply_like_caller(st, session, lock, RUNG)
                assert ok, err
                session.flush()
            nonce, balance = _account_scalars(session)
            assert nonce == NONCE0 + 2
            assert balance == 10**9 - 2 * (100 + FEE)
            assert _account_scalars(session, ADDR_R)[1] == 0

    def test_rung_still_rejects_a_signature_over_a_different_nonce(self, fixture_db):  # noqa: F811
        """The kept nonce is now authenticated: a lock whose envelope nonce was
        changed after signing no longer verifies (the old rewrite hid this)."""
        engine, _ = fixture_db
        st = StateTransition()
        lock_a, _ = self._two_locks()
        lock_a["nonce"] = NONCE0 + 9
        with Session(engine) as session:
            _authority(session)
            ok, err = _apply_like_caller(st, session, lock_a, RUNG)
            assert not ok and "bridge_signature" in err
            assert _account_scalars(session)[0] == NONCE0
        assert KEY_S  # signer key is the authority fixture key
