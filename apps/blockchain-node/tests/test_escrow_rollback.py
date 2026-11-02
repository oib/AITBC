"""Tests for what a release whose settlement never landed leaves behind (#780 step d).

A release or refund is applied to the cached contract before it settles on-chain, so one
that does not settle must not leave this worker's cache reading RELEASED. The database
transaction rolls the row back by itself; ``EscrowManager.evict_contract`` makes the cache
follow, and the next lookup rebuilds the contract from the row.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from aitbc_chain.base_models import Escrow
from aitbc_chain.contracts.escrow import EscrowContract, EscrowManager, EscrowState, contract_id_for
from aitbc_chain.metadata import chain_metadata
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

BUYER = "0x1111111111111111111111111111111111111111"
PROVIDER = "0x2222222222222222222222222222222222222222"
JOB = "job-1"


def _make_contract(mgr: EscrowManager, contract_id: str | None = None) -> EscrowContract:
    """Insert a JOB_COMPLETED contract with verified milestones, ready to release."""
    contract_id = contract_id or contract_id_for(BUYER, PROVIDER, JOB)
    contract = EscrowContract(
        contract_id=contract_id,
        job_id=JOB,
        client_address=BUYER,
        agent_address=PROVIDER,
        amount=Decimal("1.0"),
        fee_rate=Decimal("0.025"),
        created_at=0.0,
        expires_at=1e12,
        state=EscrowState.JOB_COMPLETED,
        milestones=[{"amount": "1.0", "completed": True, "verified": True}],
        current_milestone=0,
        dispute_reason=None,
        dispute_evidence=[],
        resolution=None,
        released_amount=Decimal(0),
        refunded_amount=Decimal(0),
    )
    mgr.escrow_contracts[contract_id] = contract
    mgr.active_contracts.add(contract_id)
    return contract


@pytest.fixture
def row_db(monkeypatch):
    """One locked, unsettled escrow row, served through ``database.session_scope``."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Escrow(
                job_id=JOB,
                chain_id="test-chain",
                buyer=BUYER,
                provider=PROVIDER,
                amount=36_000_000,
                status="locked",
                created_at=datetime(2026, 11, 1, tzinfo=UTC),
            )
        )
        session.commit()

    @contextmanager
    def _scope():
        with Session(engine) as session:
            yield session

    monkeypatch.setattr("aitbc_chain.database.session_scope", _scope)
    return engine


def test_evict_of_an_unknown_contract_is_a_noop():
    mgr = EscrowManager()
    assert mgr.evict_contract("missing") is False
    assert mgr.escrow_contracts == {} and mgr.active_contracts == set() and mgr.disputed_contracts == set()


def test_evict_forgets_the_contract_everywhere():
    mgr = EscrowManager()
    contract = _make_contract(mgr)
    mgr.disputed_contracts.add(contract.contract_id)

    assert mgr.evict_contract(contract.contract_id) is True

    assert contract.contract_id not in mgr.escrow_contracts
    assert contract.contract_id not in mgr.active_contracts
    assert contract.contract_id not in mgr.disputed_contracts


def test_evict_leaves_other_contracts_alone():
    mgr = EscrowManager()
    keep = _make_contract(mgr, "c-keep")
    drop = _make_contract(mgr, "c-drop")

    mgr.evict_contract(drop.contract_id)

    assert mgr.escrow_contracts == {"c-keep": keep}
    assert mgr.active_contracts == {"c-keep"}


@pytest.mark.asyncio
async def test_unsettled_release_is_rebuilt_from_the_row_not_left_released(row_db):
    """The release applied in memory; settlement failed; the cache must not say RELEASED."""
    mgr = EscrowManager()
    contract = _make_contract(mgr)
    ok, _ = await mgr.release_full_payment(contract.contract_id)
    assert ok
    assert contract.state is EscrowState.RELEASED
    assert contract.contract_id not in mgr.active_contracts

    mgr.evict_contract(contract.contract_id)
    reloaded = await mgr.get_or_load_contract(JOB)

    assert reloaded is not None and reloaded is not contract
    assert reloaded.contract_id == contract.contract_id
    assert reloaded.state is EscrowState.FUNDED
    assert reloaded.released_amount == Decimal(0)
    assert reloaded.contract_id in mgr.active_contracts


@pytest.mark.asyncio
async def test_release_is_retryable_after_the_cache_was_evicted(row_db):
    """What the route does on a retry: rebuild, mark the job done, release again."""
    mgr = EscrowManager()
    contract = _make_contract(mgr)
    await mgr.release_full_payment(contract.contract_id)
    mgr.evict_contract(contract.contract_id)

    retry = await mgr.get_or_load_contract(JOB)
    assert retry is not None
    for milestone in retry.milestones:
        milestone["completed"] = True
        milestone["verified"] = True
    retry.state = EscrowState.JOB_COMPLETED
    ok, message = await mgr.release_full_payment(retry.contract_id)

    assert ok, message
    assert retry.state is EscrowState.RELEASED
    assert retry.released_amount == Decimal("0.975")
