"""#2637: bounty state must not commit before its transfer is queued.

``verify_bounty``/``expire_bounty`` used to commit ``completed``/``expired``
(and zero ``remaining_amount``) before ``queue_protocol_transfer`` ran, so a
refused queue stranded the money movement while the retry answered
idempotent success. ``deploy_bounty`` committed the ``BountyContract`` row
before queueing the BOUNTY_LOCK, leaving an active bounty with no escrow
behind it.

Now the transfer queues first (a refusal leaves the row untouched), the
idempotent branches heal a missing payout/refund/lock instead of reporting
success over a stranded escrow leg, and a failed deploy removes its row.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import Mock

import pytest
from eth_keys import keys
from eth_utils import keccak
from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool

from aitbc_chain.base_models import BountyContract, BountySubmissionRecord, Transaction, _to_ait_address
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
    return engine, queued, monkeypatch


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


def _expire(bounty_id: str) -> dict[str, Any]:
    body = {"bounty_id": bounty_id, "user_address": USER, "chain_id": CHAIN}
    return bounty.expire_bounty(Mock(), bounty_id, _signed_operator_body(body))


def _bounty_row(engine, bounty_id: str) -> BountyContract | None:
    with Session(engine) as session:
        return session.exec(
            select(BountyContract).where(BountyContract.chain_id == CHAIN, BountyContract.bounty_id == bounty_id)
        ).first()


def _submission_row(engine, submission_id: str) -> BountySubmissionRecord | None:
    with Session(engine) as session:
        return session.exec(
            select(BountySubmissionRecord).where(
                BountySubmissionRecord.chain_id == CHAIN,
                BountySubmissionRecord.submission_id == submission_id,
            )
        ).first()


def _refuse_next_queue(monkeypatch, queued: list[dict[str, Any]]) -> None:
    """Make the next queue_protocol_transfer call raise like a full pool,
    then restore the recording stub."""
    calls = {"n": 0}

    def _flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("mempool pool full: fee-0 transfer cannot evict")
        queued.append(kwargs)
        return "0x" + "cd" * 32

    monkeypatch.setattr(bounty, "queue_protocol_transfer", _flaky)


@pytest.mark.asyncio
async def test_verify_queue_refusal_leaves_row_untouched_and_retry_pays(rpc_db):
    """The auditor repro: a refused payout queue must not strand the
    bounty — the row stays un-completed and the retry queues the payout."""
    engine, queued, monkeypatch = rpc_db
    _seed_creator(engine)
    _deploy("b-v")
    _seed_confirmed_lock(engine, "b-v", 100)
    _submit("b-v", "sub-v")
    queued.clear()
    _refuse_next_queue(monkeypatch, queued)

    with pytest.raises(ValueError, match="pool full"):
        _verify("b-v", "sub-v")

    row = _bounty_row(engine, "b-v")
    assert row.status == "submitted"
    assert row.remaining_amount == 100
    assert row.winner_address is None
    assert _submission_row(engine, "sub-v").status == "pending"
    assert not [q for q in queued if q["tx_type"] == "BOUNTY_PAYOUT"]

    result = _verify("b-v", "sub-v")
    assert result["success"] is True
    assert result["status"] == "completed"
    payout = next(q for q in queued if q["tx_type"] == "BOUNTY_PAYOUT")
    assert payout["amount"] == 100
    assert payout["recipient"] == _to_ait_address(SUBMITTER)


@pytest.mark.asyncio
async def test_expire_queue_refusal_leaves_row_untouched_and_retry_refunds(rpc_db):
    """Same contract on the refund leg: refused queue -> row stays active,
    retry expires and queues the BOUNTY_REFUND."""
    engine, queued, monkeypatch = rpc_db
    _seed_creator(engine)
    _deploy("b-e")
    _seed_confirmed_lock(engine, "b-e", 100)
    queued.clear()
    _refuse_next_queue(monkeypatch, queued)

    with pytest.raises(ValueError, match="pool full"):
        _expire("b-e")

    row = _bounty_row(engine, "b-e")
    assert row.status == "active"
    assert row.remaining_amount == 100
    assert not [q for q in queued if q["tx_type"] == "BOUNTY_REFUND"]

    result = _expire("b-e")
    assert result["success"] is True
    assert result["status"] == "expired"
    refund = next(q for q in queued if q["tx_type"] == "BOUNTY_REFUND")
    assert refund["amount"] == 100
    assert refund["recipient"] == _to_ait_address(USER)


@pytest.mark.asyncio
async def test_verify_idempotent_heals_a_missing_payout(rpc_db):
    """A completed row with no payout behind it (crash between queue and
    commit, or pre-fix data) gets the transfer queued on the retry."""
    engine, queued, _monkeypatch = rpc_db
    _seed_creator(engine)
    _deploy("b-h")
    _seed_confirmed_lock(engine, "b-h", 100)
    _submit("b-h", "sub-h")
    # Simulate the stranded state: completed row, verified submission,
    # winner set — but no BOUNTY_PAYOUT queued or sealed.
    with Session(engine) as session:
        bounty_row = session.exec(
            select(BountyContract).where(BountyContract.chain_id == CHAIN, BountyContract.bounty_id == "b-h")
        ).one()
        bounty_row.status = "completed"
        bounty_row.remaining_amount = 0
        bounty_row.winner_address = _to_ait_address(SUBMITTER)
        submission = session.exec(select(BountySubmissionRecord).where(BountySubmissionRecord.submission_id == "sub-h")).one()
        submission.status = "verified"
        session.add_all([bounty_row, submission])
        session.commit()
    queued.clear()

    result = _verify("b-h", "sub-h")

    assert result["success"] is True
    assert result["idempotent"] is True
    assert result["status"] == "completed"
    assert "transaction_hash" in result
    assert result["healed_amount"] == 100
    payout = next(q for q in queued if q["tx_type"] == "BOUNTY_PAYOUT")
    assert payout["amount"] == 100
    assert payout["recipient"] == _to_ait_address(SUBMITTER)
    assert payout["payload"]["submission_id"] == "sub-h"


@pytest.mark.asyncio
async def test_verify_idempotent_does_not_double_queue(rpc_db):
    """Once the payout exists (pending in the stubbed queue), the
    idempotent branch leaves it alone — no second transfer."""
    engine, queued, _monkeypatch = rpc_db
    _seed_creator(engine)
    _deploy("b-h2")
    _seed_confirmed_lock(engine, "b-h2", 100)
    _submit("b-h2", "sub-h2")
    _verify("b-h2", "sub-h2")  # completes with payout queued
    queued.clear()

    # The stub records but does not persist a mempool row, so simulate the
    # pending copy the heal check would see by checking the sealed path is
    # not hit either — instead assert the response stays plain idempotent
    # when a pending entry exists. Seed a MempoolEntry carrying the payout.
    from aitbc_chain.mempool_common import MempoolEntry

    with Session(engine) as session:
        session.add(
            MempoolEntry(
                chain_id=CHAIN,
                tx_hash="0x" + "ee" * 32,
                content=json.dumps(
                    {
                        "type": "BOUNTY_PAYOUT",
                        "payload": {"bounty_id": "b-h2", "submission_id": "sub-h2"},
                    }
                ),
                fee=0,
                size_bytes=1,
                received_at=1.0,
            )
        )
        session.commit()

    result = _verify("b-h2", "sub-h2")
    assert result["success"] is True
    assert result["idempotent"] is True
    assert "transaction_hash" not in result
    assert not [q for q in queued if q["tx_type"] == "BOUNTY_PAYOUT"]


@pytest.mark.asyncio
async def test_expire_idempotent_heals_a_missing_refund(rpc_db):
    """An expired row with no refund behind it gets the BOUNTY_REFUND
    queued on the retry, to the creator for the confirmed lock total."""
    engine, queued, _monkeypatch = rpc_db
    _seed_creator(engine)
    _deploy("b-hr")
    _seed_confirmed_lock(engine, "b-hr", 100)
    with Session(engine) as session:
        bounty_row = session.exec(
            select(BountyContract).where(BountyContract.chain_id == CHAIN, BountyContract.bounty_id == "b-hr")
        ).one()
        bounty_row.status = "expired"
        bounty_row.remaining_amount = 0
        session.add(bounty_row)
        session.commit()
    queued.clear()

    result = _expire("b-hr")

    assert result["success"] is True
    assert result["idempotent"] is True
    assert result["refunded"] == 100
    assert "transaction_hash" in result
    refund = next(q for q in queued if q["tx_type"] == "BOUNTY_REFUND")
    assert refund["amount"] == 100
    assert refund["recipient"] == _to_ait_address(USER)


@pytest.mark.asyncio
async def test_deploy_idempotent_heals_a_missing_lock(rpc_db):
    """An active row with no BOUNTY_LOCK behind it (the pre-fix stranded
    deploy) gets the lock queued on the idempotent retry."""
    engine, queued, _monkeypatch = rpc_db
    _seed_creator(engine)
    with Session(engine) as session:
        session.add(
            BountyContract(
                chain_id=CHAIN,
                bounty_id="b-dh",
                creator_address=_to_ait_address(USER),
                reward_amount=100,
                remaining_amount=100,
                status="active",
            )
        )
        session.commit()
    queued.clear()

    result = _deploy("b-dh")

    assert result["success"] is True
    assert result["idempotent"] is True
    assert "transaction_hash" in result
    lock = next(q for q in queued if q["tx_type"] == "BOUNTY_LOCK")
    assert lock["amount"] == 100
    assert lock["recipient"] == bounty.bounty_escrow_address()


@pytest.mark.asyncio
async def test_deploy_queue_refusal_removes_the_row(rpc_db):
    """A refused BOUNTY_LOCK queue must not leave an active bounty row
    with no escrow behind it — the row is removed and the retry deploys."""
    engine, queued, monkeypatch = rpc_db
    _seed_creator(engine)
    _refuse_next_queue(monkeypatch, queued)

    with pytest.raises(ValueError, match="pool full"):
        _deploy("b-dq")

    assert _bounty_row(engine, "b-dq") is None

    result = _deploy("b-dq")
    assert result["success"] is True
    assert result["status"] == "active"
    assert any(q["tx_type"] == "BOUNTY_LOCK" for q in queued)
