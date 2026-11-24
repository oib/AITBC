"""``verify_agent_identity`` must require the verifier's signature (#2936).

The route stored ``is_verified=True`` and ``verified_by`` for a
caller-supplied ``agent_id``/``verifier_address`` behind only the RPC API
key — any key holder could mark any agent verified and attribute it to an
arbitrary address. The verifier now signs the same freshness-bound message
shape as the staking/governance writes: ``action``, ``chain_id``, the
canonical-lowercase ``verifier_address``, ``agent_id``, ``nonce`` and
``timestamp``.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from eth_keys import keys
from eth_utils import keccak
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, select

from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import AgentIdentity
from aitbc_chain.rpc import staking as rpc_staking

CHAIN = "test"
VERIFIER_KEY = keys.PrivateKey(b"\x55" * 32)
VERIFIER = VERIFIER_KEY.public_key.to_checksum_address()


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def rpc_db(engine, monkeypatch):
    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(rpc_staking, "session_scope", _session_scope)
    return engine


def _identity(session: Session, agent_id: str = "agent-1") -> AgentIdentity:
    identity = AgentIdentity(
        chain_id=CHAIN,
        agent_id=agent_id,
        agent_address="0x" + "ab" * 20,
        status="active",
    )
    session.add(identity)
    session.commit()
    return identity


def _sign_message(message: dict, key: keys.PrivateKey = VERIFIER_KEY) -> str:
    encoded = json.dumps(message, sort_keys=True, separators=(",", ":")).encode()
    return key.sign_msg_hash(keccak(encoded)).to_hex()


def _verify_body(key: keys.PrivateKey = VERIFIER_KEY, **over) -> dict:
    body = {
        "chain_id": CHAIN,
        "agent_id": "agent-1",
        "verifier_address": VERIFIER,
        "nonce": 11,
        "timestamp": time.time(),
    }
    body.update(over)
    body["signature"] = _sign_message(
        {
            "action": "agent_verify",
            "agent_id": body["agent_id"],
            "chain_id": CHAIN,
            "nonce": body["nonce"],
            "timestamp": body["timestamp"],
            "verifier_address": VERIFIER.lower(),
        },
        key,
    )
    return body


@pytest.mark.asyncio
async def test_verify_marks_identity_with_valid_signature(rpc_db) -> None:
    with Session(rpc_db) as session:
        _identity(session)
    result = rpc_staking.verify_agent_identity(Mock(), _verify_body())
    assert result["success"] is True
    assert result["is_verified"] is True
    assert result["verified_by"] == VERIFIER
    with Session(rpc_db) as session:
        row = session.exec(select(AgentIdentity).where(AgentIdentity.agent_id == "agent-1")).one()
        assert row.is_verified is True
        assert row.verified_by == VERIFIER


@pytest.mark.asyncio
async def test_verify_rejects_unsigned_body(rpc_db) -> None:
    from fastapi import HTTPException

    with Session(rpc_db) as session:
        _identity(session)
    body = {
        "chain_id": CHAIN,
        "agent_id": "agent-1",
        "verifier_address": VERIFIER,
        "nonce": 1,
        "timestamp": time.time(),
    }
    with pytest.raises(HTTPException) as exc:
        rpc_staking.verify_agent_identity(Mock(), body)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_verify_rejects_signature_from_other_key(rpc_db) -> None:
    from fastapi import HTTPException

    with Session(rpc_db) as session:
        _identity(session)
    body = _verify_body(key=keys.PrivateKey(b"\x66" * 32))
    with pytest.raises(HTTPException) as exc:
        rpc_staking.verify_agent_identity(Mock(), body)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_verify_rejects_stale_timestamp(rpc_db) -> None:
    from fastapi import HTTPException

    with Session(rpc_db) as session:
        _identity(session)
    stale = time.time() - (rpc_staking.STAKE_AUTH_MAX_AGE_SECONDS + 60)
    body = _verify_body(timestamp=stale)
    with pytest.raises(HTTPException) as exc:
        rpc_staking.verify_agent_identity(Mock(), body)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_verify_signature_binds_agent_id(rpc_db) -> None:
    """A signature for agent-1 must not verify agent-2."""
    from fastapi import HTTPException

    with Session(rpc_db) as session:
        _identity(session, "agent-1")
        _identity(session, "agent-2")
    body = _verify_body()
    body["agent_id"] = "agent-2"  # tamper after signing
    with pytest.raises(HTTPException) as exc:
        rpc_staking.verify_agent_identity(Mock(), body)
    assert exc.value.status_code == 403
