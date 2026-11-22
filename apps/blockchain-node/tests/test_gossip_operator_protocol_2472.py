"""#2472: resolved-value protocol transfers become gossip-admissible when bound.

``BOUNTY_PAYOUT``/``BOUNTY_REFUND``/agent ``STAKE_RELEASE`` resolve payee
and amount server-side, so #2457 left them local-queue only. The RPCs now
accept an optional signed ``to``/``amount`` pair (learnable via a
``resolve_only`` probe), verify it against their own resolution, and embed
it in ``payload.auth`` — after which every peer re-verifies the same
binding. Envelopes without the pair still drop at gossip intake.
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

from aitbc_chain.base_models import Account
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.protocol_escrow import bounty_escrow_address, stake_escrow_address
from aitbc_chain.rpc.transactions import _validate_transaction_admission
from aitbc_chain.rpc.utils import gossip_transaction_drop_reason

CHAIN = "ait-test-2472"
OPERATOR_KEY = keys.PrivateKey(b"\x55" * 32)
OPERATOR = OPERATOR_KEY.public_key.to_checksum_address()
USER_KEY = keys.PrivateKey(b"\x66" * 32)
USER = USER_KEY.public_key.to_checksum_address()
ATTACKER = keys.PrivateKey(b"\x99" * 32).public_key.to_checksum_address()
STAKE_ESCROW = stake_escrow_address()
BOUNTY_ESCROW = bounty_escrow_address()


def _sign(message: dict[str, Any], key: keys.PrivateKey = OPERATOR_KEY) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _auth(message: dict[str, Any], signer: str = OPERATOR, key: keys.PrivateKey = OPERATOR_KEY) -> dict[str, Any]:
    return {"signer": signer, "message": message, "signature": _sign(message, key)}


def _operator_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OPERATOR)


def _payout_tx(message_over: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    message = {
        "bounty_id": "b-1",
        "submission_id": "sub-1",
        "to": USER,
        "amount": 500,
        "auth_nonce": "po-1",
        "chain_id": CHAIN,
        **(message_over or {}),
    }
    tx: dict[str, Any] = {
        "from": BOUNTY_ESCROW,
        "to": USER,
        "amount": 500,
        "fee": 0,
        "nonce": 0,
        "type": "BOUNTY_PAYOUT",
        "payload": {"bounty_id": "b-1", "submission_id": "sub-1", "auth": _auth(message)},
        "chain_id": CHAIN,
    }
    tx.update(overrides)
    return tx


def _refund_tx(message_over: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    message = {
        "bounty_id": "b-1",
        "user_address": USER,
        "to": USER,
        "amount": 300,
        "auth_nonce": "re-1",
        "chain_id": CHAIN,
        **(message_over or {}),
    }
    tx: dict[str, Any] = {
        "from": BOUNTY_ESCROW,
        "to": USER,
        "amount": 300,
        "fee": 0,
        "nonce": 0,
        "type": "BOUNTY_REFUND",
        "payload": {"bounty_id": "b-1", "auth": _auth(message)},
        "chain_id": CHAIN,
    }
    tx.update(overrides)
    return tx


def _release_tx(message_over: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    message = {
        "stake_id": "s-1",
        "user_address": USER,
        "to": USER,
        "amount": 700,
        "auth_nonce": "sr-1",
        "chain_id": CHAIN,
        **(message_over or {}),
    }
    tx: dict[str, Any] = {
        "from": STAKE_ESCROW,
        "to": USER,
        "amount": 700,
        "fee": 0,
        "nonce": 0,
        "type": "STAKE_RELEASE",
        "payload": {
            "agent_stake_id": "s-1",
            "lock_tx_hashes": ["0x" + "ab" * 32],
            "auth": _auth(message),
        },
        "chain_id": CHAIN,
    }
    tx.update(overrides)
    return tx


# --- transport pre-filter: bound variants pass ---


def test_bound_bounty_payout_passes(monkeypatch):
    _operator_env(monkeypatch)
    assert gossip_transaction_drop_reason(_payout_tx()) is None


def test_bound_bounty_refund_passes(monkeypatch):
    _operator_env(monkeypatch)
    assert gossip_transaction_drop_reason(_refund_tx()) is None


def test_bound_agent_stake_release_passes(monkeypatch):
    _operator_env(monkeypatch)
    assert gossip_transaction_drop_reason(_release_tx()) is None


# --- unbound / mismatched variants still drop ---


def test_payout_without_amount_dropped(monkeypatch):
    """Legacy envelope (no signed amount) must not ride gossip."""
    _operator_env(monkeypatch)
    msg = {
        "bounty_id": "b-1",
        "submission_id": "sub-1",
        "to": USER,
        "amount": None,
        "auth_nonce": "po-unb-1",
        "chain_id": CHAIN,
    }
    assert gossip_transaction_drop_reason(_payout_tx(msg)) == "invalid_protocol_auth"


def test_payout_amount_mismatch_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _payout_tx(amount=999)
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_payout_repointed_payee_dropped(monkeypatch):
    """A captured auth re-pointed at an attacker's balance must not pass."""
    _operator_env(monkeypatch)
    tx = _payout_tx(**{"to": ATTACKER})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_payout_signed_for_other_payee_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _payout_tx({"to": ATTACKER})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_refund_wrong_escrow_leg_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _refund_tx(**{"from": STAKE_ESCROW})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_release_non_escrow_sender_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _release_tx(**{"from": USER})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_release_amount_mismatch_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _release_tx(amount=1)
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_release_stake_id_mismatch_dropped(monkeypatch):
    _operator_env(monkeypatch)
    tx = _release_tx(payload={"agent_stake_id": "s-2", "auth": _release_tx()["payload"]["auth"]})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


