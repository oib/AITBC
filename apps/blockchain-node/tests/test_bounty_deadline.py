"""#2368: ``deadline_height`` on /rpc/bounty deploy + the expire gate.

A bounty deployed with ``deadline_height`` stores it on the
``BountyContract`` row (and on the sealed ``BOUNTY_LOCK`` payload) and
``expire_bounty`` refuses with 409 until the chain head reaches it. A
bounty deployed without one keeps the legacy expire-anytime semantics.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi import HTTPException
from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool

from aitbc_chain.base_models import BountyContract, Block, Transaction, _to_ait_address
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account
from aitbc_chain.rpc import bounty

CHAIN = "test"  # whitelisted by the conftest _allow_test_chain_ids fixture

USER_KEY = keys.PrivateKey(b"\x11" * 32)
USER = USER_KEY.public_key.to_checksum_address()
OP_KEY = keys.PrivateKey(b"\x33" * 32)
OP_ADDR = OP_KEY.public_key.to_checksum_address()


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


def _seed_block(engine, height: int) -> None:
    with Session(engine) as session:
        session.add(
            Block(
                chain_id=CHAIN,
                height=height,
                hash="0x" + f"{height:064x}",
                parent_hash="0x" + f"{height - 1:064x}" if height else "0x" + "00" * 32,
                proposer="test",
                timestamp=datetime.now(UTC),
                tx_count=0,
            )
        )
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


def _deploy(bounty_id: str, *, deadline_height: int | None = None, amount: int = 100) -> dict[str, Any]:
    body = {"bounty_id": bounty_id, "user_address": USER, "reward_amount": amount, "chain_id": CHAIN}
    if deadline_height is not None:
        body["deadline_height"] = deadline_height
    return bounty.deploy_bounty(Mock(), _signed_operator_body(body))


def _bounty_row(engine, bounty_id: str) -> BountyContract:
    with Session(engine) as session:
        return session.exec(
            select(BountyContract).where(BountyContract.chain_id == CHAIN, BountyContract.bounty_id == bounty_id)
        ).one()


@pytest.mark.asyncio
async def test_deploy_stores_deadline_height(rpc_db):
    engine, queued = rpc_db
    _seed_creator(engine)
    result = _deploy("b-dl", deadline_height=42)
    assert result["success"] is True
    assert result["deadline_height"] == 42
    row = _bounty_row(engine, "b-dl")
    assert row.deadline_height == 42
    # The sealed BOUNTY_LOCK payload carries the deadline for on-chain readers.
    lock = next(q for q in queued if q["tx_type"] == "BOUNTY_LOCK")
    assert lock["payload"]["deadline_height"] == 42


@pytest.mark.asyncio
async def test_deploy_without_deadline_stays_none(rpc_db):
    engine, queued = rpc_db
    _seed_creator(engine)
    result = _deploy("b-nodl")
    assert result["deadline_height"] is None
    assert _bounty_row(engine, "b-nodl").deadline_height is None
    lock = next(q for q in queued if q["tx_type"] == "BOUNTY_LOCK")
    assert "deadline_height" not in lock["payload"]


@pytest.mark.asyncio
async def test_deploy_rejects_bad_deadline_height(rpc_db):
    engine, _ = rpc_db
    _seed_creator(engine)
    body = _signed_operator_body(
        {"bounty_id": "b-bad", "user_address": USER, "reward_amount": 100, "chain_id": CHAIN, "deadline_height": "soon"}
    )
    with pytest.raises(HTTPException) as exc:
        bounty.deploy_bounty(Mock(), body)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_expire_before_deadline_rejected(rpc_db):
    engine, queued = rpc_db
    _seed_creator(engine)
    _deploy("b-early", deadline_height=10)
    _seed_confirmed_lock(engine, "b-early", 100)
    _seed_block(engine, 5)  # head 5 < deadline 10
    body = _signed_operator_body({"bounty_id": "b-early", "user_address": USER, "chain_id": CHAIN})
    with pytest.raises(HTTPException) as exc:
        bounty.expire_bounty(Mock(), "b-early", body)
    assert exc.value.status_code == 409
    assert "deadline" in exc.value.detail
    assert "10" in exc.value.detail and "5" in exc.value.detail
    row = _bounty_row(engine, "b-early")
    assert row.status == "active"
    assert row.remaining_amount == 100


@pytest.mark.asyncio
async def test_expire_at_deadline_succeeds(rpc_db):
    engine, queued = rpc_db
    _seed_creator(engine)
    _deploy("b-at", deadline_height=10)
    _seed_confirmed_lock(engine, "b-at", 100)
    _seed_block(engine, 10)  # head == deadline
    queued.clear()
    body = _signed_operator_body({"bounty_id": "b-at", "user_address": USER, "chain_id": CHAIN})
    result = bounty.expire_bounty(Mock(), "b-at", body)
    assert result["success"] is True
    assert result["status"] == "expired"
    assert result["refunded"] == 100
    row = _bounty_row(engine, "b-at")
    assert row.status == "expired"
    assert row.remaining_amount == 0
    refund = next(q for q in queued if q["tx_type"] == "BOUNTY_REFUND")
    assert refund["amount"] == 100


@pytest.mark.asyncio
async def test_expire_after_deadline_succeeds(rpc_db):
    engine, queued = rpc_db
    _seed_creator(engine)
    _deploy("b-after", deadline_height=3)
    _seed_confirmed_lock(engine, "b-after", 100)
    _seed_block(engine, 7)  # head 7 > deadline 3
    body = _signed_operator_body({"bounty_id": "b-after", "user_address": USER, "chain_id": CHAIN})
    result = bounty.expire_bounty(Mock(), "b-after", body)
    assert result["status"] == "expired"


@pytest.mark.asyncio
async def test_expire_without_deadline_anytime(rpc_db):
    """Legacy semantics: no deadline_height → expire allowed at any head,
    including an empty chain (head 0)."""
    engine, queued = rpc_db
    _seed_creator(engine)
    _deploy("b-free")
    _seed_confirmed_lock(engine, "b-free", 100)
    # no Block rows at all: head resolves to 0
    body = _signed_operator_body({"bounty_id": "b-free", "user_address": USER, "chain_id": CHAIN})
    result = bounty.expire_bounty(Mock(), "b-free", body)
    assert result["success"] is True
    assert result["status"] == "expired"
    assert result["refunded"] == 100
