"""Tests for rolling back an escrow release whose settlement never landed."""

import asyncio
from decimal import Decimal

import pytest

from aitbc_chain.contracts.escrow import EscrowContract, EscrowManager, EscrowState


def _make_contract(mgr: EscrowManager, contract_id: str = "c-1") -> EscrowContract:
    """Insert a JOB_COMPLETED contract with verified milestones, ready to release."""
    contract = EscrowContract(
        contract_id=contract_id,
        job_id="job-1",
        client_address="0x1111111111111111111111111111111111111111",
        agent_address="0x2222222222222222222222222222222222222222",
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


def test_release_lock_is_stable_per_contract():
    mgr = EscrowManager()
    assert mgr.release_lock("c-1") is mgr.release_lock("c-1")
    assert mgr.release_lock("c-1") is not mgr.release_lock("c-2")


def test_snapshot_returns_none_for_unknown_contract():
    mgr = EscrowManager()
    assert mgr.snapshot_release_state("missing") is None
    assert mgr.restore_after_failed_settlement("missing", None) is False


@pytest.mark.asyncio
async def test_rollback_restores_state_after_failed_settlement():
    """A release that does not settle must leave the contract exactly as it was."""
    mgr = EscrowManager()
    contract = _make_contract(mgr)

    snapshot = mgr.snapshot_release_state("c-1")
    ok, _ = await mgr.release_full_payment("c-1")
    assert ok
    # Released in memory: state advanced, funds counted, no longer active.
    assert contract.state is EscrowState.RELEASED
    assert contract.released_amount > Decimal(0)
    assert "c-1" not in mgr.active_contracts

    assert mgr.restore_after_failed_settlement("c-1", snapshot) is True

    assert contract.state is EscrowState.JOB_COMPLETED
    assert contract.released_amount == Decimal(0)
    assert "c-1" in mgr.active_contracts


@pytest.mark.asyncio
async def test_release_is_retryable_after_rollback():
    """Rollback must leave the contract in a state a later release can act on."""
    mgr = EscrowManager()
    contract = _make_contract(mgr)

    snapshot = mgr.snapshot_release_state("c-1")
    await mgr.release_full_payment("c-1")
    mgr.restore_after_failed_settlement("c-1", snapshot)

    ok, message = await mgr.release_full_payment("c-1")
    assert ok, message
    assert contract.state is EscrowState.RELEASED
    assert contract.released_amount == Decimal("0.975")


@pytest.mark.asyncio
async def test_concurrent_releases_are_serialised_by_the_lock():
    """The per-contract lock must exclude a second releaser while one holds it."""
    mgr = EscrowManager()
    _make_contract(mgr)
    lock = mgr.release_lock("c-1")

    async with lock:
        second = asyncio.create_task(asyncio.wait_for(mgr.release_lock("c-1").acquire(), timeout=0.05))
        with pytest.raises(asyncio.TimeoutError):
            await second
    # Released again once the holder exits.
    await asyncio.wait_for(mgr.release_lock("c-1").acquire(), timeout=0.5)