def test_payout_foreign_signature_dropped(monkeypatch):
    _operator_env(monkeypatch)
    message = {
        "bounty_id": "b-1",
        "submission_id": "sub-1",
        "to": USER,
        "amount": 500,
        "auth_nonce": "po-forged-1",
        "chain_id": CHAIN,
    }
    forged = _auth(message, signer=OPERATOR, key=USER_KEY)
    tx = _payout_tx(payload={"bounty_id": "b-1", "submission_id": "sub-1", "auth": forged})
    assert gossip_transaction_drop_reason(tx) == "invalid_protocol_auth"


# --- admission gate (session-backed) ---


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Account(chain_id=CHAIN, address=USER, balance=10**9, nonce=0))
        s.add(Account(chain_id=CHAIN, address=STAKE_ESCROW, balance=10**9, nonce=0))
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


def test_admission_accepts_bound_payout(door):
    door(_payout_tx())


def test_admission_accepts_bound_refund(door):
    door(_refund_tx())


def test_admission_accepts_bound_release(door):
    door(_release_tx())


def test_admission_rejects_unbound_payout(door):
    msg = {
        "bounty_id": "b-1",
        "submission_id": "sub-1",
        "to": USER,
        "amount": None,
        "auth_nonce": "po-unb-2",
        "chain_id": CHAIN,
    }
    with pytest.raises(ValueError):
        door(_payout_tx(msg))


def test_admission_rejects_repointed_release(door):
    with pytest.raises(ValueError):
        door(_release_tx(**{"to": ATTACKER}))


# --- seal-time binding stays conditional for legacy envelopes ---


def test_unbound_payout_message_still_binds_submission_only():
    """Pre-#2472 envelopes (no to/amount) keep sealing on the local path —
    the conditional binds must not reject them."""
    from aitbc_chain.state.state_transition_payload_auth import _payload_auth_binds_transfer

    message = {"bounty_id": "b-1", "submission_id": "sub-1", "chain_id": CHAIN}
    tx = _payout_tx()
    tx["payload"]["auth"] = _auth(message)
    assert _payload_auth_binds_transfer("BOUNTY_PAYOUT", message, tx) is True


def test_bound_payout_message_binds_payee_and_amount():
    from aitbc_chain.state.state_transition_payload_auth import _payload_auth_binds_transfer

    tx = _payout_tx()
    message = tx["payload"]["auth"]["message"]
    assert _payload_auth_binds_transfer("BOUNTY_PAYOUT", message, tx) is True
    tx["to"] = ATTACKER
    assert _payload_auth_binds_transfer("BOUNTY_PAYOUT", message, tx) is False


def test_bound_release_message_binds_amount():
    from aitbc_chain.state.state_transition_payload_auth import _payload_auth_binds_transfer

    tx = _release_tx()
    message = tx["payload"]["auth"]["message"]
    assert _payload_auth_binds_transfer("STAKE_RELEASE", message, tx) is True
    tx["amount"] = 1
    assert _payload_auth_binds_transfer("STAKE_RELEASE", message, tx) is False
