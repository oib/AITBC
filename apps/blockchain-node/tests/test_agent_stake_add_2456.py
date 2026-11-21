"""#2456 AGENT-STAKING-ADD-ECHO-1 pins — add response fields + top-up marker.

``add_to_agent_stake`` used to echo ``amount`` as the stake's NEW TOTAL,
so a caller summing top-ups over-counted by the whole principal. The
response now carries the delta (``added_amount``/``amount``) and the
total (``new_total``) separately, and the queued STAKE_LOCK payload gets
an ``additional_amount`` marker so ``agent-staking status`` can tell a
top-up from the original lock.
"""

from __future__ import annotations

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

from aitbc_chain.base_models import AgentStakeRecord, _to_ait_address
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account
from aitbc_chain.rpc import agent_staking

CHAIN = "test"

USER_KEY = keys.PrivateKey(b"\x11" * 32)
USER = USER_KEY.public_key.to_checksum_address()
OP_KEY = keys.PrivateKey(b"\x33" * 32)
OP_ADDR = OP_KEY.public_key.to_checksum_address()
SID = "stake-add-2456"


def _sign(message: dict[str, Any], key: keys.PrivateKey) -> str:
    import json

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
    queue_protocol_transfer spy — the add path's three externalities."""
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OP_ADDR)

    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(agent_staking, "session_scope", _session_scope)
    monkeypatch.setattr(agent_staking, "protocol_transfers_active", lambda *a, **k: True)
    queued: list[dict[str, Any]] = []

    def _queue(**kwargs):
        queued.append(kwargs)
        return "0x" + "ab" * 32

    monkeypatch.setattr(agent_staking, "queue_protocol_transfer", _queue)
    return queued


def _seed_active_stake(engine, *, amount: int = 36_000_000, balance: int = 100_000_000) -> None:
    user = _to_ait_address(USER)
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=user, balance=balance))
        session.add(
            AgentStakeRecord(
                chain_id=CHAIN,
                stake_id=SID,
                staker_address=user,
                agent_wallet=user,
                amount=amount,
                lock_period=30,
                locked_until=datetime.now(UTC) + timedelta(days=30),
                status="active",
            )
        )
        session.commit()


@pytest.mark.asyncio
async def test_add_returns_delta_and_total(engine, armed):
    """added_amount/amount carry the 0.5 AIT delta; new_total the 1.5 AIT sum."""
    _seed_active_stake(engine)
    body = _signed_body({"stake_id": SID, "user_address": USER, "additional_amount": 18_000_000, "chain_id": CHAIN})
    result = agent_staking.add_to_agent_stake(Mock(), SID, body)
    assert result["success"] is True
    assert result["added_amount"] == 18_000_000
    assert result["amount"] == 18_000_000  # delta, not the 54M total
    assert result["new_total"] == 54_000_000


@pytest.mark.asyncio
async def test_add_payload_marks_topup(engine, armed):
    """The queued STAKE_LOCK payload carries additional_amount so status
    can distinguish the top-up from the original lock."""
    _seed_active_stake(engine)
    body = _signed_body({"stake_id": SID, "user_address": USER, "additional_amount": 18_000_000, "chain_id": CHAIN})
    agent_staking.add_to_agent_stake(Mock(), SID, body)
    assert len(armed) == 1
    call = armed[0]
    assert call["tx_type"] == "STAKE_LOCK"
    assert call["payload"]["additional_amount"] == 18_000_000
    assert call["payload"]["agent_stake_id"] == SID


@pytest.mark.asyncio
async def test_add_unknown_stake_still_404s(engine, armed):
    _seed_active_stake(engine)
    body = _signed_body({"stake_id": "nope", "user_address": USER, "additional_amount": 1, "chain_id": CHAIN})
    with pytest.raises(HTTPException) as exc:
        agent_staking.add_to_agent_stake(Mock(), "nope", body)
    assert exc.value.status_code == 404
