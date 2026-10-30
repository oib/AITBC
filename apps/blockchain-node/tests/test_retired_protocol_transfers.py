"""BNT-2 + BNT-1-v17: protocol-transfer RPC surfaces refuse while dead.

Two refusal layers live here:

- **Unconditional (HTLC + AUTO_STAKE):** those emissions carry no
  ``payload.auth`` at all and can never seal at any version — they stay
  retired forever (``RetiredProtocolTransfer`` / log-and-skip).
- **Gated (staking / agent-staking / bounty):** their emissions DO carry
  auth and seal from ``state_transition_v17_height`` on, so the surfaces
  refuse with HTTP 410 only *while unarmed* — pin unset, or the next
  height still below it. These tests drive each restored handler past its
  signature checks with a validly signed request and assert the gate's
  "not active" 410 — plus that nothing was written or queued.
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
from sqlmodel import Session, create_engine, func, select
from sqlmodel.pool import StaticPool

from aitbc_chain.base_models import BountyContract, BountySubmissionRecord, HTLCSwapState
from aitbc_chain.config import settings
from aitbc_chain.contracts.htlc_contract import HTLCContract
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import AgentStakeRecord, Stake, Transaction
from aitbc_chain.rpc import agent_staking, bounty, escrow_routes, staking
from aitbc_chain.rpc.retired import RetiredProtocolTransfer

CHAIN = "test"  # whitelisted by the conftest _allow_test_chain_ids fixture

USER_KEY = keys.PrivateKey(b"\x11" * 32)
USER = USER_KEY.public_key.to_checksum_address()
OP_KEY = keys.PrivateKey(b"\x33" * 32)
OP_ADDR = OP_KEY.public_key.to_checksum_address()


def _sign(message: dict[str, Any], key: keys.PrivateKey) -> str:
    """Sign a request payload exactly as verify_request_signature rebuilds it."""
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _signed_stake_body(
    action: str,
    *,
    sign_fields: dict[str, Any] | None = None,
    body_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A fully-signed consensus-staking request body — reaches the gate.

    The RPC reconstructs the signed message from a fixed field set
    (``address`` in its lowercase spelling, ``chain_id``, ``action``,
    ``nonce``, ``timestamp``, plus ``amount`` for stake / ``stake_id`` for
    unstake); anything else in the request body rides unsigned.
    """
    message = {
        "address": USER.lower(),
        "chain_id": CHAIN,
        "action": action,
        "nonce": 0,
        "timestamp": time.time(),
    }
    message.update(sign_fields or {})
    return {
        **message,
        "address": USER,  # the request carries the canonical spelling
        **(body_fields or {}),
        "signature": _sign(message, USER_KEY),
    }


def _signed_operator_body(fields: dict[str, Any]) -> dict[str, Any]:
    """An operator-signed agent-economics body — passes require_operator_signature."""
    return {**fields, "signature": _sign(fields, OP_KEY)}


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def rpc_db(engine, monkeypatch):
    """Route the modules' session_scope at the test engine and keep the
    chain definitively unarmed: no blocks, no v17 pin."""
    scope = _scope_for(engine)
    for module in (staking, agent_staking, bounty, escrow_routes):
        monkeypatch.setattr(module, "session_scope", scope)
    monkeypatch.setattr(settings, "state_transition_v17_height", None)
    return engine


def _scope_for(engine):
    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    return _session_scope


def _counts(engine) -> dict[str, int]:
    with Session(engine) as session:
        return {
            "stake": session.exec(select(func.count()).select_from(Stake)).one(),
            "agent_stake": session.exec(select(func.count()).select_from(AgentStakeRecord)).one(),
            "bounty": session.exec(select(func.count()).select_from(BountyContract)).one(),
            "bounty_sub": session.exec(select(func.count()).select_from(BountySubmissionRecord)).one(),
            "htlc": session.exec(select(func.count()).select_from(HTLCSwapState)).one(),
            "tx": session.exec(select(func.count()).select_from(Transaction)).one(),
        }


@pytest.mark.asyncio
async def test_stake_refuses_410_while_unarmed_and_writes_nothing(rpc_db):
    """A correctly signed stake request gets past auth — and then hits the
    unarmed gate: 410, no Stake row, nothing queued."""
    before = _counts(rpc_db)
    body = _signed_stake_body("stake", sign_fields={"amount": 1}, body_fields={"amount": 1, "lock_days": 30})
    with pytest.raises(HTTPException) as exc:
        staking.stake_tokens(request=None, stake_data=body)
    assert exc.value.status_code == 410
    assert "not active" in exc.value.detail.lower()
    assert "v17" in exc.value.detail
    assert _counts(rpc_db) == before


