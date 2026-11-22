"""#2630/#2631/#2639/#2640/#2641: bounty + agent-stake audit cluster.

- #2630 ``stake_tokens`` committed the active Stake row before the
  STAKE_LOCK queued — a refused queue left voting power backed by no
  lock. The row is now removed on queue refusal.
- #2631 the agent-staking performance/distribute/claim memos had no
  dedupe — a replayed operator-signed body wrote another row. Memos now
  dedupe on the canonical payload hash.
- #2639 ``submit_bounty`` answered idempotent success for an existing
  submission_id even when the request named another bounty — now the
  stored row must match bounty and submitter.
- #2640 ``dispute_bounty`` only set a status label — verify still paid
  and expire still refunded a disputed bounty. Both money paths now
  refuse while disputed; re-dispute is idempotent and an expired bounty
  can no longer be disputed.
- #2641 ``deploy_bounty``/``create_agent_stake`` answered idempotent
  success for an existing id even when the request named another
  creator, amount or term — the stored record must now match the
  request.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any
from unittest.mock import Mock

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi import HTTPException
from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool

from aitbc_chain.base_models import (
    AgentStakeMemo,
    AgentStakeRecord,
    BountyContract,
    Stake,
    _to_ait_address,
)
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account
from aitbc_chain.rpc import agent_staking, bounty, staking

CHAIN = "test"  # whitelisted by the conftest _allow_test_chain_ids fixture

USER_KEY = keys.PrivateKey(b"\x11" * 32)
USER = USER_KEY.public_key.to_checksum_address()
USER2_KEY = keys.PrivateKey(b"\x22" * 32)
USER2 = USER2_KEY.public_key.to_checksum_address()
OP_KEY = keys.PrivateKey(b"\x33" * 32)
OP_ADDR = OP_KEY.public_key.to_checksum_address()
AGENT = _to_ait_address("0x" + "ab" * 20)


def _sign(message: dict[str, Any], key: keys.PrivateKey) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _op_body(fields: dict[str, Any]) -> dict[str, Any]:
    return {**fields, "signature": _sign(fields, OP_KEY)}


def _stake_body(amount: int = 1000, *, nonce: int = 0, lock_days: int = 30) -> dict[str, Any]:
    message = {
        "address": USER.lower(),
        "chain_id": CHAIN,
        "action": "stake",
        "nonce": nonce,
        "timestamp": time.time(),
        "amount": amount,
    }
    return {
        **message,
        "address": USER,
        "lock_days": lock_days,
        "signature": _sign(message, USER_KEY),
    }


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def rpc_db(engine, monkeypatch):
    """Route all three modules' session_scope at the test engine, arm v17,
    and stub each module's mempool queue."""

    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    for module in (bounty, staking, agent_staking):
        monkeypatch.setattr(module, "session_scope", _session_scope)
    monkeypatch.setattr(settings, "state_transition_v17_height", 1)
    queued: list[dict[str, Any]] = []

    def _fake_queue(**kwargs):
        queued.append(kwargs)
        return "0x" + "ab" * 32

    for module in (bounty, staking, agent_staking):
        monkeypatch.setattr(module, "queue_protocol_transfer", _fake_queue)
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OP_ADDR)
    return engine, queued, monkeypatch


def _seed_account(engine, address: str = USER, balance: int = 10**9, nonce: int = 0) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=_to_ait_address(address), balance=balance, nonce=nonce))
        session.commit()


def _deploy(bounty_id: str, *, amount: int = 100, creator: str = USER, deadline: int | None = None) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "bounty_id": bounty_id,
        "user_address": creator,
        "reward_amount": amount,
        "chain_id": CHAIN,
    }
    if deadline is not None:
        fields["deadline_height"] = deadline
    return bounty.deploy_bounty(Mock(), _op_body(fields))


def _submit(bounty_id: str, submission_id: str, *, submitter: str = USER) -> dict[str, Any]:
    body = {
        "bounty_id": bounty_id,
        "submission_id": submission_id,
        "user_address": submitter,
        "chain_id": CHAIN,
    }
    return bounty.submit_bounty(Mock(), bounty_id, _op_body(body))


def _verify(bounty_id: str, submission_id: str, *, verified: bool = True) -> dict[str, Any]:
    body = {
        "bounty_id": bounty_id,
        "submission_id": submission_id,
        "verified": verified,
        "chain_id": CHAIN,
    }
    return bounty.verify_bounty(Mock(), bounty_id, _op_body(body))


