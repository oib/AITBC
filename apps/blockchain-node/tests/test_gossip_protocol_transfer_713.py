"""#713: unsigned staking-protocol transfers must survive gossip/P2P intake.

``queue_protocol_transfer`` emits STAKE_LOCK/STAKE_RELEASE without a
top-level signature — the keyless escrow cannot sign and the user's wallet
signature rides in ``payload.auth`` instead. #2396 added peer fan-out, but
``gossip_transaction_drop_reason`` dropped every unsigned envelope as
``missing_signature``, so a stake submitted to a non-proposing host sat in
its local mempool until TTL and never sealed.

The carve admits exactly the user-signed staking pair, and only when
``payload.auth`` re-verifies end-to-end: signature recovers to ``signer``,
the signed message binds the transfer (party/chain/action/amount/stake
id), the signer is the user leg (staker on a lock, payee on a release),
the other leg is the canonical stake escrow, and the signed timestamp +
nonce are fresh. The nonce *value* is checked against chain state at
admission so a captured auth cannot be replayed after the account moves.
Operator-signed protocol transfers whose signed body fully binds the
envelope joined the carve under #2457 (see
test_gossip_operator_protocol_2457.py); types whose payee/amount are
resolved server-side after signing remain local-queue only.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any

import pytest
from eth_keys import keys
from eth_utils import keccak
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account
from aitbc_chain.protocol_escrow import stake_escrow_address
from aitbc_chain.rpc.transactions import _validate_transaction_admission
from aitbc_chain.rpc.utils import gossip_transaction_drop_reason

CHAIN = "ait-test-713"
STAKER_KEY = keys.PrivateKey(b"\x77" * 32)
STAKER = STAKER_KEY.public_key.to_checksum_address()
OTHER_KEY = keys.PrivateKey(b"\x88" * 32)
ESCROW = stake_escrow_address()


def _sign(message: dict[str, Any], key: keys.PrivateKey = STAKER_KEY) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _fresh_message(**overrides: Any) -> dict[str, Any]:
    message: dict[str, Any] = {
        "address": STAKER,
        "amount": 1000,
        "chain_id": CHAIN,
        "action": "stake",
        "nonce": 0,
        "timestamp": time.time(),
    }
    message.update(overrides)
    return message


def _auth(message: dict[str, Any], signer: str = STAKER, key: keys.PrivateKey = STAKER_KEY) -> dict[str, Any]:
    return {"signer": signer, "message": message, "signature": _sign(message, key)}


def _stake_lock_tx(**overrides: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": STAKER,
        "to": ESCROW,
        "amount": 1000,
        "fee": 0,
        "nonce": 0,
        "type": "STAKE_LOCK",
        "payload": {"stake_id": "7", "lock_days": 1, "auth": _auth(_fresh_message())},
        "chain_id": CHAIN,
    }
    tx.update(overrides)
    return tx


def _stake_release_tx(**overrides: Any) -> dict[str, Any]:
    message = _fresh_message(action="unstake", stake_id="7")
    tx: dict[str, Any] = {
        "from": ESCROW,
        "to": STAKER,
        "amount": 1000,
        "fee": 0,
        "nonce": 0,
        "type": "STAKE_RELEASE",
        "payload": {"stake_id": "7", "lock_tx_hashes": ["0x" + "ab" * 32], "auth": _auth(message)},
        "chain_id": CHAIN,
    }
    tx.update(overrides)
    return tx


# --- transport pre-filter (gossip_transaction_drop_reason) ---


def test_valid_stake_lock_passes_drop_reason():
    assert gossip_transaction_drop_reason(_stake_lock_tx()) is None


def test_valid_stake_release_passes_drop_reason():
    assert gossip_transaction_drop_reason(_stake_release_tx()) is None


def test_stake_lock_without_auth_dropped():
    tx = _stake_lock_tx(payload={"stake_id": "7"})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_stake_lock_forged_signature_dropped():
    message = _fresh_message()
    forged = _auth(message, key=OTHER_KEY)  # signature recovers to OTHER, not STAKER
    tx = _stake_lock_tx(payload={"stake_id": "7", "auth": forged})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_stake_lock_signer_must_be_sender():
    """A valid signature by a third party must not move the staker's funds."""
    message = _fresh_message(address=OTHER_KEY.public_key.to_checksum_address())
    auth = _auth(message, signer=OTHER_KEY.public_key.to_checksum_address(), key=OTHER_KEY)
    tx = _stake_lock_tx(payload={"stake_id": "7", "auth": auth})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_stake_lock_recipient_must_be_escrow():
    """A replayed auth re-pointed at an attacker address is refused."""
    attacker = OTHER_KEY.public_key.to_checksum_address()
    tx = _stake_lock_tx(to=attacker)
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_stake_release_sender_must_be_escrow():
    attacker = OTHER_KEY.public_key.to_checksum_address()
    tx = _stake_release_tx(**{"from": attacker})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_stake_release_payee_must_be_signer():
    """A release paying someone other than the signer is refused."""
    message = _fresh_message(action="unstake", stake_id="7", address=STAKER)
    auth = _auth(message, signer=OTHER_KEY.public_key.to_checksum_address(), key=OTHER_KEY)
    tx = _stake_release_tx(payload={"stake_id": "7", "auth": auth})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_stake_lock_stale_timestamp_dropped():
    message = _fresh_message(timestamp=time.time() - 3600)
    tx = _stake_lock_tx(payload={"stake_id": "7", "auth": _auth(message)})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_stake_lock_missing_nonce_dropped():
    message = _fresh_message()
    del message["nonce"]
    tx = _stake_lock_tx(payload={"stake_id": "7", "auth": _auth(message)})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_stake_lock_amount_must_match():
    message = _fresh_message(amount=500)
    tx = _stake_lock_tx(payload={"stake_id": "7", "auth": _auth(message)})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_unsigned_transfer_still_missing_signature():
    tx = _stake_lock_tx(type="TRANSFER", payload={}, **{"to": "0x" + "00" * 20})
    assert gossip_transaction_drop_reason(tx) == "missing_signature"


