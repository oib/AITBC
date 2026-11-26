"""#3010 AUDIT-AGENT-STAKE-RELEASE-RETRY-1 pins — dead release re-drive.

``_canonical_guard`` answered idempotent ``completed`` whenever the local
row was ahead of a sealed STAKE_UNBOND, *assuming* the STAKE_RELEASE was
still in the mempool. A release rejected or dropped after the row flipped
left the principal locked forever: every retry short-circuited on the
local row and never reached the pending check or a re-queue.

Now the guard only answers idempotent while a live pending STAKE_RELEASE
(owner-scoped per #3025) backs the local ``completed``; with no pending
marker the row resyncs to the sealed ``unbonding`` truth and the normal
path re-drives the release.
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
from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from aitbc_chain.base_models import AgentStakeRecord, Transaction, _to_ait_address
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.mempool_common import MempoolEntry
from aitbc_chain.rpc import agent_staking

CHAIN = "test"

USER_KEY = keys.PrivateKey(b"\x11" * 32)
USER = USER_KEY.public_key.to_checksum_address()
OP_KEY = keys.PrivateKey(b"\x33" * 32)
OP_ADDR = OP_KEY.public_key.to_checksum_address()
SID = "stake-3010"
AMOUNT = 36_000_000


def _sign(message: dict[str, Any], key: keys.PrivateKey) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _complete_body() -> dict[str, Any]:
    fields = {"stake_id": SID, "user_address": USER, "chain_id": CHAIN}
    return {**fields, "signature": _sign(fields, OP_KEY)}


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def armed(engine, monkeypatch):
    """session_scope on the test engine, armed protocol transfers, and a
    queue_protocol_transfer spy (same harness as the #2628 pins)."""
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
        return "0x" + "ab" * 32

    monkeypatch.setattr(agent_staking, "queue_protocol_transfer", _queue)
    return queued


def _seed_stake(engine, *, status: str) -> None:
    with Session(engine) as session:
        session.add(
            AgentStakeRecord(
                chain_id=CHAIN,
                stake_id=SID,
                staker_address=_to_ait_address(USER),
                agent_wallet=_to_ait_address(USER),
                amount=AMOUNT,
                lock_period=30,
                locked_until=datetime.now(UTC) - timedelta(days=1),
                status=status,
            )
        )
        session.commit()


def _seed_tx(engine, *, tx_type: str, payload: dict[str, Any], recipient: str | None = None) -> None:
    with Session(engine) as session:
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash="0x" + keccak(json.dumps({"type": tx_type, **payload}, sort_keys=True).encode()).hex()[:64],
                block_height=1,
                sender=_to_ait_address(USER),
                recipient=_to_ait_address(recipient or agent_staking.stake_escrow_address()),
                value=AMOUNT if tx_type == "STAKE_LOCK" else 0,
                type=tx_type,
                payload=payload,
            )
        )
        session.commit()


def _seed_pending_release(engine, *, to: str) -> None:
    with Session(engine) as session:
        session.add(
            MempoolEntry(
                chain_id=CHAIN,
                tx_hash="0x" + "88" * 32,
                content=json.dumps({"type": "STAKE_RELEASE", "to": to, "payload": {"agent_stake_id": SID}}),
                fee=0,
                size_bytes=1,
                received_at=1.0,
            )
        )
        session.commit()


def _stake_row(engine) -> AgentStakeRecord:
    with Session(engine) as session:
        return session.exec(
            select(AgentStakeRecord).where(AgentStakeRecord.chain_id == CHAIN, AgentStakeRecord.stake_id == SID)
        ).first()


def _seed_dead_release_shape(engine) -> None:
    """Row completed, lock + unbond sealed, release neither sealed nor pending."""
    _seed_stake(engine, status="completed")
    _seed_tx(engine, tx_type="STAKE_LOCK", payload={"agent_stake_id": SID, "lock_days": 30})
    _seed_tx(engine, tx_type="STAKE_UNBOND", payload={"agent_stake_id": SID})


@pytest.mark.asyncio
async def test_completed_row_dead_release_redrives(engine, armed):
    """The headline repro: row ``completed``, sealed unbond, sealed lock,
    no sealed or pending release — complete must queue a fresh
    STAKE_RELEASE instead of answering idempotent forever."""
    _seed_dead_release_shape(engine)
    queued = armed
    queued.clear()

    result = agent_staking.complete_agent_stake(Mock(), SID, _complete_body())

    assert result["success"] is True
    assert result["status"] == "completed"
    releases = [q for q in queued if q["tx_type"] == "STAKE_RELEASE"]
    assert len(releases) == 1
    assert releases[0]["recipient"] == _to_ait_address(USER)
    assert _stake_row(engine).status == "completed"


@pytest.mark.asyncio
async def test_completed_row_pending_release_stays_idempotent(engine, armed):
    """A live pending STAKE_RELEASE still earns the idempotent answer —
    the re-drive must not duplicate a payout already on its way."""
    _seed_dead_release_shape(engine)
    _seed_pending_release(engine, to=_to_ait_address(USER))
    queued = armed
    queued.clear()

    result = agent_staking.complete_agent_stake(Mock(), SID, _complete_body())

    assert result["success"] is True
    assert result["idempotent"] is True
    assert result["status"] == "completed"
    assert result["source"] == "local"
    assert not [q for q in queued if q["tx_type"] == "STAKE_RELEASE"]
    assert _stake_row(engine).status == "completed"


@pytest.mark.asyncio
async def test_completed_row_sealed_release_stays_idempotent(engine, armed):
    """A sealed STAKE_RELEASE is authoritative — canonical ``completed``
    answers idempotent from chain source, row healed, no re-queue."""
    _seed_stake(engine, status="completed")
    _seed_tx(engine, tx_type="STAKE_LOCK", payload={"agent_stake_id": SID, "lock_days": 30})
    _seed_tx(
        engine,
        tx_type="STAKE_RELEASE",
        payload={"agent_stake_id": SID},
        recipient=USER,
    )
    queued = armed
    queued.clear()

    result = agent_staking.complete_agent_stake(Mock(), SID, _complete_body())

    assert result["success"] is True
    assert result["idempotent"] is True
    assert result["status"] == "completed"
    assert result["source"] == "chain"
    assert not [q for q in queued if q["tx_type"] == "STAKE_RELEASE"]


@pytest.mark.asyncio
async def test_completed_row_foreign_pending_release_does_not_block_redrive(engine, armed):
    """#3025 scoping: a pending STAKE_RELEASE paying a *different* staker
    under a colliding stake_id is not this stake's release — the dead
    release still re-drives."""
    _seed_dead_release_shape(engine)
    _seed_pending_release(engine, to="0x" + "99" * 20)
    queued = armed
    queued.clear()

    result = agent_staking.complete_agent_stake(Mock(), SID, _complete_body())

    assert result["success"] is True
    releases = [q for q in queued if q["tx_type"] == "STAKE_RELEASE"]
    assert len(releases) == 1