def _expire(bounty_id: str) -> dict[str, Any]:
    body = {"bounty_id": bounty_id, "user_address": USER, "chain_id": CHAIN}
    return bounty.expire_bounty(Mock(), bounty_id, _op_body(body))


def _dispute(bounty_id: str, *, submission_id: str | None = None) -> dict[str, Any]:
    fields: dict[str, Any] = {"bounty_id": bounty_id, "chain_id": CHAIN}
    if submission_id:
        fields["submission_id"] = submission_id
    return bounty.dispute_bounty(Mock(), bounty_id, _op_body(fields))


def _bounty_row(engine, bounty_id: str) -> BountyContract | None:
    with Session(engine) as session:
        return session.exec(
            select(BountyContract).where(BountyContract.chain_id == CHAIN, BountyContract.bounty_id == bounty_id)
        ).first()


def _stake_rows(engine) -> list[Stake]:
    with Session(engine) as session:
        return list(session.exec(select(Stake).where(Stake.chain_id == CHAIN)).all())


def _memo_rows(engine) -> list[AgentStakeMemo]:
    with Session(engine) as session:
        return list(session.exec(select(AgentStakeMemo).where(AgentStakeMemo.chain_id == CHAIN)).all())


def _refuse_next_queue(module, monkeypatch, queued: list[dict[str, Any]]) -> None:
    calls = {"n": 0}

    def _flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("mempool pool full: fee-0 transfer cannot evict")
        queued.append(kwargs)
        return "0x" + "cd" * 32

    monkeypatch.setattr(module, "queue_protocol_transfer", _flaky)


# --- #2630: stake row must not survive a refused lock queue -------------


@pytest.mark.asyncio
async def test_stake_queue_refusal_removes_row_and_retry_stakes(rpc_db):
    """A refused STAKE_LOCK queue must not leave an active Stake row —
    voting power backed by no lock."""
    engine, queued, monkeypatch = rpc_db
    _seed_account(engine)
    _refuse_next_queue(staking, monkeypatch, queued)

    with pytest.raises(ValueError, match="pool full"):
        staking.stake_tokens(Mock(), _stake_body())

    assert _stake_rows(engine) == []
    assert not [q for q in queued if q["tx_type"] == "STAKE_LOCK"]

    result = staking.stake_tokens(Mock(), _stake_body())
    assert result["success"] is True
    rows = _stake_rows(engine)
    assert len(rows) == 1
    assert rows[0].status == "active"
    lock = next(q for q in queued if q["tx_type"] == "STAKE_LOCK")
    assert lock["payload"]["stake_id"] == str(rows[0].id)


# --- #2631: agent-stake memos dedupe on the signed body ------------------


def _performance_body(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "chain_id": CHAIN,
        "stake_id": "stake-1",
        "epoch": 7,
        "score": 42,
    }
    fields.update(overrides)
    return _op_body(fields)


@pytest.mark.asyncio
async def test_performance_memo_replay_is_idempotent(rpc_db):
    engine, _queued, _monkeypatch = rpc_db
    body = _performance_body()

    first = agent_staking.record_performance(Mock(), body)
    second = agent_staking.record_performance(Mock(), body)

    assert first["success"] is True
    assert second.get("idempotent") is True
    assert len(_memo_rows(engine)) == 1


@pytest.mark.asyncio
async def test_performance_memo_distinct_body_writes_new_row(rpc_db):
    engine, _queued, _monkeypatch = rpc_db

    agent_staking.record_performance(Mock(), _performance_body())
    agent_staking.record_performance(Mock(), _performance_body(epoch=8))

    assert len(_memo_rows(engine)) == 2


@pytest.mark.asyncio
async def test_distribute_memo_replay_is_idempotent(rpc_db):
    engine, _queued, _monkeypatch = rpc_db
    fields = {"chain_id": CHAIN, "agent_wallet": AGENT, "amount": 500, "epoch": 3}
    body = _op_body(fields)

    agent_staking.record_distribute(Mock(), AGENT, body)
    again = agent_staking.record_distribute(Mock(), AGENT, body)

    assert again.get("idempotent") is True
    assert len(_memo_rows(engine)) == 1


# --- #2639: submission_id collision across bounties ----------------------