def test_unbond_without_auth_dropped():
    """STAKE_UNBOND joined the gossipable set under #2457 but still needs
    admissible operator auth — a bare envelope is refused."""
    tx = _stake_lock_tx(type="STAKE_UNBOND", payload={"agent_stake_id": "1"})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


# --- admission gate (session-backed, shared by gossip + p2p) ---


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Account(chain_id=CHAIN, address=STAKER, balance=10**9, nonce=0))
        s.add(Account(chain_id=CHAIN, address=ESCROW, balance=10**9, nonce=0))
        s.commit()
        yield s


@pytest.fixture
def door(session, monkeypatch):
    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
    monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])

    def submit(tx: dict[str, Any]) -> None:
        _validate_transaction_admission(tx, None)

    return submit


def test_admission_accepts_valid_stake_lock(door):
    door(_stake_lock_tx())


def test_admission_accepts_valid_stake_release(door):
    door(_stake_release_tx())


def test_admission_rejects_replayed_auth_after_nonce_moves(door, session):
    """The signed nonce must equal the signer's live account nonce."""
    account = session.get(Account, (CHAIN, STAKER))
    account.nonce = 1
    session.add(account)
    session.commit()
    with pytest.raises(ValueError, match="stale payload.auth nonce"):
        door(_stake_lock_tx())


def test_admission_rejects_missing_signer_account(door, session):
    account = session.get(Account, (CHAIN, STAKER))
    session.delete(account)
    session.commit()
    with pytest.raises(ValueError):
        door(_stake_lock_tx())


def test_admission_still_checks_sender_balance(door, session):
    account = session.get(Account, (CHAIN, STAKER))
    account.balance = 10
    session.add(account)
    session.commit()
    with pytest.raises(ValueError, match="insufficient balance"):
        door(_stake_lock_tx())
