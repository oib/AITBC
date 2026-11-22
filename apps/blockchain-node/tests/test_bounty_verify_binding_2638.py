"""#2638: ``verify_bounty`` must bind the submission to the path bounty.

``submission_id`` is unique per chain, not per bounty — before the fix the
verify lookup matched on ``submission_id`` alone, so an operator-signed
(bounty B, submission-of-A) pair paid B's escrow to A's submitter and
completed B. The lookup now filters on ``bounty_id`` too: a foreign
submission reads as not-found and nothing moves.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import Mock

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi import HTTPException
from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool

from aitbc_chain.base_models import BountyContract, Transaction, _to_ait_address
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account
from aitbc_chain.rpc import bounty

CHAIN = "test"  # whitelisted by the conftest _allow_test_chain_ids fixture

USER_KEY = keys.PrivateKey(b"\x11" * 32)
USER = USER_KEY.public_key.to_checksum_address()
OP_KEY = keys.PrivateKey(b"\x33" * 32)
OP_ADDR = OP_KEY.public_key.to_checksum_address()
SUBMITTER_KEY = keys.PrivateKey(b"\x44" * 32)
SUBMITTER = SUBMITTER_KEY.public_key.to_checksum_address()


def _sign(message: dict[str, Any], key: keys.PrivateKey) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _signed_operator_body(fields: dict[str, Any]) -> dict[str, Any]:
    return {**fields, "signature": _sign(fields, OP_KEY)}


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def rpc_db(engine, monkeypatch):
    """Route bounty.session_scope at the test engine, arm v17, and stub the
    mempool queue so no real transaction is emitted."""

    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(bounty, "session_scope", _session_scope)
    monkeypatch.setattr(settings, "state_transition_v17_height", 1)
    queued: list[dict[str, Any]] = []

    def _fake_queue(**kwargs):
        queued.append(kwargs)
        return "0x" + "ab" * 32

    monkeypatch.setattr(bounty, "queue_protocol_transfer", _fake_queue)
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OP_ADDR)
    return engine, queued


def _seed_creator(engine, balance: int = 10**9) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=_to_ait_address(USER), balance=balance, nonce=0))
        session.commit()


def _seed_confirmed_lock(engine, bounty_id: str, amount: int, block_height: int = 1) -> None:
    """A sealed BOUNTY_LOCK so _require_funded sees the escrow as funded."""
    with Session(engine) as session:
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash="0x" + keccak(bounty_id.encode()).hex()[:64],
                block_height=block_height,
                sender=_to_ait_address(USER),
                recipient=bounty.bounty_escrow_address(),
                value=amount,
                type="BOUNTY_LOCK",
                payload={"bounty_id": bounty_id},
            )
        )
        session.commit()


def _deploy(bounty_id: str, *, amount: int = 100) -> dict[str, Any]:
    body = {"bounty_id": bounty_id, "user_address": USER, "reward_amount": amount, "chain_id": CHAIN}
    return bounty.deploy_bounty(Mock(), _signed_operator_body(body))


def _submit(bounty_id: str, submission_id: str) -> dict[str, Any]:
    body = {
        "bounty_id": bounty_id,
        "submission_id": submission_id,
        "user_address": SUBMITTER,
        "chain_id": CHAIN,
    }
    return bounty.submit_bounty(Mock(), bounty_id, _signed_operator_body(body))


def _verify(bounty_id: str, submission_id: str, *, verified: bool = True) -> dict[str, Any]:
    body = {
        "bounty_id": bounty_id,
        "submission_id": submission_id,
        "verified": verified,
        "chain_id": CHAIN,
    }
    return bounty.verify_bounty(Mock(), bounty_id, _signed_operator_body(body))


def _bounty_row(engine, bounty_id: str) -> BountyContract:
    with Session(engine) as session:
        return session.exec(
            select(BountyContract).where(BountyContract.chain_id == CHAIN, BountyContract.bounty_id == bounty_id)
        ).one()


def _submission_row(engine, submission_id: str):
    from aitbc_chain.base_models import BountySubmissionRecord

    with Session(engine) as session:
        return session.exec(
            select(BountySubmissionRecord).where(
                BountySubmissionRecord.chain_id == CHAIN,
                BountySubmissionRecord.submission_id == submission_id,
            )
        ).one()


@pytest.mark.asyncio
async def test_verify_rejects_a_submission_made_to_another_bounty(rpc_db):
    """The auditor repro: bounty B verified with a submission recorded
    against bounty A must not pay B's escrow to A's submitter."""
    engine, queued = rpc_db
    _seed_creator(engine)
    _deploy("b-A")
    _deploy("b-B")
    _seed_confirmed_lock(engine, "b-A", 100)
    _seed_confirmed_lock(engine, "b-B", 100)
    _submit("b-A", "sub-for-A")
    queued.clear()

    with pytest.raises(HTTPException) as exc:
        _verify("b-B", "sub-for-A")
    assert exc.value.status_code == 404

    row_b = _bounty_row(engine, "b-B")
    assert row_b.status == "active"
    assert row_b.remaining_amount == 100
    assert row_b.winner_address is None
    assert _submission_row(engine, "sub-for-A").status == "pending"
    assert not [q for q in queued if q["tx_type"] == "BOUNTY_PAYOUT"]


@pytest.mark.asyncio
async def test_verify_own_submission_still_pays(rpc_db):
    """Control: the bound lookup still resolves a submission that does
    belong to the verified bounty."""
    engine, queued = rpc_db
    _seed_creator(engine)
    _deploy("b-own")
    _seed_confirmed_lock(engine, "b-own", 100)
    _submit("b-own", "sub-own")
    queued.clear()

    result = _verify("b-own", "sub-own")

    assert result["success"] is True
    assert result["status"] == "completed"
    payout = next(q for q in queued if q["tx_type"] == "BOUNTY_PAYOUT")
    assert payout["recipient"] == _to_ait_address(SUBMITTER)
    assert payout["amount"] == 100
    row = _bounty_row(engine, "b-own")
    assert row.status == "completed"
    assert row.winner_address == _to_ait_address(SUBMITTER)


@pytest.mark.asyncio
async def test_verify_rejects_rejected_submission_of_same_bounty(rpc_db):
    """Rejecting a submission does not block re-verifying it — status is
    the gate's business, not the binding's; a rejected row still belongs
    to its bounty so the lookup resolves it (existing semantics kept)."""
    engine, queued = rpc_db
    _seed_creator(engine)
    _deploy("b-rej")
    _seed_confirmed_lock(engine, "b-rej", 100)
    _submit("b-rej", "sub-rej")
    _verify("b-rej", "sub-rej", verified=False)
    queued.clear()

    result = _verify("b-rej", "sub-rej")
    assert result["success"] is True
    assert result["status"] == "completed"
