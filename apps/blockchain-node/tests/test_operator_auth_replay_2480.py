"""#2480 OPERATOR-AUTH-REPLAY-1: one-shot ``payload.auth`` for operator transfers.

The #2457/#2472 operator signature covers the signed RPC body but not the
envelope, so a captured ``auth`` replayed under fresh nonce/fee minted a new
tx hash and drained the shared bounty escrow (one sealed ``BOUNTY_PAYOUT``
auth paid 3x). The fix binds a one-shot ``auth_nonce`` inside the signed
message, refuses nonce-less operator auths at admission, burns each
``auth.signature`` at admission (sealed lookup) and at apply (v29:
same-block set + sealed lookup), and keeps legacy no-nonce auths valid
below the v29 height for replay compatibility.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest
from eth_keys import keys
from eth_utils import keccak
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from aitbc_chain.base_models import Account, Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.protocol_escrow import bounty_escrow_address
from aitbc_chain.rpc.transactions import _validate_transaction_admission
from aitbc_chain.rpc.utils import gossip_transaction_drop_reason
from aitbc_chain.state.state_transition import StateTransition

CHAIN = "ait-test-2480"
OPERATOR_KEY = keys.PrivateKey(b"\x55" * 32)
OPERATOR = OPERATOR_KEY.public_key.to_checksum_address()
USER_KEY = keys.PrivateKey(b"\x66" * 32)
USER = USER_KEY.public_key.to_checksum_address()
BOUNTY_ESCROW = bounty_escrow_address()


def _sign(message: dict[str, Any], key: keys.PrivateKey = OPERATOR_KEY) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _auth(message: dict[str, Any]) -> dict[str, Any]:
    return {"signer": OPERATOR, "message": message, "signature": _sign(message)}


def _operator_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OPERATOR)


def _bounty_lock_tx(nonce: int = 0, auth_nonce: str = "bn-1", envelope_nonce: int = 0) -> dict[str, Any]:
    """An operator-signed BOUNTY_LOCK; ``envelope_nonce`` varies the tx hash
    while ``auth_nonce``/``auth`` stay fixed — the replay shape from #2480."""
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


# --- transport pre-filter: auth_nonce is mandatory for operator auths ---


def test_operator_auth_without_auth_nonce_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _bounty_lock_tx()
    del tx["payload"]["auth"]["message"]["auth_nonce"]
    # Re-sign without the nonce so the signature itself stays valid.
    message = dict(tx["payload"]["auth"]["message"].items())
    tx["payload"]["auth"] = _auth(message)
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_operator_auth_with_auth_nonce_passes(monkeypatch):
    _operator_env(monkeypatch)
    assert gossip_transaction_drop_reason(_bounty_lock_tx()) is None


# --- admission gate: nonce requirement + sealed-signature dedup ---


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
    _operator_env(monkeypatch)

    def submit(tx: dict[str, Any]) -> None:
        _validate_transaction_admission(tx, None)

    return submit


def test_admission_rejects_missing_auth_nonce(door):
    tx = _bounty_lock_tx()
    del tx["payload"]["auth"]["message"]["auth_nonce"]
    tx["payload"]["auth"] = _auth(tx["payload"]["auth"]["message"])
    with pytest.raises(ValueError):
        door(tx)


def _seal_auth_row(session: Session, tx: dict[str, Any], *, tx_hash: str = "0xsealed") -> None:
    auth = tx["payload"]["auth"]
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=tx_hash,
            block_height=3,
            sender=tx["from"],
            recipient=tx["to"],
            value=int(tx.get("amount", 0)),
            type=str(tx.get("type", "BOUNTY_LOCK")),
            status="confirmed",
            payload={"bounty_id": "b-1", "auth": auth},
        )
    )
    session.commit()


def test_admission_rejects_sealed_auth_signature_replay(door, session):
    """The #2480 exploit at the door: same auth, fresh envelope nonce."""
    original = _bounty_lock_tx(envelope_nonce=0)
    _seal_auth_row(session, original)
    replay = _bounty_lock_tx(envelope_nonce=9)  # different tx hash, same auth
    with pytest.raises(ValueError, match="authorization"):
        door(replay)


