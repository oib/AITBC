"""#2484 BOUNTY-PAYOUT-INVARIANTS-1: per-bounty outflow bounds at apply (v30).

The #2480 one-shot auth bound stops *replay* of one authorization, but a
buggy or compromised operator signer could still drain a bounty escrow
with *distinct* signed transfers. v30 enforces, from replicated
``Transaction`` rows only (never the RPC-mutated ``BountyContract`` row):

- summed ``BOUNTY_PAYOUT`` + ``BOUNTY_REFUND`` value per ``bounty_id``
  never exceeds the summed ``BOUNTY_LOCK`` value (refunds count — the
  honest lifecycle pays XOR refunds the full remainder, so a signed
  payout+refund pair is the same drain);
- at most one ``BOUNTY_PAYOUT`` per ``(bounty_id, submission_id)``.

Same-block applications accumulate in ``_block_bounty_out`` /
``_block_bounty_subs``; sealed rows at or above the applied height are
excluded so staged proposer rows are not double-counted. Below v30 the
rules are unchanged — historical blocks (incl. the v17 payout+refund
pair) replay identically.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from eth_keys import keys
from eth_utils import keccak
from sqlalchemy import create_engine
from sqlmodel import Session

from aitbc_chain.base_models import Account, Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.protocol_escrow import bounty_escrow_address
from aitbc_chain.state.state_transition import StateTransition

CHAIN = "ait-test-2484"
OPERATOR_KEY = keys.PrivateKey(b"\x77" * 32)
OPERATOR = OPERATOR_KEY.public_key.to_checksum_address()
USER_KEY = keys.PrivateKey(b"\x88" * 32)
USER = USER_KEY.public_key.to_checksum_address()
WINNER_KEY = keys.PrivateKey(b"\x99" * 32)
WINNER = WINNER_KEY.public_key.to_checksum_address()
BOUNTY_ESCROW = bounty_escrow_address()


def _sign(message: dict[str, Any]) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return OPERATOR_KEY.sign_msg_hash(digest).to_hex()


def _auth(message: dict[str, Any]) -> dict[str, Any]:
    return {"signer": OPERATOR, "message": message, "signature": _sign(message)}


def _bounty_lock_tx(bounty_id: str = "b-1", amount: int = 500, auth_nonce: str = "lk-1") -> dict[str, Any]:
    message = {
        "bounty_id": bounty_id,
        "user_address": USER,
        "reward_amount": amount,
        "auth_nonce": auth_nonce,
        "chain_id": CHAIN,
    }
    return {
        "from": USER,
        "to": BOUNTY_ESCROW,
        "amount": amount,
        "value": amount,
        "fee": 0,
        "nonce": 0,
        "type": "BOUNTY_LOCK",
        "payload": {"bounty_id": bounty_id, "auth": _auth(message)},
        "chain_id": CHAIN,
    }


def _bounty_payout_tx(
    bounty_id: str = "b-1",
    submission_id: str = "sub-1",
    amount: int = 500,
    auth_nonce: str = "po-1",
    payee: str = WINNER,
) -> dict[str, Any]:
    message = {
        "bounty_id": bounty_id,
        "submission_id": submission_id,
        "to": payee,
        "amount": amount,
        "verified": True,
        "auth_nonce": auth_nonce,
        "chain_id": CHAIN,
    }
    return {
        "from": BOUNTY_ESCROW,
        "to": payee,
        "amount": amount,
        "value": amount,
        "fee": 0,
        "nonce": 0,
        "type": "BOUNTY_PAYOUT",
        "payload": {"bounty_id": bounty_id, "submission_id": submission_id, "auth": _auth(message)},
        "chain_id": CHAIN,
    }


def _bounty_refund_tx(
    bounty_id: str = "b-1",
    amount: int = 500,
    auth_nonce: str = "rf-1",
    payee: str = USER,
) -> dict[str, Any]:
    message = {
        "bounty_id": bounty_id,
        "to": payee,
        "amount": amount,
        "auth_nonce": auth_nonce,
        "chain_id": CHAIN,
    }
    return {
        "from": BOUNTY_ESCROW,
        "to": payee,
        "amount": amount,
        "value": amount,
        "fee": 0,
        "nonce": 0,
        "type": "BOUNTY_REFUND",
        "payload": {"bounty_id": bounty_id, "auth": _auth(message)},
        "chain_id": CHAIN,
    }


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'bounty-2484.db'}", echo=False)
    chain_metadata.create_all(eng)
    return eng


def _session(engine) -> Session:
    s = Session(engine)
    s.add(Account(chain_id=CHAIN, address=USER, balance=10**9, nonce=0))
    s.add(Account(chain_id=CHAIN, address=WINNER, balance=0, nonce=0))
    s.add(Account(chain_id=CHAIN, address=BOUNTY_ESCROW, balance=10**12, nonce=0))
    s.commit()
    return s


def _seal_bounty_tx(session: Session, tx: dict[str, Any], tx_hash: str, height: int = 1) -> None:
    """Persist a sealed Transaction row so ``bounty_flow_state`` sees it."""
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=tx_hash,
            block_height=height,
            sender=tx["from"],
            recipient=tx["to"],
            value=int(tx.get("value", tx.get("amount", 0))),
            type=str(tx.get("type")),
            status="confirmed",
            payload=tx["payload"],
        )
    )
    session.commit()


def _apply(st: StateTransition, session: Session, tx: dict[str, Any], tx_hash: str, version: int = 30):
    return st.apply_transaction(session, CHAIN, tx, tx_hash=tx_hash, block_version=version, block_height=2)


# --- sealed-history invariants ---


def test_v30_payout_within_locked_applies(engine):
    st = StateTransition()
    with _session(engine) as s:
        _seal_bounty_tx(s, _bounty_lock_tx(), "0xlock")
        ok, err = _apply(st, s, _bounty_payout_tx(), "0xpayout")
        assert ok, err


def test_v30_payout_without_lock_rejected(engine):
    """A payout for a bounty that was never locked cannot draw escrow."""
    st = StateTransition()
    with _session(engine) as s:
        ok, err = _apply(st, s, _bounty_payout_tx(), "0xpayout")
        assert ok is False and "no confirmed BOUNTY_LOCK" in err


def test_v30_payout_exceeding_locked_rejected(engine):
    st = StateTransition()
    with _session(engine) as s:
        _seal_bounty_tx(s, _bounty_lock_tx(amount=500), "0xlock")
        ok, err = _apply(st, s, _bounty_payout_tx(amount=600, auth_nonce="po-big"), "0xpayout")
        assert ok is False and "exceeds locked" in err


def test_v30_second_payout_same_submission_rejected(engine):
    """Distinct fresh auths still cannot pay one submission twice (#2484's
    exact gap: the v29 one-shot bound sees different signatures)."""
    st = StateTransition()
    with _session(engine) as s:
        _seal_bounty_tx(s, _bounty_lock_tx(amount=1000), "0xlock")
        _seal_bounty_tx(s, _bounty_payout_tx(submission_id="sub-1", amount=400, auth_nonce="po-a"), "0xpo1")
        ok, err = _apply(st, s, _bounty_payout_tx(submission_id="sub-1", amount=400, auth_nonce="po-b"), "0xpo2")
        assert ok is False and "already paid" in err


def test_v30_second_submission_payout_within_locked_applies(engine):
    """A different submission is a different payout — allowed while the
    summed outflow stays under the lock (partial-payout shape)."""
    st = StateTransition()
    with _session(engine) as s:
        _seal_bounty_tx(s, _bounty_lock_tx(amount=1000), "0xlock")
        _seal_bounty_tx(s, _bounty_payout_tx(submission_id="sub-1", amount=400, auth_nonce="po-a"), "0xpo1")
        ok, err = _apply(st, s, _bounty_payout_tx(submission_id="sub-2", amount=400, auth_nonce="po-b"), "0xpo2")
        assert ok, err


def test_v30_cumulative_payouts_capped_by_lock(engine):
    """Two different submissions can still overdraw the escrow — the sum
    bound catches what the per-submission rule cannot."""
    st = StateTransition()
    with _session(engine) as s:
        _seal_bounty_tx(s, _bounty_lock_tx(amount=500), "0xlock")
        _seal_bounty_tx(s, _bounty_payout_tx(submission_id="sub-1", amount=300, auth_nonce="po-a"), "0xpo1")
        ok, err = _apply(st, s, _bounty_payout_tx(submission_id="sub-2", amount=300, auth_nonce="po-b"), "0xpo2")
        assert ok is False and "exceeds locked" in err


def test_v30_refund_counts_toward_outflow(engine):
    """Payout after refund (or vice versa) is the same escrow drain — the
    combined bound refuses the second leg."""
    st = StateTransition()
    with _session(engine) as s:
        _seal_bounty_tx(s, _bounty_lock_tx(amount=500), "0xlock")
        _seal_bounty_tx(s, _bounty_refund_tx(amount=500, auth_nonce="rf-a"), "0xrf")
        ok, err = _apply(st, s, _bounty_payout_tx(amount=500, auth_nonce="po-a"), "0xpo")
        assert ok is False and "exceeds locked" in err


def test_v30_refund_itself_bounded(engine):
    st = StateTransition()
    with _session(engine) as s:
        _seal_bounty_tx(s, _bounty_lock_tx(amount=500), "0xlock")
        _seal_bounty_tx(s, _bounty_refund_tx(amount=500, auth_nonce="rf-a"), "0xrf1")
        ok, err = _apply(st, s, _bounty_refund_tx(amount=1, auth_nonce="rf-b"), "0xrf2")
        assert ok is False and "exceeds locked" in err


def test_v30_same_block_accumulators(engine):
    """Two payouts applied in one block (no sealed rows between them) are
    still bounded — the in-memory accumulators cover the proposer path."""
    st = StateTransition()
    with _session(engine) as s:
        _seal_bounty_tx(s, _bounty_lock_tx(amount=600), "0xlock")
        ok1, err1 = _apply(st, s, _bounty_payout_tx(submission_id="sub-1", amount=400, auth_nonce="po-a"), "0xpo1")
        assert ok1, err1
        ok2, err2 = _apply(st, s, _bounty_payout_tx(submission_id="sub-2", amount=400, auth_nonce="po-b"), "0xpo2")
        assert ok2 is False and "exceeds locked" in err2
        # and the per-submission rule fires same-block too
        ok3, err3 = _apply(st, s, _bounty_payout_tx(submission_id="sub-1", amount=100, auth_nonce="po-c"), "0xpo3")
        assert ok3 is False and "already paid" in err3


def test_below_v30_invariants_dormant(engine):
    """Replay compat: the same over-lock pair applies at v29 — the live
    v17-ex-bounty-2 payout+refund history depends on this."""
    st = StateTransition()
    with _session(engine) as s:
        _seal_bounty_tx(s, _bounty_lock_tx(amount=500), "0xlock")
        _seal_bounty_tx(s, _bounty_refund_tx(amount=500, auth_nonce="rf-a"), "0xrf")
        ok, err = _apply(st, s, _bounty_payout_tx(amount=500, auth_nonce="po-a"), "0xpo", version=29)
        assert ok, err


def test_v30_unrelated_bounty_unaffected(engine):
    """A second bounty's outflow is independent — b-2 pays fine while b-1
    is exhausted."""
    st = StateTransition()
    with _session(engine) as s:
        _seal_bounty_tx(s, _bounty_lock_tx(bounty_id="b-1", amount=500), "0xlock1")
        _seal_bounty_tx(s, _bounty_lock_tx(bounty_id="b-2", amount=500, auth_nonce="lk-2"), "0xlock2")
        _seal_bounty_tx(s, _bounty_refund_tx(bounty_id="b-1", amount=500, auth_nonce="rf-a"), "0xrf")
        ok, err = _apply(
            st,
            s,
            _bounty_payout_tx(bounty_id="b-2", submission_id="sub-9", amount=500, auth_nonce="po-9"),
            "0xpo9",
        )
        assert ok, err
