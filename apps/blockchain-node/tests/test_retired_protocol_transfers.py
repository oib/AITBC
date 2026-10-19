"""BNT-2: retired protocol-transfer RPC surfaces refuse up front.

Every ``queue_protocol_transfer`` emission is unsigned and unsealable at
block version 9 (BNT-1 audit), so the staking / agent-staking / AUTO_STAKE /
bounty / HTLC entry points retire: HTTP 410 (or RetiredProtocolTransfer for
the HTLC contract), no domain row, nothing queued. The stub bodies are gone;
each surface raises unconditionally at the top.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlmodel import Session, create_engine, func, select
from sqlmodel.pool import StaticPool

from aitbc_chain.base_models import BountyContract, BountySubmissionRecord, HTLCSwapState
from aitbc_chain.contracts.htlc_contract import HTLCContract
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import AgentStakeRecord, Stake, Transaction
from aitbc_chain.rpc import agent_staking, bounty, escrow_routes, staking
from aitbc_chain.rpc.retired import RetiredProtocolTransfer

CHAIN = "test"  # whitelisted by the conftest _allow_test_chain_ids fixture


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def rpc_db(engine, monkeypatch):
    scope = _scope_for(engine)
    for module in (staking, agent_staking, escrow_routes):
        monkeypatch.setattr(module, "session_scope", scope)
    return engine


@contextmanager
def _session_scope_no_db(*args, **kwargs):
    raise AssertionError("retired handler touched session_scope")
    yield


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


async def test_stake_refuses_410_and_writes_nothing(rpc_db):
    before = _counts(rpc_db)
    with pytest.raises(HTTPException) as exc:
        await staking.stake_tokens(request=None, stake_data={"address": "0xabc", "amount": 1})
    assert exc.value.status_code == 410
    assert "retired" in exc.value.detail.lower()
    assert _counts(rpc_db) == before


async def test_unstake_refuses_410(rpc_db):
    with pytest.raises(HTTPException) as exc:
        await staking.unstake_tokens(request=None, unstake_data={"address": "0xabc", "stake_id": "1"})
    assert exc.value.status_code == 410


async def test_agent_staking_all_four_refuse_410(rpc_db, monkeypatch):
    monkeypatch.setattr(agent_staking, "session_scope", _session_scope_no_db)
    for call, args in [
        (agent_staking.create_agent_stake, (Mock(), {"signature": "0x"})),
        (agent_staking.add_to_agent_stake, (Mock(), "s-1", {"signature": "0x"})),
        (agent_staking.unbond_agent_stake, (Mock(), "s-1", {"signature": "0x"})),
        (agent_staking.complete_agent_stake, (Mock(), "s-1", {"signature": "0x"})),
    ]:
        with pytest.raises(HTTPException) as exc:
            await call(*args)
        assert exc.value.status_code == 410


async def test_bounty_all_five_refuse_410(rpc_db):
    before = _counts(rpc_db)
    for call, args in [
        (bounty.deploy_bounty, (Mock(), {"signature": "0x"})),
        (bounty.submit_bounty, (Mock(), "b-1", {"signature": "0x"})),
        (bounty.verify_bounty, (Mock(), "b-1", {"signature": "0x"})),
        (bounty.dispute_bounty, (Mock(), "b-1", {"signature": "0x"})),
        (bounty.expire_bounty, (Mock(), "b-1", {"signature": "0x"})),
    ]:
        with pytest.raises(HTTPException) as exc:
            await call(*args)
        assert exc.value.status_code == 410
    assert _counts(rpc_db) == before


def test_htlc_mutators_raise_retired(rpc_db):
    htlc = HTLCContract(chain_id=CHAIN)
    with Session(rpc_db) as session:
        with pytest.raises(RetiredProtocolTransfer):
            htlc.initiate_swap(session, "0xa", "0xb", 1, "0x" + "ab" * 32, 100)
        with pytest.raises(RetiredProtocolTransfer):
            htlc.complete_swap(session, "sw-1", "secret")
        with pytest.raises(RetiredProtocolTransfer):
            htlc.refund_swap(session, "sw-1")


async def test_auto_stake_skips_without_failing_release(caplog):
    """AUTO_STAKE sits in the escrow release path: it must log-and-skip,
    never raise — a retired failure here would break escrow releases."""
    result = await escrow_routes._auto_stake("0xabc", 100, CHAIN, job_id="j-1")
    assert result is None
    # second call must not raise either (retired warning logs once)
    assert await escrow_routes._auto_stake("0xabc", 100, CHAIN) is None


async def test_get_staking_info_still_serves(rpc_db):
    """Read endpoints stay live — only the mutating surfaces retired."""
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
    result = await staking.get_staking_info(Mock(), "0xabc", CHAIN)
    assert "410" not in str(result)  # any normal shape — the point is it ran
