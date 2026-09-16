"""Regression tests: protocol-transfer authorization evidence (GAP-42).

STAKE_LOCK/STAKE_RELEASE are queued unsigned by design — the staking escrow
is keyless and cannot sign a release. The RPC layer now embeds the request
signature it already verified as ``payload.auth = {signer, message,
signature}``, so the block record carries provable authorization rather than
trusting the serving node, and ``validate_transaction`` re-verifies the auth
when present — rejecting malformed or mismatched evidence while pre-auth
history (the sealed STAKE_LOCK in block 7306) keeps replaying identically.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from eth_keys import keys
from eth_utils import keccak
from sqlalchemy import create_engine, text
from sqlmodel import Session

from aitbc_chain.metadata import chain_metadata
from aitbc_chain.protocol_escrow import queue_protocol_transfer
from aitbc_chain.state.state_transition import StateTransition

CHAIN = "test"
STAKER_KEY = keys.PrivateKey(b"\x11" * 32)
STAKER = STAKER_KEY.public_key.to_checksum_address()
OTHER_KEY = keys.PrivateKey(b"\x22" * 32)
ESCROW = "0x0000000000000000000000000000000000e5c09"


def _sign(message: dict[str, Any], key: keys.PrivateKey = STAKER_KEY) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _auth(message: dict[str, Any], signer: str = STAKER, key: keys.PrivateKey = STAKER_KEY) -> dict[str, Any]:
    return {"signer": signer, "message": message, "signature": _sign(message, key)}


def _stake_tx(tx_type: str, payload: dict[str, Any], *, sender: str, recipient: str) -> dict[str, Any]:
    return {
        "from": sender,
        "to": recipient,
        "amount": 1000,
        "value": 1000,
        "fee": 0,
        "nonce": 0,
        "type": tx_type,
        "payload": payload,
        "chain_id": CHAIN,
    }


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    chain_metadata.create_all(engine)
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    with Session(engine) as session:
        for addr, balance in ((STAKER, 10**9), (ESCROW, 10**9)):
            session.execute(
                text(
                    "INSERT INTO account (chain_id, address, balance, nonce, updated_at) "
                    "VALUES (:chain_id, :addr, :balance, 0, :now)"
                ),
                {"chain_id": CHAIN, "addr": addr, "balance": balance, "now": now},
            )
        session.commit()
    yield engine
    engine.dispose()


def test_stake_lock_with_valid_auth_accepted(engine):
    message = {"address": STAKER, "amount": 1000, "chain_id": CHAIN, "action": "stake"}
    tx = _stake_tx("STAKE_LOCK", {"stake_id": "7", "auth": _auth(message)}, sender=STAKER, recipient=ESCROW)
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xlock-auth")
    assert ok is True, msg


def test_stake_lock_with_mismatched_auth_rejected(engine):
    """A signature that does not recover to the claimed signer is rejected."""
    message = {"address": STAKER, "amount": 1000, "chain_id": CHAIN, "action": "stake"}
    forged = _auth(message, key=OTHER_KEY)  # signed by OTHER_KEY, claims STAKER
    tx = _stake_tx("STAKE_LOCK", {"stake_id": "7", "auth": forged}, sender=STAKER, recipient=ESCROW)
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xlock-forged")
    assert ok is False
    assert "auth" in msg.lower()


def test_stake_lock_without_auth_still_accepted(engine):
    """Pre-auth history must keep replaying: block 7306 sealed an auth-less STAKE_LOCK."""
    tx = _stake_tx("STAKE_LOCK", {"stake_id": "1", "lock_days": 30}, sender=STAKER, recipient=ESCROW)
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xlock-legacy")
    assert ok is True, msg


def test_stake_release_with_valid_auth_accepted(engine):
    """The escrow sender is keyless; the user's unstake signature rides in payload.auth."""
    message = {"address": STAKER, "stake_id": "7", "chain_id": CHAIN, "action": "unstake"}
    tx = _stake_tx("STAKE_RELEASE", {"stake_id": "7", "auth": _auth(message)}, sender=ESCROW, recipient=STAKER)
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xrelease-auth")
    assert ok is True, msg


def test_stake_release_with_malformed_auth_rejected(engine):
    tx = _stake_tx(
        "STAKE_RELEASE",
        {"stake_id": "7", "auth": {"signer": STAKER}},  # no message/signature
        sender=ESCROW,
        recipient=STAKER,
    )
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xrelease-bad")
    assert ok is False
    assert "auth" in msg.lower()


def test_stake_lock_auth_must_name_the_debited_sender(engine):
    """A signature naming a different address cannot ride another account's lock."""
    message = {"address": OTHER_KEY.public_key.to_checksum_address(), "amount": 1000, "chain_id": CHAIN, "action": "stake"}
    auth = _auth(message, signer=OTHER_KEY.public_key.to_checksum_address(), key=OTHER_KEY)
    tx = _stake_tx("STAKE_LOCK", {"stake_id": "7", "auth": auth}, sender=STAKER, recipient=ESCROW)
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xlock-wrong-party")
    assert ok is False
    assert "auth" in msg.lower()


def test_stake_lock_auth_amount_must_match_transfer(engine):
    """A 1000-unit signature must not authorize a 5000-unit lock."""
    message = {"address": STAKER, "amount": 1000, "chain_id": CHAIN, "action": "stake"}
    tx = _stake_tx("STAKE_LOCK", {"stake_id": "7", "auth": _auth(message)}, sender=STAKER, recipient=ESCROW)
    tx["value"] = 5000
    tx["amount"] = 5000
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xlock-amount")
    assert ok is False
    assert "auth" in msg.lower()


