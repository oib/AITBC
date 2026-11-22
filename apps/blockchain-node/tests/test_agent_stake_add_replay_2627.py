"""#2627 AGENT-STAKE-ADD-REPLAY-1 pins — top-up replay guard.

``add_to_agent_stake`` had no replay guard: a byte-identical re-sent
operator-signed body passed signature verification again and did
``record.amount += additional`` each time, while the mempool deduped the
identical lock to one transaction — N replays inflated the recorded
principal N-fold and ``complete_agent_stake`` then 409'd forever.

Two layers now guard it: an optional signed ``request_id``/``nonce`` is a
one-shot key recorded as an ``agent_stake_memo`` row (reuse with a
different amount is a 409), and the #2628 lock-derived reconcile makes an
identical body converge on the already-queued/sealed lock instead of
re-adding — which is also the only chain-consistent answer, since
identical bodies produce identical transactions the mempool itself
dedupes.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi import HTTPException
from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from aitbc_chain.base_models import AgentStakeMemo, AgentStakeRecord, Transaction, _to_ait_address
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.mempool_common import MempoolEntry
from aitbc_chain.models import Account
from aitbc_chain.rpc import agent_staking

CHAIN = "test"

USER_KEY = keys.PrivateKey(b"\x11" * 32)
USER = USER_KEY.public_key.to_checksum_address()
OP_KEY = keys.PrivateKey(b"\x33" * 32)
OP_ADDR = OP_KEY.public_key.to_checksum_address()
SID = "stake-2627"
AMOUNT = 36_000_000


def _sign(message: dict[str, Any], key: keys.PrivateKey) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _signed_body(fields: dict[str, Any]) -> dict[str, Any]:
    return {**fields, "signature": _sign(fields, OP_KEY)}


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def armed(engine, monkeypatch):
    """session_scope on the test engine, armed transfers, and a queue spy
    that also persists a MempoolEntry so pending-detection sees it."""
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OP_ADDR)
    factory = sessionmaker(class_=Session, bind=engine, expire_on_commit=False)

    @contextmanager
    def _session_scope(*args, **kwargs):
        with factory() as session:
            yield session

    monkeypatch.setattr(agent_staking, "session_scope", _session_scope)
    monkeypatch.setattr(agent_staking, "protocol_transfers_active", lambda *a, **k: True)
    queued: list[dict[str, Any]] = []

    def _queue(**kwargs):
        queued.append(kwargs)
        content = {"type": kwargs["tx_type"], "payload": kwargs.get("payload") or {}}
        with factory() as session:
            session.add(
                MempoolEntry(
                    chain_id=CHAIN,
                    tx_hash="0x" + keccak(json.dumps(content, sort_keys=True).encode()).hex()[:64],
                    content=json.dumps(content),
                    fee=0,
                    size_bytes=1,
                    received_at=1.0,
                )
            )
            session.commit()
        return "0x" + "ab" * 32

    monkeypatch.setattr(agent_staking, "queue_protocol_transfer", _queue)
    return queued


def _seed(engine, *, amount: int = AMOUNT, balance: int = 100_000_000) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=_to_ait_address(USER), balance=balance))
        session.add(
            AgentStakeRecord(
                chain_id=CHAIN,
                stake_id=SID,
                staker_address=_to_ait_address(USER),
                agent_wallet=_to_ait_address(USER),
                amount=amount,
                lock_period=30,
                locked_until=datetime.now(UTC) - timedelta(days=1),
                status="active",
            )
        )
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash="0x" + "11" * 32,
                block_height=1,
                sender=_to_ait_address(USER),
                recipient=agent_staking.stake_escrow_address(),
                value=amount,
                type="STAKE_LOCK",
                payload={"agent_stake_id": SID, "lock_days": 30},
            )
        )
        session.commit()


def _stake_row(engine) -> AgentStakeRecord:
    with Session(engine) as session:
        return session.exec(
            select(AgentStakeRecord).where(AgentStakeRecord.chain_id == CHAIN, AgentStakeRecord.stake_id == SID)
        ).first()


def _add_body(**extra: Any) -> dict[str, Any]:
    return _signed_body({"stake_id": SID, "user_address": USER, "additional_amount": 7_200_000, "chain_id": CHAIN, **extra})


@pytest.mark.asyncio
async def test_identical_body_replay_does_not_inflate(engine, armed):
    """The auditor repro: the same signed body sent three times must grow
    the record once — the queued lock is pending, so replays reconcile."""
    _seed(engine)
    queued = armed
    body = _add_body()

    first = agent_staking.add_to_agent_stake(Mock(), SID, body)
    second = agent_staking.add_to_agent_stake(Mock(), SID, body)
    third = agent_staking.add_to_agent_stake(Mock(), SID, body)

    assert first["new_total"] == AMOUNT + 7_200_000
    assert second["success"] is True and third["success"] is True
    assert _stake_row(engine).amount == AMOUNT + 7_200_000
    assert len([q for q in queued if q["tx_type"] == "STAKE_LOCK"]) == 1


@pytest.mark.asyncio
async def test_request_id_replay_is_idempotent(engine, armed):
    """A signed request_id makes the replay explicit: second use answers
    idempotent, writes no second lock, grows nothing."""
    _seed(engine)
    queued = armed
    body = _add_body(request_id="topup-1")

    first = agent_staking.add_to_agent_stake(Mock(), SID, body)
    replay = agent_staking.add_to_agent_stake(Mock(), SID, body)

    assert first["success"] is True and first["request_id"] if "request_id" in first else True
    assert replay["idempotent"] is True
    assert replay["request_id"] == "topup-1"
    assert _stake_row(engine).amount == AMOUNT + 7_200_000
    assert len([q for q in queued if q["tx_type"] == "STAKE_LOCK"]) == 1
    with Session(engine) as session:
        memos = session.exec(select(AgentStakeMemo).where(AgentStakeMemo.kind == "topup_request")).all()
    assert len(memos) == 1
    assert memos[0].external_id == f"{SID}:topup-1"


@pytest.mark.asyncio
async def test_request_id_reuse_with_different_amount_is_409(engine, armed):
    _seed(engine)
    agent_staking.add_to_agent_stake(Mock(), SID, _add_body(request_id="topup-1"))
    other = _signed_body(
        {"stake_id": SID, "user_address": USER, "additional_amount": 9_000_000, "chain_id": CHAIN, "request_id": "topup-1"}
    )
    with pytest.raises(HTTPException) as exc:
        agent_staking.add_to_agent_stake(Mock(), SID, other)
    assert exc.value.status_code == 409
    assert _stake_row(engine).amount == AMOUNT + 7_200_000


@pytest.mark.asyncio
async def test_distinct_request_ids_same_amount_both_apply(engine, armed):
    """Deliberate repeats stay possible: different request_ids are
    different top-ups — two locks queue, the record grows twice."""
    _seed(engine)
    queued = armed

    agent_staking.add_to_agent_stake(Mock(), SID, _add_body(request_id="topup-1"))
    second = agent_staking.add_to_agent_stake(Mock(), SID, _add_body(request_id="topup-2"))

    assert second["success"] is True
    assert second["new_total"] == AMOUNT + 2 * 7_200_000
    assert _stake_row(engine).amount == AMOUNT + 2 * 7_200_000
    assert len([q for q in queued if q["tx_type"] == "STAKE_LOCK"]) == 2


@pytest.mark.asyncio
async def test_legacy_body_does_not_consolidate_request_id_lock(engine, armed):
    """A no-request_id body must not be swallowed by a request_id-bearing
    lock of the same amount — they are different transactions on-chain."""
    _seed(engine)
    queued = armed

    agent_staking.add_to_agent_stake(Mock(), SID, _add_body(request_id="topup-1"))
    legacy = agent_staking.add_to_agent_stake(Mock(), SID, _add_body())

    assert legacy["success"] is True
    assert _stake_row(engine).amount == AMOUNT + 2 * 7_200_000
    assert len([q for q in queued if q["tx_type"] == "STAKE_LOCK"]) == 2
