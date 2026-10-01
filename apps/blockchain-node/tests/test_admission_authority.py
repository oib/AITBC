"""Mempool admission refuses authority-gated types from the wrong sender (register V-8).

``validate_transaction`` has always refused a GOVERNANCE_EXECUTE from outside the on-chain executor list and an
ESCROW_RELEASE / ESCROW_REFUND from anyone but the settlement authority, but only when a proposer applied the block.
Every intake door (REST, gossip ingest and the p2p transport all call ``_validate_transaction_admission``) admitted such
a transaction, which then sat in the mempool until a proposer drained and dropped it: on 2026-10-01 a GOVERNANCE_EXECUTE
from the retired executor ``0x02B8...`` was admitted that way and dropped at proposal. These tests pin the door, its
error precedence, and that the admission helper never disagrees with ``validate_transaction``.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from eth_utils import keccak
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_hash
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, ChainParameter, Transaction
from aitbc_chain.config import settings
from aitbc_chain.database import chain_metadata
from aitbc_chain.rpc.transactions import _validate_transaction_admission
from aitbc_chain.state.admission_authority import AUTHORITY_GATED_TYPES, sender_authority_error
from aitbc_chain.state.state_transition import StateTransition

CHAIN = "ait-test"
EXECUTOR = "0x" + "e1" * 20
AUTHORITY = "0x" + "a7" * 20
STRANGER = "0x" + "5a" * 20
BROKE = "0x" + "b0" * 20
NONCED = "0x" + "c3" * 20  # funded, account nonce 7
SENDER_KEY = "0x" + "55" * 32  # signs the matrix transactions: v9 demands a signature before it reaches the authority gate
SENDER = derive_ethereum_address(SENDER_KEY)

# What validate_transaction says when it refuses on authority grounds (and nothing else).
AUTHORITY_MESSAGES = (
    "is not an authorized executor",
    "governance_executors chain parameter is not set",
    "must be signed by settlement authority",
    "requires a settlement authority",
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        for addr in (EXECUTOR, AUTHORITY, STRANGER):
            s.add(Account(chain_id=CHAIN, address=addr, balance=1_000_000, nonce=0))
        s.add(Account(chain_id=CHAIN, address=BROKE, balance=0, nonce=7))
        s.add(Account(chain_id=CHAIN, address=NONCED, balance=1_000_000, nonce=7))
        s.add(Account(chain_id=CHAIN, address=SENDER, balance=1_000_000, nonce=0))
        s.commit()
        yield s


def _set(session: Session, parameter: str, value: str) -> None:
    session.add(ChainParameter(chain_id=CHAIN, parameter=parameter, value=value))
    session.commit()


@pytest.fixture
def door(session, monkeypatch):
    """``_validate_transaction_admission`` wired to the test database, as the next block (v9) would apply it."""

    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
    monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])
    monkeypatch.setattr(settings, "escrow_settlement_authority", "")
    monkeypatch.delenv("ESCROW_RELEASE_ADDRESS", raising=False)
    monkeypatch.setattr(settings, "state_transition_v9_height", 1)

    def submit(tx_type: str, sender: str, **overrides: Any) -> None:
        tx: dict[str, Any] = {
            "from": sender,
            "to": sender,
            "amount": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": 0,
            "type": tx_type,
            "chain_id": CHAIN,
            "payload": {},
        }
        tx.update(overrides)
        _validate_transaction_admission(tx, None)

    return submit


def test_non_executor_governance_execute_is_refused_at_admission(door, session) -> None:
    _set(session, "governance_executors", EXECUTOR)
    with pytest.raises(ValueError, match="is not an authorized executor"):
        door("GOVERNANCE_EXECUTE", STRANGER)


def test_executor_governance_execute_is_admitted(door, session) -> None:
    _set(session, "governance_executors", EXECUTOR)
    door("GOVERNANCE_EXECUTE", EXECUTOR)


def test_unset_executors_refuse_every_sender_from_v5(door) -> None:
    with pytest.raises(ValueError, match="governance_executors chain parameter is not set"):
        door("GOVERNANCE_EXECUTE", EXECUTOR)


def test_unset_executors_stay_lenient_below_v5(door, monkeypatch) -> None:
    """Below v5 the apply side accepts an execute with no allowlist, so admission must not be stricter."""
    monkeypatch.setattr(settings, "state_transition_v9_height", 0)
    door("GOVERNANCE_EXECUTE", STRANGER)


@pytest.mark.parametrize("tx_type", ["ESCROW_RELEASE", "ESCROW_REFUND"])
def test_non_authority_escrow_settlement_is_refused_at_admission(door, session, tx_type) -> None:
    _set(session, "escrow_settlement_authority", AUTHORITY)
    with pytest.raises(ValueError, match="must be signed by settlement authority"):
        door(tx_type, STRANGER)


@pytest.mark.parametrize("tx_type", ["ESCROW_RELEASE", "ESCROW_REFUND"])
def test_authority_escrow_settlement_is_admitted(door, session, tx_type) -> None:
    _set(session, "escrow_settlement_authority", AUTHORITY)
    door(tx_type, AUTHORITY)


def test_unset_settlement_authority_refuses_escrow_from_v5(door) -> None:
    with pytest.raises(ValueError, match="requires a settlement authority"):
        door("ESCROW_RELEASE", AUTHORITY)


def test_other_types_are_not_authority_gated(door, session) -> None:
    _set(session, "governance_executors", EXECUTOR)
    _set(session, "escrow_settlement_authority", AUTHORITY)
    door("TRANSFER", STRANGER, to=EXECUTOR, amount=1)


def test_earlier_rejections_keep_their_message(door, session) -> None:
    """The authority check runs last, so an unfunded or mis-nonced sender still sees the old message."""
    _set(session, "governance_executors", EXECUTOR)
    with pytest.raises(ValueError, match="insufficient balance"):
        door("GOVERNANCE_EXECUTE", BROKE, nonce=7)
    with pytest.raises(ValueError, match="stale nonce"):
        door("GOVERNANCE_EXECUTE", NONCED, nonce=0)


def test_the_gated_types_are_the_validate_transaction_sender_gates() -> None:
    assert AUTHORITY_GATED_TYPES == {"GOVERNANCE_EXECUTE", "ESCROW_RELEASE", "ESCROW_REFUND"}


def _signed(tx: dict[str, Any]) -> dict[str, Any]:
    signable = {k: v for k, v in tx.items() if k != "signature"}
    if "amount" in signable:
        signable.pop("value", None)  # the signed form carries amount, not value (see test_governance_execute_gate._make_tx)
    digest = "0x" + keccak(json.dumps(signable, sort_keys=True, separators=(",", ":")).encode()).hex()
    return {**tx, "signature": sign_transaction_hash(digest, SENDER_KEY)}


@pytest.mark.parametrize("block_version", [2, 3, 4, 5, 9])
@pytest.mark.parametrize("tx_type", sorted(AUTHORITY_GATED_TYPES))
@pytest.mark.parametrize("parameter_state", ["unset", "names_sender", "names_other"])
def test_helper_never_disagrees_with_validate_transaction(
    session, monkeypatch, block_version, tx_type, parameter_state
) -> None:
    """Admission may only refuse what apply refuses, with the same message, at every version and parameter state."""
    monkeypatch.setattr(settings, "escrow_settlement_authority", "")
    monkeypatch.delenv("ESCROW_RELEASE_ADDRESS", raising=False)
    parameter = "governance_executors" if tx_type == "GOVERNANCE_EXECUTE" else "escrow_settlement_authority"
    if parameter_state == "names_sender":
        _set(session, parameter, SENDER)
    elif parameter_state == "names_other":
        _set(session, parameter, EXECUTOR if tx_type == "GOVERNANCE_EXECUTE" else AUTHORITY)
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash="lock-job1",
            block_height=None,
            sender=SENDER,
            recipient=AUTHORITY,
            payload={"job_id": "job1", "provider": "provider1"},
            value=100,
            fee=0,
            nonce=0,
            type="ESCROW_LOCK",
            status="confirmed",
            timestamp=datetime.now(UTC).isoformat(),
        )
    )
    session.commit()
    if tx_type == "GOVERNANCE_EXECUTE":
        recipient = SENDER
        payload: dict[str, Any] = {
            "proposal_id": "p1",
            "execution_payload": {"action": "parameter_change", "parameter": "x", "value": "1"},
        }
    else:
        recipient, payload = ("provider1" if tx_type == "ESCROW_RELEASE" else SENDER), {"job_id": "job1"}
    tx = _signed(
        {
            "from": SENDER,
            "to": recipient,
            "value": 0,
            "amount": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": 0,
            "type": tx_type,
            "chain_id": CHAIN,
            "payload": payload,
        }
    )
    ok, message = StateTransition().validate_transaction(
        session, CHAIN, tx, f"tx-{block_version}-{tx_type}-{parameter_state}", block_version=block_version
    )
    mine = sender_authority_error(session, CHAIN, tx_type, SENDER, block_version=block_version)
    if mine is not None:
        assert (ok, message) == (False, mine)
    else:
        assert ok or not any(m in message for m in AUTHORITY_MESSAGES), message