def test_admission_accepts_distinct_auth_nonce(door, session):
    original = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=0)
    _seal_auth_row(session, original)
    fresh = _bounty_lock_tx(auth_nonce="bn-2", envelope_nonce=9)
    door(fresh)  # a new authorization is not a replay


def test_admission_rejects_legacy_sealed_auth_replay(door, session):
    """A pre-#2480 sealed auth (no auth_nonce in the message) is still a
    spent authorization — admission refuses it outright now that operator
    bodies must carry the one-shot nonce."""
    legacy = _bounty_lock_tx()
    message = {k: v for k, v in legacy["payload"]["auth"]["message"].items() if k != "auth_nonce"}
    legacy["payload"]["auth"] = _auth(message)
    _seal_auth_row(session, legacy)
    replay = _bounty_lock_tx(envelope_nonce=4)
    replay["payload"]["auth"] = _auth(message)  # same legacy auth, new envelope
    with pytest.raises(ValueError):
        door(replay)


# --- apply-side v29 gate ---


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'replay-2480.db'}", echo=False)
    chain_metadata.create_all(engine)
    return engine


def _apply(session: Session, st: StateTransition, tx: dict[str, Any], tx_hash: str, version: int):
    return st.apply_transaction(session, CHAIN, tx, tx_hash=tx_hash, block_version=version, block_height=1)


def _seed_accounts(session: Session) -> None:
    session.add(Account(chain_id=CHAIN, address=USER, balance=10**9, nonce=0))
    session.add(Account(chain_id=CHAIN, address=BOUNTY_ESCROW, balance=10**9, nonce=0))
    session.commit()


def test_v29_apply_rejects_same_block_auth_replay(tmp_path):
    """Two envelopes, one auth: the second is refused at v29 (#2480's
    reproduced triple-payout collapses to a single apply)."""
    st = StateTransition()
    first = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=0)
    replay = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=7)
    with Session(_engine(tmp_path)) as session:
        _seed_accounts(session)
        ok1, err1 = _apply(session, st, first, "0xfirst", 29)
        assert ok1, err1
        ok2, err2 = _apply(session, st, replay, "0xreplay", 29)
        assert ok2 is False and "authorization" in err2


def test_v29_apply_rejects_sealed_auth_replay(tmp_path):
    st = StateTransition()
    sealed_tx = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=0)
    replay = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=0)
    with Session(_engine(tmp_path)) as session:
        _seed_accounts(session)
        _seal_auth_row(session, sealed_tx)
        ok, err = _apply(session, st, replay, "0xreplay", 29)
        assert ok is False and "authorization" in err


def test_v29_apply_rejects_missing_auth_nonce(tmp_path):
    """A legacy no-nonce operator auth cannot ride a v29 block."""
    st = StateTransition()
    tx = _bounty_lock_tx()
    del tx["payload"]["auth"]["message"]["auth_nonce"]
    tx["payload"]["auth"] = _auth(tx["payload"]["auth"]["message"])
    with Session(_engine(tmp_path)) as session:
        _seed_accounts(session)
        ok, err = _apply(session, st, tx, "0xlegacy", 29)
        assert ok is False and "auth_nonce" in err


def test_below_v29_same_auth_replay_still_applies(tmp_path):
    """Replay compat: pre-v29 blocks keep the old rules — the same pair
    that v29 refuses both apply at v28 (the dormant rung)."""
    st = StateTransition()
    first = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=0)
    second = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=1)
    with Session(_engine(tmp_path)) as session:
        _seed_accounts(session)
        ok1, err1 = _apply(session, st, first, "0xfirst", 28)
        assert ok1, err1
        ok2, err2 = _apply(session, st, second, "0xsecond", 28)
        assert ok2, err2


def test_v29_apply_accepts_distinct_auth_nonces(tmp_path):
    """Legitimate repeats stay valid: different auth_nonce → different
    signature → both apply."""
    st = StateTransition()
    first = _bounty_lock_tx(auth_nonce="bn-1", envelope_nonce=0)
    second = _bounty_lock_tx(auth_nonce="bn-2", envelope_nonce=1)
    with Session(_engine(tmp_path)) as session:
        _seed_accounts(session)
        ok1, err1 = _apply(session, st, first, "0xfirst", 29)
        assert ok1, err1
        ok2, err2 = _apply(session, st, second, "0xsecond", 29)
        assert ok2, err2
