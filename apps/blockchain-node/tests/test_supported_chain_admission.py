"""Supported-chain admission on the non-market mempool intakes (C19 / H1).

The C18 audit found ``execute_governance_proposal`` resolved a request-supplied
``chain_id`` and let it reach the mempool unvalidated. The route now calls
``_require_supported_chain`` immediately after ``get_chain_id``, so a foreign
chain id is refused with HTTP 400 before any record lookup or mempool
insertion. These tests pin both sides: refusal fires before ``session_scope``
opens, and a whitelisted chain still queues the governance transaction.

The four H2 protocol-transfer routes the audit also flagged
(``add_to_agent_stake`` / ``complete_agent_stake`` / ``verify_bounty`` /
``expire_bounty``) have since been retired outright — they raise HTTP 410
before any chain-id handling; see ``rpc/retired.py``.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from eth_keys import keys
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from aitbc_chain.base_models import _to_ait_address
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, GovernanceProposal
from aitbc_chain.rpc import staking

CHAIN = "test"  # whitelisted by the conftest _allow_test_chain_ids fixture
FOREIGN = "foreign-island"  # deliberately outside _TEST_CHAIN_IDS

OP_KEY = keys.PrivateKey(b"\x44" * 32)
OPERATOR = OP_KEY.public_key.to_checksum_address()
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
    """Point the route module's session_scope at the in-memory engine."""
    monkeypatch.setattr(staking, "session_scope", _scope_for(engine))
    return engine


def _no_db(monkeypatch) -> None:
    """Any session_scope use means the request got past the chain gate."""

    @contextmanager
    def _boom(*args, **kwargs):
        raise AssertionError("session_scope opened for an unsupported chain_id")
        yield

    monkeypatch.setattr(staking, "session_scope", _boom)


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
