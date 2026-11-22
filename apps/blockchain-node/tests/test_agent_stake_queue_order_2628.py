"""#2628 AGENT-STAKE-COMPLETE-BEFORE-QUEUE-1 pins — queue-before-commit.

``complete_agent_stake`` used to commit ``status = "completed"`` before
``queue_protocol_transfer`` ran, so a refused queue left a stake whose
retry answered idempotent success while the release never queued — the
principal stayed in escrow. The same commit-before-queue shape existed in
``unbond_agent_stake`` (row → ``unbonding`` before the STAKE_UNBOND
marker), ``create_agent_stake`` (row → ``active`` before the STAKE_LOCK)
and ``add_to_agent_stake`` (amount grown before the top-up lock).

Now every flow queues inside the session before the row commits, and a
retry that finds the transfer already pending (or sealed) reconciles the
row instead of emitting a duplicate.
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
from aitbc_chain.models import Account
from aitbc_chain.rpc import agent_staking

CHAIN = "test"

USER_KEY = keys.PrivateKey(b"\x11" * 32)
USER = USER_KEY.public_key.to_checksum_address()
OP_KEY = keys.PrivateKey(b"\x33" * 32)
OP_ADDR = OP_KEY.public_key.to_checksum_address()
SID = "stake-2628"
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
    """session_scope on the test engine, armed protocol transfers, and a
    queue_protocol_transfer spy."""
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OP_ADDR)

    # expire_on_commit=False mirrors prod_parity_sessionmaker — the RPC
    # handlers read record attributes after the session closes.
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


def _seed_account(engine, balance: int = 100_000_000) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=_to_ait_address(USER), balance=balance))
        session.commit()


def _seed_stake(engine, *, status: str = "active", amount: int = AMOUNT, matured: bool = True) -> None:
    with Session(engine) as session:
        session.add(
            AgentStakeRecord(
                chain_id=CHAIN,
                stake_id=SID,
                staker_address=_to_ait_address(USER),
                agent_wallet=_to_ait_address(USER),
                amount=amount,
                lock_period=30,
                locked_until=datetime.now(UTC) + (timedelta(days=-1) if matured else timedelta(days=30)),
                status=status,
            )
        )
        session.commit()


def _seed_lock_tx(
    engine,
    *,
    value: int,
    payload: dict[str, Any],
    height: int = 1,
    tx_type: str = "STAKE_LOCK",
    tx_hash: str | None = None,
) -> None:
    with Session(engine) as session:
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash=tx_hash or "0x" + keccak(json.dumps(payload, sort_keys=True).encode()).hex()[:64],
                block_height=height,
                sender=_to_ait_address(USER),
                recipient=agent_staking.stake_escrow_address(),
                value=value,
                type=tx_type,
                payload=payload,
            )
        )
        session.commit()


def _seed_pending(engine, tx_type: str, payload: dict[str, Any]) -> None:
    with Session(engine) as session:
        session.add(
            MempoolEntry(
                chain_id=CHAIN,
                tx_hash="0x" + keccak(json.dumps(payload, sort_keys=True).encode()).hex()[:64],
                content=json.dumps({"type": tx_type, "payload": payload}),
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


def _refuse_next_queue(monkeypatch, queued: list[dict[str, Any]]) -> None:
    calls = {"n": 0}

    def _flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("mempool pool full: fee-0 transfer cannot evict")
        queued.append(kwargs)
        return "0x" + "cd" * 32

    monkeypatch.setattr(agent_staking, "queue_protocol_transfer", _flaky)


def _complete_body() -> dict[str, Any]:
    return _signed_body({"stake_id": SID, "user_address": USER, "chain_id": CHAIN})


def _unbond_body() -> dict[str, Any]:
    return _signed_body({"stake_id": SID, "user_address": USER, "chain_id": CHAIN})


def _add_body(additional: int) -> dict[str, Any]:
    return _signed_body({"stake_id": SID, "user_address": USER, "additional_amount": additional, "chain_id": CHAIN})


def _create_body() -> dict[str, Any]:
    return _signed_body(
        {
            "stake_id": SID,
            "user_address": USER,
            "agent_wallet": USER,
            "amount": AMOUNT,
            "lock_period": 30,
            "chain_id": CHAIN,
        }
    )


# --- complete_agent_stake -------------------------------------------------


@pytest.mark.asyncio
async def test_complete_queue_refusal_leaves_unbonding_and_retry_releases(engine, armed, monkeypatch):
    """The auditor repro: a refused release queue must not strand the
    stake as 'completed' — the row stays unbonding and the retry queues."""
    _seed_stake(engine, status="unbonding")
    _seed_lock_tx(engine, value=AMOUNT, payload={"agent_stake_id": SID, "lock_days": 30})
    queued = armed
    queued.clear()
    _refuse_next_queue(monkeypatch, queued)

    with pytest.raises(ValueError, match="pool full"):
        agent_staking.complete_agent_stake(Mock(), SID, _complete_body())
    assert _stake_row(engine).status == "unbonding"

    result = agent_staking.complete_agent_stake(Mock(), SID, _complete_body())
    assert result["success"] is True
    assert result["status"] == "completed"
    assert any(q["tx_type"] == "STAKE_RELEASE" for q in queued)
    assert _stake_row(engine).status == "completed"


@pytest.mark.asyncio
async def test_complete_pending_release_answers_success_without_duplicate(engine, armed):
    """A release already in the mempool (previous attempt died after
    queueing) must not queue a second one — the row stays unbonding so a
    dropped entry still retries."""
    _seed_stake(engine, status="unbonding")
    _seed_lock_tx(engine, value=AMOUNT, payload={"agent_stake_id": SID, "lock_days": 30})
    _seed_pending(engine, "STAKE_RELEASE", {"agent_stake_id": SID})
    queued = armed
    queued.clear()

    result = agent_staking.complete_agent_stake(Mock(), SID, _complete_body())

    assert result["success"] is True
    assert result["release_pending"] is True
    assert result["status"] == "unbonding"
    assert _stake_row(engine).status == "unbonding"
    assert not [q for q in queued if q["tx_type"] == "STAKE_RELEASE"]


@pytest.mark.asyncio
async def test_complete_sealed_release_heals_row_without_duplicate(engine, armed):
    """#2645: the pre-#2628 ordering could seal the STAKE_RELEASE while the
    row stayed `unbonding` — `complete` must answer idempotent from sealed
    history, heal the stranded row, and never queue a second release."""
    _seed_stake(engine, status="unbonding")
    _seed_lock_tx(engine, value=AMOUNT, payload={"agent_stake_id": SID, "lock_days": 30})
    _seed_lock_tx(
        engine,
        value=AMOUNT,
        payload={"agent_stake_id": SID},
        tx_type="STAKE_RELEASE",
        tx_hash="0x" + "ef" * 32,
    )
    queued = armed
    queued.clear()

    result = agent_staking.complete_agent_stake(Mock(), SID, _complete_body())

    assert result["success"] is True
    assert result["idempotent"] is True
    assert result["status"] == "completed"
    assert result["source"] == "chain"
    assert _stake_row(engine).status == "completed"
    assert not [q for q in queued if q["tx_type"] == "STAKE_RELEASE"]


@pytest.mark.asyncio
async def test_complete_sealed_release_heals_even_before_lock_expiry(engine, armed):
    """The money already moved — a sealed release heals the row regardless
    of the local lock-expiry clock."""
    _seed_stake(engine, status="unbonding", matured=False)
    _seed_lock_tx(engine, value=AMOUNT, payload={"agent_stake_id": SID, "lock_days": 30})
    _seed_lock_tx(
        engine,
        value=AMOUNT,
        payload={"agent_stake_id": SID},
        tx_type="STAKE_RELEASE",
        tx_hash="0x" + "12" * 32,
    )
    queued = armed
    queued.clear()

    result = agent_staking.complete_agent_stake(Mock(), SID, _complete_body())

    assert result["success"] is True
    assert result["status"] == "completed"
    assert _stake_row(engine).status == "completed"
    assert not [q for q in queued if q["tx_type"] == "STAKE_RELEASE"]


@pytest.mark.asyncio
async def test_unbond_sealed_marker_heals_stale_active_row(engine, armed):
    """#2645 sibling: a sealed STAKE_UNBOND with a local row still `active`
    heals forward to `unbonding` on the idempotent answer — never backwards."""
    _seed_stake(engine, status="active")
    _seed_lock_tx(
        engine,
        value=AMOUNT,
        payload={"agent_stake_id": SID},
        tx_type="STAKE_UNBOND",
        tx_hash="0x" + "34" * 32,
    )
    queued = armed
    queued.clear()

    result = agent_staking.unbond_agent_stake(Mock(), SID, _unbond_body())

    assert result["success"] is True
    assert result["idempotent"] is True
    assert result["status"] == "unbonding"
    assert _stake_row(engine).status == "unbonding"
    assert not [q for q in queued if q["tx_type"] == "STAKE_UNBOND"]


# --- unbond_agent_stake ---------------------------------------------------


@pytest.mark.asyncio
async def test_unbond_queue_refusal_leaves_active_and_retry_marks(engine, armed, monkeypatch):
    _seed_stake(engine, status="active")
    queued = armed
    queued.clear()
    _refuse_next_queue(monkeypatch, queued)

    with pytest.raises(ValueError, match="pool full"):
        agent_staking.unbond_agent_stake(Mock(), SID, _unbond_body())
    assert _stake_row(engine).status == "active"

    result = agent_staking.unbond_agent_stake(Mock(), SID, _unbond_body())
    assert result["success"] is True
    assert result["status"] == "unbonding"
    assert any(q["tx_type"] == "STAKE_UNBOND" for q in queued)
    assert _stake_row(engine).status == "unbonding"


@pytest.mark.asyncio
async def test_unbond_pending_marker_flips_without_requeue(engine, armed):
    """Marker already pending + row still active (commit died) → flip the
    row, do not emit a second STAKE_UNBOND."""
    _seed_stake(engine, status="active")
    _seed_pending(engine, "STAKE_UNBOND", {"agent_stake_id": SID})
    queued = armed
    queued.clear()

    result = agent_staking.unbond_agent_stake(Mock(), SID, _unbond_body())

    assert result["success"] is True
    assert result["already_queued"] is True
    assert result["transaction_hash"] is None
    assert _stake_row(engine).status == "unbonding"
    assert not [q for q in queued if q["tx_type"] == "STAKE_UNBOND"]


# --- create_agent_stake ---------------------------------------------------


@pytest.mark.asyncio
async def test_create_queue_refusal_leaves_no_row_and_retry_creates(engine, armed, monkeypatch):
    _seed_account(engine)
    queued = armed
    queued.clear()
    _refuse_next_queue(monkeypatch, queued)

    with pytest.raises(ValueError, match="pool full"):
        agent_staking.create_agent_stake(Mock(), _create_body())
    assert _stake_row(engine) is None

    result = agent_staking.create_agent_stake(Mock(), _create_body())
    assert result["success"] is True
    assert result["status"] == "active"
    assert any(q["tx_type"] == "STAKE_LOCK" for q in queued)
    assert _stake_row(engine).status == "active"


@pytest.mark.asyncio
async def test_create_pending_lock_rebuilds_row_without_requeue(engine, armed):
    """Lock queued but the row commit died → the retry rebuilds the row
    idempotently instead of queueing a second STAKE_LOCK."""
    _seed_account(engine)
    _seed_pending(engine, "STAKE_LOCK", {"agent_stake_id": SID, "lock_days": 30})
    queued = armed
    queued.clear()

    result = agent_staking.create_agent_stake(Mock(), _create_body())

    assert result["success"] is True
    assert result["idempotent"] is True
    assert result["lock_pending"] is True
    assert _stake_row(engine).status == "active"
    assert not [q for q in queued if q["tx_type"] == "STAKE_LOCK"]


@pytest.mark.asyncio
async def test_create_sealed_lock_rebuilds_row(engine, armed):
    _seed_account(engine)
    _seed_lock_tx(engine, value=AMOUNT, payload={"agent_stake_id": SID, "lock_days": 30})
    queued = armed
    queued.clear()

    result = agent_staking.create_agent_stake(Mock(), _create_body())

    assert result["success"] is True
    assert result["idempotent"] is True
    assert result["lock_sealed"] is True
    assert _stake_row(engine).status == "active"
    assert not [q for q in queued if q["tx_type"] == "STAKE_LOCK"]


# --- add_to_agent_stake ---------------------------------------------------


def _seed_funded_stake(engine, amount: int = AMOUNT) -> None:
    """Active stake plus its confirmed base STAKE_LOCK covering amount."""
    _seed_stake(engine, status="active", amount=amount)
    _seed_lock_tx(engine, value=amount, payload={"agent_stake_id": SID, "lock_days": 30})


@pytest.mark.asyncio
async def test_add_queue_refusal_leaves_amount_and_retry_adds(engine, armed, monkeypatch):
    _seed_funded_stake(engine)
    _seed_account(engine)
    queued = armed
    queued.clear()
    _refuse_next_queue(monkeypatch, queued)

    with pytest.raises(ValueError, match="pool full"):
        agent_staking.add_to_agent_stake(Mock(), SID, _add_body(5))
    assert _stake_row(engine).amount == AMOUNT

    result = agent_staking.add_to_agent_stake(Mock(), SID, _add_body(5))
    assert result["success"] is True
    assert result["new_total"] == AMOUNT + 5
    assert _stake_row(engine).amount == AMOUNT + 5


@pytest.mark.asyncio
async def test_add_pending_topup_applies_delta_without_requeue(engine, armed):
    """Top-up lock pending + record not yet grown (commit died) → apply
    the delta, do not queue a second lock."""
    _seed_funded_stake(engine)
    _seed_account(engine)
    _seed_pending(engine, "STAKE_LOCK", {"agent_stake_id": SID, "lock_days": 30, "additional_amount": 5})
    queued = armed
    queued.clear()

    result = agent_staking.add_to_agent_stake(Mock(), SID, _add_body(5))

    assert result["success"] is True
    assert result["already_queued"] is False
    assert _stake_row(engine).amount == AMOUNT + 5
    assert not [q for q in queued if q["tx_type"] == "STAKE_LOCK"]


@pytest.mark.asyncio
async def test_add_pending_topup_already_applied_is_idempotent(engine, armed):
    """Same pending lock retried after the amount commit landed → the
    record already counts it; answer success without growing again."""
    _seed_stake(engine, status="active", amount=AMOUNT + 5)
    _seed_account(engine)
    _seed_lock_tx(engine, value=AMOUNT, payload={"agent_stake_id": SID, "lock_days": 30})
    _seed_pending(engine, "STAKE_LOCK", {"agent_stake_id": SID, "lock_days": 30, "additional_amount": 5})
    queued = armed
    queued.clear()

    result = agent_staking.add_to_agent_stake(Mock(), SID, _add_body(5))

    assert result["success"] is True
    assert result["already_queued"] is True
    assert _stake_row(engine).amount == AMOUNT + 5
    assert not [q for q in queued if q["tx_type"] == "STAKE_LOCK"]


@pytest.mark.asyncio
async def test_add_sealed_topup_unapplied_heals_amount(engine, armed):
    """Top-up lock sealed but the row commit died → the record still owes
    the delta; apply it without queueing."""
    _seed_stake(engine, status="active", amount=AMOUNT)
    _seed_account(engine)
    _seed_lock_tx(engine, value=AMOUNT, payload={"agent_stake_id": SID, "lock_days": 30})
    _seed_lock_tx(engine, value=5, payload={"agent_stake_id": SID, "lock_days": 30, "additional_amount": 5}, height=2)
    queued = armed
    queued.clear()

    result = agent_staking.add_to_agent_stake(Mock(), SID, _add_body(5))

    assert result["success"] is True
    assert _stake_row(engine).amount == AMOUNT + 5
    assert not [q for q in queued if q["tx_type"] == "STAKE_LOCK"]
