"""Supported-chain admission on the non-market mempool intakes (C19 / H1+H2).

The C18 audit found five routes that resolved a request-supplied ``chain_id``
and let it reach the mempool unvalidated:

  * ``execute_governance_proposal`` — request ``chain_id`` went straight into
    ``mempool.add(GOVERNANCE_EXECUTE)`` (H1);
  * ``add_to_agent_stake`` / ``complete_agent_stake`` /
    ``verify_bounty`` / ``expire_bounty`` — request ``chain_id`` reached
    ``queue_protocol_transfer`` → ``mempool.add`` (H2).

Each route now calls ``_require_supported_chain`` immediately after
``get_chain_id``, so a foreign chain id is refused with HTTP 400 before any
record lookup, state transition, or mempool insertion. These tests pin both
sides: refusal fires before ``session_scope`` opens, and a whitelisted chain
still queues the protocol transaction it always did.
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
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from aitbc_chain.base_models import _to_ait_address
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, AgentStakeRecord, BountyContract, BountySubmissionRecord, GovernanceProposal
from aitbc_chain.rpc import agent_staking, bounty, staking

CHAIN = "test"  # whitelisted by the conftest _allow_test_chain_ids fixture
FOREIGN = "foreign-island"  # deliberately outside _TEST_CHAIN_IDS

OP_KEY = keys.PrivateKey(b"\x44" * 32)
OPERATOR = OP_KEY.public_key.to_checksum_address()
USER_KEY = keys.PrivateKey(b"\x55" * 32)
USER = USER_KEY.public_key.to_checksum_address()
EXEC_KEY = keys.PrivateKey(b"\x66" * 32)
EXECUTOR = EXEC_KEY.public_key.to_checksum_address()


@pytest.fixture(autouse=True)
def _operator_env(monkeypatch) -> None:
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OPERATOR)


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


def _scope_for(engine):
    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    return _session_scope


@pytest.fixture
def rpc_db(engine, monkeypatch):
    """Point every route module's session_scope at the in-memory engine."""
    scope = _scope_for(engine)
    monkeypatch.setattr(staking, "session_scope", scope)
    monkeypatch.setattr(agent_staking, "session_scope", scope)
    monkeypatch.setattr(bounty, "session_scope", scope)
    return engine


def _no_db(monkeypatch) -> None:
    """Any session_scope use means the request got past the chain gate."""

    @contextmanager
    def _boom(*args, **kwargs):
        raise AssertionError("session_scope opened for an unsupported chain_id")
        yield

    monkeypatch.setattr(staking, "session_scope", _boom)
    monkeypatch.setattr(agent_staking, "session_scope", _boom)
    monkeypatch.setattr(bounty, "session_scope", _boom)