def test_stake_lock_auth_action_cannot_cross_type(engine):
    """An "unstake" signature must not ride on a STAKE_LOCK."""
    message = {"address": STAKER, "stake_id": "7", "amount": 1000, "chain_id": CHAIN, "action": "unstake"}
    tx = _stake_tx("STAKE_LOCK", {"stake_id": "7", "auth": _auth(message)}, sender=STAKER, recipient=ESCROW)
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xlock-xtype")
    assert ok is False
    assert "auth" in msg.lower()


def test_stake_lock_auth_chain_id_must_match(engine):
    """A signature captured on another chain is rejected."""
    message = {"address": STAKER, "amount": 1000, "chain_id": "other-chain", "action": "stake"}
    tx = _stake_tx("STAKE_LOCK", {"stake_id": "7", "auth": _auth(message)}, sender=STAKER, recipient=ESCROW)
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xlock-xchain")
    assert ok is False
    assert "auth" in msg.lower()


def test_stake_lock_agent_style_auth_accepted(engine):
    """Operator-signed agent staking binds via user_address + amount + stake id."""
    operator = OTHER_KEY.public_key.to_checksum_address()
    message = {
        "stake_id": "agent-9",
        "user_address": STAKER,
        "agent_wallet": operator,
        "amount": 1000,
        "chain_id": CHAIN,
    }
    auth = _auth(message, signer=operator, key=OTHER_KEY)
    tx = _stake_tx("STAKE_LOCK", {"agent_stake_id": "agent-9", "auth": auth}, sender=STAKER, recipient=ESCROW)
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xlock-agent")
    assert ok is True, msg


def test_stake_lock_agent_auth_wrong_stake_id_rejected(engine):
    """An operator signature for stake 'agent-8' must not lock 'agent-9'."""
    operator = OTHER_KEY.public_key.to_checksum_address()
    message = {
        "stake_id": "agent-8",
        "user_address": STAKER,
        "agent_wallet": operator,
        "amount": 1000,
        "chain_id": CHAIN,
    }
    auth = _auth(message, signer=operator, key=OTHER_KEY)
    tx = _stake_tx("STAKE_LOCK", {"agent_stake_id": "agent-9", "auth": auth}, sender=STAKER, recipient=ESCROW)
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xlock-agent-8")
    assert ok is False
    assert "auth" in msg.lower()


def test_stake_release_auth_must_name_the_payee(engine):
    """Replay: a captured unstake signature must not release to a different payee."""
    message = {"address": STAKER, "stake_id": "7", "chain_id": CHAIN, "action": "unstake"}
    tx = _stake_tx(
        "STAKE_RELEASE",
        {"stake_id": "7", "auth": _auth(message)},
        sender=ESCROW,
        recipient=OTHER_KEY.public_key.to_checksum_address(),
    )
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xrelease-other")
    assert ok is False
    assert "auth" in msg.lower()


def test_stake_release_auth_wrong_stake_id_rejected(engine):
    """A signature over stake 8 must not release stake 7."""
    message = {"address": STAKER, "stake_id": "8", "chain_id": CHAIN, "action": "unstake"}
    tx = _stake_tx("STAKE_RELEASE", {"stake_id": "7", "auth": _auth(message)}, sender=ESCROW, recipient=STAKER)
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xrelease-8")
    assert ok is False
    assert "auth" in msg.lower()


def test_stake_release_auth_without_stake_id_rejected(engine):
    """A release auth that names no stake cannot be bound — fail closed."""
    message = {"address": STAKER, "chain_id": CHAIN, "action": "unstake"}
    tx = _stake_tx("STAKE_RELEASE", {"stake_id": "7", "auth": _auth(message)}, sender=ESCROW, recipient=STAKER)
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xrelease-noid")
    assert ok is False
    assert "auth" in msg.lower()


def test_stake_lock_auth_without_named_party_rejected(engine):
    """A valid signature that names no account binds to nothing — fail closed."""
    message = {"amount": 1000, "chain_id": CHAIN, "action": "stake"}
    tx = _stake_tx("STAKE_LOCK", {"stake_id": "7", "auth": _auth(message)}, sender=STAKER, recipient=ESCROW)
    with Session(engine) as session:
        ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "0xlock-noname")
    assert ok is False
    assert "auth" in msg.lower()


def test_queue_protocol_transfer_embeds_auth_in_payload():
    mempool = MagicMock()
    mempool.add = MagicMock(return_value="0xqueued")
    message = {"address": STAKER, "amount": 5, "chain_id": CHAIN, "action": "stake"}
    auth = _auth(message)
    with patch("aitbc_chain.mempool.get_mempool", return_value=mempool):
        queue_protocol_transfer(
            sender=STAKER,
            recipient=ESCROW,
            amount=5,
            chain_id=CHAIN,
            tx_type="STAKE_LOCK",
            payload={"stake_id": "9"},
            auth=auth,
        )
    queued = mempool.add.call_args[0][0]
    assert queued["payload"]["auth"] == auth
    assert queued["payload"]["stake_id"] == "9"
    # Unsigned at the top level by design — authorization lives in the payload.
    assert "signature" not in queued


def test_queue_protocol_transfer_without_auth_unchanged():
    """Protocol-initiated transfers (AUTO_STAKE) carry no auth and are unchanged."""
    mempool = MagicMock()
    mempool.add = MagicMock(return_value="0xqueued")
    with patch("aitbc_chain.mempool.get_mempool", return_value=mempool):
        queue_protocol_transfer(
            sender=STAKER,
            recipient=ESCROW,
            amount=5,
            chain_id=CHAIN,
            tx_type="STAKE_LOCK",
            payload={"stake_id": "9", "source": "auto_stake"},
        )
    queued = mempool.add.call_args[0][0]
    assert "auth" not in queued["payload"]