@pytest.mark.asyncio
async def test_stake_refuses_410_when_pin_set_but_unreached(rpc_db, monkeypatch):
    """The pin being *set* is not enough — until the next block would apply
    v17 the surface stays dormant (head=0 → next=1 < pin=2)."""
    monkeypatch.setattr(settings, "state_transition_v17_height", 2)
    body = _signed_stake_body("stake", sign_fields={"amount": 1}, body_fields={"amount": 1, "lock_days": 30})
    with pytest.raises(HTTPException) as exc:
        staking.stake_tokens(request=None, stake_data=body)
    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_unstake_refuses_410_while_unarmed(rpc_db):
    body = _signed_stake_body("unstake", sign_fields={"stake_id": "1"}, body_fields={"stake_id": "1"})
    with pytest.raises(HTTPException) as exc:
        staking.unstake_tokens(request=None, unstake_data=body)
    assert exc.value.status_code == 410
    assert "not active" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_agent_staking_all_four_refuse_410_while_unarmed(rpc_db, monkeypatch):
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OP_ADDR)
    before = _counts(rpc_db)
    for call, args in [
        (
            agent_staking.create_agent_stake,
            (
                Mock(),
                _signed_operator_body(
                    {
                        "stake_id": "s-1",
                        "user_address": USER,
                        "agent_wallet": USER,
                        "amount": 10,
                        "lock_period": 30,
                        "chain_id": CHAIN,
                    }
                ),
            ),
        ),
        (
            agent_staking.add_to_agent_stake,
            (Mock(), "s-1", _signed_operator_body({"stake_id": "s-1", "user_address": USER, "additional_amount": 5})),
        ),
        (
            agent_staking.unbond_agent_stake,
            (Mock(), "s-1", _signed_operator_body({"stake_id": "s-1", "user_address": USER})),
        ),
        (
            agent_staking.complete_agent_stake,
            (Mock(), "s-1", _signed_operator_body({"stake_id": "s-1", "user_address": USER})),
        ),
    ]:
        with pytest.raises(HTTPException) as exc:
            await call(*args)
        assert exc.value.status_code == 410, f"{call.__name__}: {exc.value.detail}"
        assert "not active" in exc.value.detail.lower()
    assert _counts(rpc_db) == before


@pytest.mark.asyncio
async def test_bounty_all_five_refuse_410_while_unarmed(rpc_db, monkeypatch):
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OP_ADDR)
    before = _counts(rpc_db)
    for call, args in [
        (
            bounty.deploy_bounty,
            (Mock(), _signed_operator_body({"bounty_id": "b-1", "user_address": USER, "reward_amount": 10})),
        ),
        (
            bounty.submit_bounty,
            (Mock(), "b-1", _signed_operator_body({"bounty_id": "b-1", "submission_id": "sub-1", "user_address": USER})),
        ),
        (
            bounty.verify_bounty,
            (Mock(), "b-1", _signed_operator_body({"bounty_id": "b-1", "submission_id": "sub-1", "verified": True})),
        ),
        (
            bounty.dispute_bounty,
            (Mock(), "b-1", _signed_operator_body({"bounty_id": "b-1", "submission_id": "sub-1"})),
        ),
        (
            bounty.expire_bounty,
            (Mock(), "b-1", _signed_operator_body({"bounty_id": "b-1", "user_address": USER})),
        ),
    ]:
        with pytest.raises(HTTPException) as exc:
            await call(*args)
        assert exc.value.status_code == 410, f"{call.__name__}: {exc.value.detail}"
        assert "not active" in exc.value.detail.lower()
    assert _counts(rpc_db) == before


@pytest.mark.asyncio
async def test_agent_stake_signed_id_must_match_path(rpc_db, monkeypatch):
    """The signed body's stake_id binds the emitted tx — a body naming a
    different stake than the path refuses before any state is touched."""
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OP_ADDR)
    for call, args in [
        (agent_staking.unbond_agent_stake, (Mock(), "s-1", _signed_operator_body({"stake_id": "s-2", "user_address": USER}))),
        (
            agent_staking.complete_agent_stake,
            (Mock(), "s-1", _signed_operator_body({"stake_id": "s-2", "user_address": USER})),
        ),
        (
            agent_staking.add_to_agent_stake,
            (Mock(), "s-1", _signed_operator_body({"stake_id": "s-2", "user_address": USER, "additional_amount": 5})),
        ),
    ]:
        with pytest.raises(HTTPException) as exc:
            await call(*args)
        assert exc.value.status_code == 400
        assert "stake_id" in exc.value.detail