def _signed_body(payload: dict[str, Any]) -> dict[str, Any]:
    """Operator-signed request body — the shape require_operator_signature checks."""
    digest = keccak(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    return {**payload, "signature": OP_KEY.sign_msg_hash(digest).to_hex()}


def _queued(mocker_calls) -> list[str]:
    return [c.kwargs["chain_id"] for c in mocker_calls]


# --- H1: execute_governance_proposal ----------------------------------------


async def test_execute_proposal_foreign_chain_refused(rpc_db, monkeypatch) -> None:
    _no_db(monkeypatch)
    mempool = Mock()
    monkeypatch.setattr(staking, "get_mempool", lambda: mempool)
    with pytest.raises(HTTPException) as exc:
        await staking.execute_governance_proposal(Mock(), "p1", executor_address=EXECUTOR, chain_id=FOREIGN)
    assert exc.value.status_code == 400
    assert "unsupported chain_id" in exc.value.detail
    mempool.add.assert_not_called()


async def test_execute_proposal_supported_chain_queues(rpc_db, monkeypatch) -> None:
    monkeypatch.setattr(staking.settings, "genesis_private_key", EXEC_KEY.to_hex())
    mempool = Mock()
    mempool.add.return_value = "0xgovtx"
    monkeypatch.setattr(staking, "get_mempool", lambda: mempool)
    with Session(rpc_db) as session:
        session.add(
            GovernanceProposal(
                chain_id=CHAIN,
                proposal_id="p1",
                proposer_address=OPERATOR,
                title="t",
                description="d",
                status="succeeded",
                execution_payload={"chain_parameter": {"key": "x", "value": "1"}},
                voting_starts=datetime.now(UTC),
                voting_ends=datetime.now(UTC),
            )
        )
        session.add(Account(chain_id=CHAIN, address=_to_ait_address(EXECUTOR), balance=10, nonce=0))
        session.commit()

    result = await staking.execute_governance_proposal(Mock(), "p1", executor_address=EXECUTOR, chain_id=CHAIN)

    assert result["success"] is True
    assert result["transaction_hash"] == "0xgovtx"
    assert _queued(mempool.add.mock_calls) == [CHAIN]


# --- H2: agent-staking routes -----------------------------------------------


def _stake_record(status: str = "active", locked_until: datetime | None = None) -> AgentStakeRecord:
    return AgentStakeRecord(
        chain_id=CHAIN,
        stake_id="stake-1",
        staker_address=_to_ait_address(USER),
        agent_wallet=_to_ait_address(USER),
        amount=100,
        lock_period=10,
        locked_until=locked_until or datetime.now(UTC) + timedelta(days=10),
        status=status,
    )


async def test_add_to_agent_stake_foreign_chain_refused(rpc_db, monkeypatch) -> None:
    _no_db(monkeypatch)
    queue = Mock()
    monkeypatch.setattr(agent_staking, "queue_protocol_transfer", queue)
    body = _signed_body({"chain_id": FOREIGN, "additional_amount": 5, "user_address": USER})
    with pytest.raises(HTTPException) as exc:
        await agent_staking.add_to_agent_stake(Mock(), "stake-1", body)
    assert exc.value.status_code == 400
    assert "unsupported chain_id" in exc.value.detail
    queue.assert_not_called()


async def test_add_to_agent_stake_supported_chain_queues(rpc_db, monkeypatch) -> None:
    queue = Mock(return_value="0xlocktx")
    monkeypatch.setattr(agent_staking, "queue_protocol_transfer", queue)
    with Session(rpc_db) as session:
        session.add(_stake_record())
        session.add(Account(chain_id=CHAIN, address=_to_ait_address(USER), balance=1000))
        session.commit()

    body = _signed_body({"chain_id": CHAIN, "additional_amount": 50, "user_address": USER})
    result = await agent_staking.add_to_agent_stake(Mock(), "stake-1", body)

    assert result["success"] is True
    assert result["transaction_hash"] == "0xlocktx"
    assert _queued(queue.mock_calls) == [CHAIN]
    assert queue.mock_calls[0].kwargs["tx_type"] == "STAKE_LOCK"


async def test_complete_agent_stake_foreign_chain_refused(rpc_db, monkeypatch) -> None:
    _no_db(monkeypatch)
    queue = Mock()
    monkeypatch.setattr(agent_staking, "queue_protocol_transfer", queue)
    body = _signed_body({"chain_id": FOREIGN, "user_address": USER})
    with pytest.raises(HTTPException) as exc:
        await agent_staking.complete_agent_stake(Mock(), "stake-1", body)
    assert exc.value.status_code == 400
    assert "unsupported chain_id" in exc.value.detail
    queue.assert_not_called()


async def test_complete_agent_stake_supported_chain_queues(rpc_db, monkeypatch) -> None:
    queue = Mock(return_value="0xreleasetx")
    monkeypatch.setattr(agent_staking, "queue_protocol_transfer", queue)
    lock = Mock(value=100, tx_hash="0xlock1", payload={}, block_height=1)
    monkeypatch.setattr(agent_staking, "confirmed_lock_txs", lambda *a, **k: [lock])
    with Session(rpc_db) as session:
        session.add(_stake_record(status="unbonding", locked_until=datetime.now(UTC) - timedelta(days=1)))
        session.commit()

    body = _signed_body({"chain_id": CHAIN, "user_address": USER})
    result = await agent_staking.complete_agent_stake(Mock(), "stake-1", body)

    assert result["success"] is True
    assert _queued(queue.mock_calls) == [CHAIN]
    assert queue.mock_calls[0].kwargs["tx_type"] == "STAKE_RELEASE"


# --- H2: bounty routes --------------------------------------------------------


def _bounty_record(status: str = "active", remaining: int = 100) -> BountyContract:
    return BountyContract(
        chain_id=CHAIN,
        bounty_id="b1",
        creator_address=_to_ait_address(USER),
        reward_amount=100,
        remaining_amount=remaining,
        status=status,
    )


async def test_verify_bounty_foreign_chain_refused(rpc_db, monkeypatch) -> None:
    _no_db(monkeypatch)
    queue = Mock()
    monkeypatch.setattr(bounty, "queue_protocol_transfer", queue)
    body = _signed_body({"chain_id": FOREIGN, "submission_id": "s1", "verified": True})
    with pytest.raises(HTTPException) as exc:
        await bounty.verify_bounty(Mock(), "b1", body)
    assert exc.value.status_code == 400
    assert "unsupported chain_id" in exc.value.detail
    queue.assert_not_called()


async def test_verify_bounty_supported_chain_queues(rpc_db, monkeypatch) -> None:
    queue = Mock(return_value="0xpayouttx")
    monkeypatch.setattr(bounty, "queue_protocol_transfer", queue)
    monkeypatch.setattr(bounty, "confirmed_lock_total", lambda *a, **k: 100)
    with Session(rpc_db) as session:
        session.add(_bounty_record())
        session.add(
            BountySubmissionRecord(chain_id=CHAIN, bounty_id="b1", submission_id="s1", submitter_address=_to_ait_address(USER))
        )
        session.commit()

    body = _signed_body({"chain_id": CHAIN, "submission_id": "s1", "verified": True})
    result = await bounty.verify_bounty(Mock(), "b1", body)

    assert result["success"] is True
    assert result["transaction_hash"] == "0xpayouttx"
    assert _queued(queue.mock_calls) == [CHAIN]
    assert queue.mock_calls[0].kwargs["tx_type"] == "BOUNTY_PAYOUT"


async def test_expire_bounty_foreign_chain_refused(rpc_db, monkeypatch) -> None:
    _no_db(monkeypatch)
    queue = Mock()
    monkeypatch.setattr(bounty, "queue_protocol_transfer", queue)
    body = _signed_body({"chain_id": FOREIGN, "user_address": USER})
    with pytest.raises(HTTPException) as exc:
        await bounty.expire_bounty(Mock(), "b1", body)
    assert exc.value.status_code == 400
    assert "unsupported chain_id" in exc.value.detail
    queue.assert_not_called()


async def test_expire_bounty_supported_chain_queues(rpc_db, monkeypatch) -> None:
    queue = Mock(return_value="0xrefundtx")
    monkeypatch.setattr(bounty, "queue_protocol_transfer", queue)
    monkeypatch.setattr(bounty, "confirmed_lock_total", lambda *a, **k: 100)
    with Session(rpc_db) as session:
        session.add(_bounty_record())
        session.commit()

    body = _signed_body({"chain_id": CHAIN, "user_address": USER})
    result = await bounty.expire_bounty(Mock(), "b1", body)

    assert result["success"] is True
    assert result["transaction_hash"] == "0xrefundtx"
    assert _queued(queue.mock_calls) == [CHAIN]
    assert queue.mock_calls[0].kwargs["tx_type"] == "BOUNTY_REFUND"
