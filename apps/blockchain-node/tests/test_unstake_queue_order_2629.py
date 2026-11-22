"""#2629: unstake must not mark the stake withdrawn before the release queues.

``unstake_tokens`` used to commit ``status = "withdrawn"`` before
``queue_protocol_transfer`` ran, so a refused queue (full pool, pending
release conflict, oversized entry) stranded the stake: every retry hit
"Stake is not active: withdrawn" while the principal sat in the escrow.

Now the STAKE_RELEASE queues inside the session before the row flips — a
refusal leaves the stake active and the retry re-runs cleanly. A stake
already marked ``withdrawn`` whose release is neither sealed nor pending
(the pre-fix stranded state) is retryable; one with a release in flight
stays refused so it cannot double-pay.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi import HTTPException
from sqlmodel import Session, create_engine
from sqlmodel.pool import StaticPool

from aitbc_chain.base_models import Stake, Transaction, _to_ait_address
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.mempool_common import MempoolEntry
from aitbc_chain.models import Account
from aitbc_chain.rpc import staking

CHAIN = "test"  # whitelisted by the conftest _allow_test_chain_ids fixture

USER_KEY = keys.PrivateKey(b"\x11" * 32)
USER = USER_KEY.public_key.to_checksum_address()


def _sign(message: dict[str, Any], key: keys.PrivateKey) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _unstake_body(stake_id: Any, *, nonce: int = 0) -> dict[str, Any]:
    """A fully-signed unstake request — mirrors _signed_stake_body."""
    message = {
        "address": USER.lower(),
        "chain_id": CHAIN,
        "action": "unstake",
        "nonce": nonce,
        "timestamp": time.time(),
        "stake_id": stake_id,
    }
    return {
        **message,
        "address": USER,
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
    """Route staking.session_scope at the test engine, arm v17, and stub
    the mempool queue so no real transaction is emitted."""

    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(staking, "session_scope", _session_scope)
    monkeypatch.setattr(settings, "state_transition_v17_height", 1)
    queued: list[dict[str, Any]] = []

    def _fake_queue(**kwargs):
        queued.append(kwargs)
        return "0x" + "ab" * 32

    monkeypatch.setattr(staking, "queue_protocol_transfer", _fake_queue)
    return engine, queued, monkeypatch


def _seed_account(engine, balance: int = 10**9, nonce: int = 0) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=_to_ait_address(USER), balance=balance, nonce=nonce))
        session.commit()


def _seed_matured_stake(engine, *, status: str = "active", amount: int = 1000) -> int:
    """An active stake whose lock period has passed, plus its confirmed
    STAKE_LOCK — returns the stake id."""
    with Session(engine) as session:
        stake = Stake(
            chain_id=CHAIN,
            address=USER,
            amount=amount,
            locked_until=datetime.now(UTC) - timedelta(days=1),
            status=status,
        )
        session.add(stake)
        session.commit()
        session.refresh(stake)
        stake_id = stake.id
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash="0x" + keccak(f"lock-{stake_id}".encode()).hex()[:64],
                block_height=1,
                sender=_to_ait_address(USER),
                recipient=staking.stake_escrow_address(),
                value=amount,
                type="STAKE_LOCK",
                payload={"stake_id": str(stake_id)},
            )
        )
        session.commit()
        return stake_id


def _stake_row(engine, stake_id: int) -> Stake:
    with Session(engine) as session:
        return session.get(Stake, stake_id)


def _refuse_next_queue(monkeypatch, queued: list[dict[str, Any]]) -> None:
    calls = {"n": 0}

    def _flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("mempool pool full: fee-0 transfer cannot evict")
        queued.append(kwargs)
        return "0x" + "cd" * 32

    monkeypatch.setattr(staking, "queue_protocol_transfer", _flaky)


@pytest.mark.asyncio
async def test_unstake_queue_refusal_leaves_stake_active_and_retry_releases(rpc_db):
    """The auditor repro: a refused release queue must not strand the
    stake — the row stays active and the retry queues the release."""
    engine, queued, monkeypatch = rpc_db
    _seed_account(engine)
    stake_id = _seed_matured_stake(engine)
    queued.clear()
    _refuse_next_queue(monkeypatch, queued)

    with pytest.raises(ValueError, match="pool full"):
        staking.unstake_tokens(request=Mock(), unstake_data=_unstake_body(stake_id))

    assert _stake_row(engine, stake_id).status == "active"
    assert not [q for q in queued if q["tx_type"] == "STAKE_RELEASE"]

    result = staking.unstake_tokens(request=Mock(), unstake_data=_unstake_body(stake_id))
    assert result["success"] is True
    assert result["status"] == "withdrawn"
    release = next(q for q in queued if q["tx_type"] == "STAKE_RELEASE")
    assert release["amount"] == 1000
    assert release["recipient"] == _to_ait_address(USER)
    assert _stake_row(engine, stake_id).status == "withdrawn"


@pytest.mark.asyncio
async def test_unstake_withdrawn_without_release_is_retryable(rpc_db):
    """The pre-fix stranded state: status=withdrawn but no STAKE_RELEASE
    sealed or pending — the retry is allowed and queues the release."""
    engine, queued, _monkeypatch = rpc_db
    _seed_account(engine)
    stake_id = _seed_matured_stake(engine, status="withdrawn")
    queued.clear()

    result = staking.unstake_tokens(request=Mock(), unstake_data=_unstake_body(stake_id))

    assert result["success"] is True
    assert result["status"] == "withdrawn"
    assert any(q["tx_type"] == "STAKE_RELEASE" for q in queued)


@pytest.mark.asyncio
async def test_unstake_withdrawn_with_pending_release_stays_refused(rpc_db):
    """A withdrawn stake whose release is already in the mempool must not
    queue a second one — the retry still answers 400."""
    engine, queued, _monkeypatch = rpc_db
    _seed_account(engine)
    stake_id = _seed_matured_stake(engine, status="withdrawn")
    with Session(engine) as session:
        session.add(
            MempoolEntry(
                chain_id=CHAIN,
                tx_hash="0x" + "ee" * 32,
                content=json.dumps({"type": "STAKE_RELEASE", "payload": {"stake_id": str(stake_id)}}),
                fee=0,
                size_bytes=1,
                received_at=1.0,
            )
        )
        session.commit()
    queued.clear()

    with pytest.raises(HTTPException) as exc:
        staking.unstake_tokens(request=Mock(), unstake_data=_unstake_body(stake_id))
    assert exc.value.status_code == 400
    assert "withdrawn" in exc.value.detail
    assert not [q for q in queued if q["tx_type"] == "STAKE_RELEASE"]


@pytest.mark.asyncio
async def test_unstake_withdrawn_with_sealed_release_stays_refused(rpc_db):
    """Same guard on the sealed side: a STAKE_RELEASE already in a block
    means the stake paid out — no second release."""
    engine, queued, _monkeypatch = rpc_db
    _seed_account(engine)
    stake_id = _seed_matured_stake(engine, status="withdrawn")
    with Session(engine) as session:
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash="0x" + "ff" * 32,
                block_height=2,
                sender=staking.stake_escrow_address(),
                recipient=_to_ait_address(USER),
                value=1000,
                type="STAKE_RELEASE",
                payload={"stake_id": str(stake_id)},
            )
        )
        session.commit()
    queued.clear()

    with pytest.raises(HTTPException) as exc:
        staking.unstake_tokens(request=Mock(), unstake_data=_unstake_body(stake_id))
    assert exc.value.status_code == 400
    assert not [q for q in queued if q["tx_type"] == "STAKE_RELEASE"]