@pytest.mark.asyncio
async def test_bounty_signed_id_must_match_path(rpc_db, monkeypatch):
    """Same binding for bounty: a signed bounty_id other than the path's
    refuses — otherwise the record mutates while the emitted refund/payout
    can never seal (payload.bounty_id != signed)."""
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OP_ADDR)
    for call, args in [
        (
            bounty.submit_bounty,
            (Mock(), "b-1", _signed_operator_body({"bounty_id": "b-2", "submission_id": "sub-1", "user_address": USER})),
        ),
        (
            bounty.verify_bounty,
            (Mock(), "b-1", _signed_operator_body({"bounty_id": "b-2", "submission_id": "sub-1", "verified": True})),
        ),
        (
            bounty.dispute_bounty,
            (Mock(), "b-1", _signed_operator_body({"bounty_id": "b-2", "submission_id": "sub-1"})),
        ),
        (
            bounty.expire_bounty,
            (Mock(), "b-1", _signed_operator_body({"bounty_id": "b-2", "user_address": USER})),
        ),
    ]:
        with pytest.raises(HTTPException) as exc:
            await call(*args)
        assert exc.value.status_code == 400, f"{call.__name__}: {exc.value.detail}"
        assert "bounty_id" in exc.value.detail


@pytest.mark.asyncio
async def test_bounty_verify_payout_requires_signed_bounty_id(rpc_db, monkeypatch):
    """A verify that pays out must name the bounty inside the signed body.

    The apply-time binding for BOUNTY_PAYOUT keys on submission_id — a
    signature without bounty_id could be re-pathed onto any
    ``/bounty/{id}/verify`` and drain a lock it never authorized. verified=
    True without a signed bounty_id now refuses 400; verified=False moves
    no funds, so tolerate-missing stays and the request still reaches the
    unarmed gate (410)."""
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OP_ADDR)
    with pytest.raises(HTTPException) as exc:
        bounty.verify_bounty(Mock(), "b-1", _signed_operator_body({"submission_id": "sub-1", "verified": True}))
    assert exc.value.status_code == 400
    assert "bounty_id" in exc.value.detail

    with pytest.raises(HTTPException) as exc:
        bounty.verify_bounty(Mock(), "b-1", _signed_operator_body({"submission_id": "sub-1", "verified": False}))
    assert exc.value.status_code == 410

    with pytest.raises(HTTPException) as exc:
        bounty.verify_bounty(
            Mock(), "b-1", _signed_operator_body({"bounty_id": "b-1", "submission_id": "sub-1", "verified": True})
        )
    assert exc.value.status_code == 410


def test_htlc_mutators_raise_retired(rpc_db):
    """HTLC stays dead at every version — it carries no auth at all."""
    htlc = HTLCContract(chain_id=CHAIN)
    with Session(rpc_db) as session:
        with pytest.raises(RetiredProtocolTransfer):
            htlc.initiate_swap(session, "0xa", "0xb", 1, "0x" + "ab" * 32, 100)
        with pytest.raises(RetiredProtocolTransfer):
            htlc.complete_swap(session, "sw-1", "secret")
        with pytest.raises(RetiredProtocolTransfer):
            htlc.refund_swap(session, "sw-1")


@pytest.mark.asyncio
async def test_auto_stake_skips_without_failing_release(caplog):
    """AUTO_STAKE sits in the escrow release path: it must log-and-skip,
    never raise — a retired failure here would break escrow releases."""
    result = escrow_routes._auto_stake("0xabc", 100, CHAIN, job_id="j-1")
    assert result is None
    # second call must not raise either (retired warning logs once)
    assert escrow_routes._auto_stake("0xabc", 100, CHAIN) is None


@pytest.mark.asyncio
async def test_get_staking_info_still_serves(rpc_db):
    """Read endpoints stay live — only the mutating surfaces gated."""
    with Session(rpc_db) as session:
        session.add(
            Stake(
                chain_id=CHAIN,
                address="0xabc",
                amount=5,
                locked_until=datetime.now(UTC) + timedelta(days=1),
                status="active",
            )
        )
        session.commit()
    result = staking.get_staking_info(Mock(), "0xabc", CHAIN)
    assert "410" not in str(result)  # any normal shape — the point is it ran