@pytest.mark.asyncio
async def test_submit_same_id_to_second_bounty_conflicts(rpc_db):
    engine, _queued, _monkeypatch = rpc_db
    _seed_account(engine)
    _deploy("b-a")
    _deploy("b-b")
    _submit("b-a", "sub-1")

    # Same submission_id against a DIFFERENT bounty must not answer
    # idempotent success while recording nothing.
    with pytest.raises(HTTPException) as exc:
        _submit("b-b", "sub-1")
    assert exc.value.status_code == 409

    # Same id + same bounty but a different submitter also conflicts.
    with pytest.raises(HTTPException) as exc2:
        _submit("b-a", "sub-1", submitter=USER2)
    assert exc2.value.status_code == 409

    # The genuine replay still answers idempotent.
    replay = _submit("b-a", "sub-1")
    assert replay.get("idempotent") is True


# --- #2640: dispute freezes payout and refund ----------------------------


@pytest.mark.asyncio
async def test_disputed_bounty_refuses_verify_and_expire(rpc_db):
    engine, queued, _monkeypatch = rpc_db
    _seed_account(engine)
    _deploy("b-d")
    _submit("b-d", "sub-d")
    queued.clear()

    disputed = _dispute("b-d", submission_id="sub-d")
    assert disputed["status"] == "disputed"

    with pytest.raises(HTTPException) as exc_verify:
        _verify("b-d", "sub-d")
    assert exc_verify.value.status_code == 409

    with pytest.raises(HTTPException) as exc_expire:
        _expire("b-d")
    assert exc_expire.value.status_code == 409

    # No money moved while frozen.
    assert not [q for q in queued if q["tx_type"] in ("BOUNTY_PAYOUT", "BOUNTY_REFUND")]
    row = _bounty_row(engine, "b-d")
    assert row.status == "disputed"
    assert row.remaining_amount == 100


@pytest.mark.asyncio
async def test_dispute_idempotent_and_expired_refused(rpc_db):
    engine, _queued, _monkeypatch = rpc_db
    _seed_account(engine)
    _deploy("b-e")
    _submit("b-e", "sub-e")

    first = _dispute("b-e")
    again = _dispute("b-e")
    assert first["status"] == "disputed"
    assert again.get("idempotent") is True

    # Drive the bounty to expired through the normal path would need the
    # freeze lifted — instead seed the expired state directly and prove
    # dispute refuses it.
    with Session(engine) as session:
        row = session.exec(
            select(BountyContract).where(BountyContract.chain_id == CHAIN, BountyContract.bounty_id == "b-e")
        ).first()
        row.status = "expired"
        row.remaining_amount = 0
        session.add(row)
        session.commit()

    with pytest.raises(HTTPException) as exc:
        _dispute("b-e")
    assert exc.value.status_code == 400


# --- #2641: idempotent create must match the request ---------------------


@pytest.mark.asyncio
async def test_deploy_bounty_idempotent_requires_same_terms(rpc_db):
    engine, _queued, _monkeypatch = rpc_db
    _seed_account(engine)
    _seed_account(engine, address=USER2)

    _deploy("b-x", amount=100)

    # Same request → idempotent.
    replay = _deploy("b-x", amount=100)
    assert replay.get("idempotent") is True

    # Different amount / creator / deadline → 409, not silent success.
    for kwargs in ({"amount": 200}, {"creator": USER2}, {"deadline": 500}):
        with pytest.raises(HTTPException) as exc:
            _deploy("b-x", **kwargs)
        assert exc.value.status_code == 409, kwargs


@pytest.mark.asyncio
async def test_create_agent_stake_idempotent_requires_same_terms(rpc_db):
    engine, _queued, _monkeypatch = rpc_db
    _seed_account(engine)

    def _create(**overrides: Any) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "chain_id": CHAIN,
            "stake_id": "as-1",
            "user_address": USER,
            "agent_wallet": AGENT,
            "amount": 1000,
            "lock_period": 30,
        }
        fields.update(overrides)
        return agent_staking.create_agent_stake(Mock(), _op_body(fields))

    first = _create()
    assert first["success"] is True

    replay = _create()
    assert replay.get("idempotent") is True

    for overrides in ({"amount": 2000}, {"lock_period": 60}, {"agent_wallet": USER2}):
        with pytest.raises(HTTPException) as exc:
            _create(**overrides)
        assert exc.value.status_code == 409, overrides

    with Session(engine) as session:
        rows = session.exec(
            select(AgentStakeRecord).where(AgentStakeRecord.chain_id == CHAIN, AgentStakeRecord.stake_id == "as-1")
        ).all()
        assert len(rows) == 1
        assert rows[0].amount == 1000
