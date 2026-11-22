"""#2485 OPERATOR-AUTH-BURN-REENCODE-1: the one-shot burn keys on
``(signer, auth_nonce)`` — never the signature string.

The #2480 dedup compared ``payload.auth.signature`` verbatim, but the
signature is only *parsed* for verification: hex case and ``0x``-prefix
re-encodings verify identically while comparing unequal, so a copied
auth with a re-encoded signature minted a fresh burn key and replayed.
The burn identity is now ``tx_auth_identity`` = ``signer:auth_nonce``,
both inside the signed message — untamperable without breaking the
signature, and SQL-extractable from sealed payloads so pre-#2485 rows
sealed since #2480 deployed are covered too.

The pending-copy race is closed at admission: a second envelope reusing
a still-unsealed authorization is refused while the original sits in
the mempool (first-come-first-served; the pending row itself is not
burned, so a dropped original frees the authorization again).
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest
from eth_keys import keys
from eth_utils import keccak
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from aitbc_chain.base_models import Account, Transaction
from aitbc_chain.mempool_common import MempoolEntry
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.protocol_escrow import bounty_escrow_address
from aitbc_chain.rpc.transactions import _validate_transaction_admission
from aitbc_chain.state.state_transition import StateTransition

CHAIN = "ait-test-2485"
OPERATOR_KEY = keys.PrivateKey(b"\xaa" * 32)
OPERATOR = OPERATOR_KEY.public_key.to_checksum_address()
USER_KEY = keys.PrivateKey(b"\xbb" * 32)
USER = USER_KEY.public_key.to_checksum_address()
BOUNTY_ESCROW = bounty_escrow_address()


def _sign(message: dict[str, Any]) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return OPERATOR_KEY.sign_msg_hash(digest).to_hex()


def _auth(message: dict[str, Any]) -> dict[str, Any]:
    return {"signer": OPERATOR, "message": message, "signature": _sign(message)}


def _bounty_lock_tx(auth_nonce: str = "bn-1", envelope_nonce: int = 0) -> dict[str, Any]:
    message = {
        "bounty_id": "b-1",
        "user_address": USER,
        "reward_amount": 500,
        "auth_nonce": auth_nonce,
        "chain_id": CHAIN,
    }
    return {
        "from": USER,
        "to": BOUNTY_ESCROW,
        "amount": 500,
        "fee": 0,
        "nonce": envelope_nonce,
        "type": "BOUNTY_LOCK",
        "payload": {"bounty_id": "b-1", "auth": _auth(message)},
        "chain_id": CHAIN,
    }


def _reencode(sig: str, style: str) -> str:
    """Re-encode a signature the way an attacker would: same bytes, new
    string — uppercase hex, dropped ``0x``, or re-prefixed."""
    bare = sig[2:] if sig.startswith("0x") else sig
    if style == "upper":
        return "0x" + bare.upper()
    if style == "noprefix":
        return bare
    if style == "double":
        return "0x0x" + bare
    raise AssertionError(style)


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Account(chain_id=CHAIN, address=USER, balance=10**9, nonce=0))
        s.add(Account(chain_id=CHAIN, address=BOUNTY_ESCROW, balance=10**9, nonce=0))
        s.commit()
        yield s


@pytest.fixture
def door(session, monkeypatch):
    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
    monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OPERATOR)

    def submit(tx: dict[str, Any]) -> None:
        _validate_transaction_admission(tx, None)

    return submit


def _seal_tx(session: Session, tx: dict[str, Any], tx_hash: str = "0xsealed", height: int = 3) -> None:
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=tx_hash,
            block_height=height,
            sender=tx["from"],
            recipient=tx["to"],
            value=int(tx.get("amount", 0)),
            type=str(tx.get("type", "BOUNTY_LOCK")),
            status="confirmed",
            payload=tx["payload"],
        )
    )
    session.commit()


def _add_mempool_row(session: Session, tx: dict[str, Any], tx_hash: str = "0xpending") -> None:
    session.exec(
        text(
            "CREATE TABLE IF NOT EXISTS mempool (chain_id TEXT NOT NULL, tx_hash TEXT NOT NULL, "
            "content TEXT NOT NULL, fee BIGINT DEFAULT 0, size_bytes INTEGER DEFAULT 0, "
            "received_at DOUBLE PRECISION NOT NULL, sender TEXT, nonce INTEGER, signed BOOLEAN, "
            "PRIMARY KEY (chain_id, tx_hash))"
        )
    )
    session.add(
        MempoolEntry(
            chain_id=CHAIN,
            tx_hash=tx_hash,
            content=json.dumps(tx, sort_keys=True),
            fee=0,
            size_bytes=0,
            received_at=1.0,
        )
    )
    session.commit()


# --- re-encoded signature replay: sealed side ---


@pytest.mark.parametrize("style", ["upper", "noprefix"])
def test_admission_rejects_reencoded_signature_replay(door, session, style):
    """Same auth, signature re-encoded — the #2480 string-keyed dedup saw
    a 'new' signature; the (signer, auth_nonce) identity does not."""
    original = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=0)
    _seal_tx(session, original)
    replay = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=9)
    replay["payload"]["auth"]["signature"] = _reencode(replay["payload"]["auth"]["signature"], style)
    with pytest.raises(ValueError, match="authorization"):
        door(replay)


def test_admission_rejects_pending_copy(door, session):
    """The pending-copy race: original still in mempool, copy arrives —
    refused at the door instead of riding beside it into one block."""
    original = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=0)
    _add_mempool_row(session, original)
    copy_tx = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=9)
    with pytest.raises(ValueError, match="authorization"):
        door(copy_tx)


def test_pending_copy_freed_when_original_absent(door, session):
    """No pending row, no sealed row — a fresh auth_nonce admits fine."""
    door(_bounty_lock_tx(auth_nonce="bn-fresh", envelope_nonce=3))


# --- apply side: identity-keyed same-block + sealed dedup ---


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'reencode-2485.db'}", echo=False)
    chain_metadata.create_all(engine)
    return engine


def _session(engine) -> Session:
    s = Session(engine)
    s.add(Account(chain_id=CHAIN, address=USER, balance=10**9, nonce=0))
    s.add(Account(chain_id=CHAIN, address=BOUNTY_ESCROW, balance=10**9, nonce=0))
    s.commit()
    return s


def test_v29_apply_rejects_reencoded_signature_same_block(tmp_path):
    """Two envelopes, one auth, second carries an uppercased signature —
    same-block burn keys on identity, not the signature string."""
    st = StateTransition()
    first = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=0)
    replay = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=7)
    replay["payload"]["auth"]["signature"] = _reencode(replay["payload"]["auth"]["signature"], "upper")
    with _session(_engine(tmp_path)) as s:
        ok1, err1 = st.apply_transaction(s, CHAIN, first, tx_hash="0xfirst", block_version=29, block_height=2)
        assert ok1, err1
        ok2, err2 = st.apply_transaction(s, CHAIN, replay, tx_hash="0xreplay", block_version=29, block_height=2)
        assert ok2 is False and "authorization" in err2


def test_v29_apply_rejects_reencoded_signature_sealed(tmp_path):
    st = StateTransition()
    sealed_tx = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=0)
    replay = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=0)
    replay["payload"]["auth"]["signature"] = _reencode(replay["payload"]["auth"]["signature"], "noprefix")
    with _session(_engine(tmp_path)) as s:
        _seal_tx(s, sealed_tx)
        ok, err = st.apply_transaction(s, CHAIN, replay, tx_hash="0xreplay", block_version=29, block_height=4)
        assert ok is False and "authorization" in err


def test_v29_apply_accepts_distinct_auth_nonce(tmp_path):
    """Legitimate repeats still pass: a new auth_nonce is a new
    authorization even from the same signer."""
    st = StateTransition()
    first = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=0)
    second = _bounty_lock_tx(auth_nonce="bn-2", envelope_nonce=1)
    with _session(_engine(tmp_path)) as s:
        ok1, err1 = st.apply_transaction(s, CHAIN, first, tx_hash="0xfirst", block_version=29, block_height=2)
        assert ok1, err1
        ok2, err2 = st.apply_transaction(s, CHAIN, second, tx_hash="0xsecond", block_version=29, block_height=2)
        assert ok2, err2
