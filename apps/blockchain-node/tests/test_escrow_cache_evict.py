"""Pin for ESCROW-CACHE-STUCK-JOB-COMPLETED-1 (#833).

``_release_settle_locked`` marks the cached contract ``JOB_COMPLETED``
before its guards run; every exit after that mark must evict the cached
contract or a later refund on the same worker reads a completed job that
never settled. The refund settle path has the same class of bug around
``refund_contract`` -> submit. Green on the fix; the four un-evicted exits
fail on pre-fix main.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from aitbc_chain.contracts.escrow import EscrowState
from aitbc_chain.rpc import escrow_routes as er


def _record(**overrides):
    fields = {
        "protected": True,
        "energy_settlement_asset": "AITBC",
        "energy_settlement_unit_scale": None,
        "energy_fee_basis_points": None,
        "energy_provider_credit_units": None,
        "energy_net_floor_units": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _contract():
    contract = MagicMock()
    contract.state = EscrowState.FUNDED
    contract.protected = False
    contract.released_amount = Decimal("1.0")
    contract.refunded_amount = Decimal("1.0")
    contract.client_address = "0x4444444444444444444444444444444444444444"
    contract.agent_address = "0x3333333333333333333333333333333333333333"
    contract.milestones = [{"amount": "1.0", "completed": False, "verified": False}]
    contract.fee_rate = Decimal("0")
    return contract


def _mgr(contract):
    mgr = MagicMock()
    mgr.escrow_contracts = {"c1": contract} if contract else {}
    mgr.release_payment = AsyncMock(return_value=(True, "released"))
    mgr.refund_contract = AsyncMock(return_value=(True, "refunded"))
    mgr.evict_contract = MagicMock(side_effect=lambda cid: mgr.escrow_contracts.pop(cid, None))
    return mgr


def _plan(record):
    return er._ReleasePlan(escrow_record=record, contract_id="c1")


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_case", ["asset_mismatch", "scale_mismatch", "no_row_protected", "release_fails"])
async def test_release_early_exit_evicts_the_marked_contract(exit_case):
    """Every guard that raises after the JOB_COMPLETED mark must evict — the
    row is the truth, the cache rebuilds from it."""
    contract = _contract()
    mgr = _mgr(contract)
    txn = MagicMock()

    if exit_case == "asset_mismatch":
        plan = _plan(_record(energy_settlement_asset="USDT"))
    elif exit_case == "scale_mismatch":
        plan = _plan(_record(energy_settlement_unit_scale=1))
    elif exit_case == "no_row_protected":
        contract.protected = True
        plan = _plan(None)
    else:
        mgr.release_payment = AsyncMock(return_value=(False, "cannot release"))
        plan = _plan(None)

    with pytest.raises(HTTPException):
        await er._release_settle_locked(mgr, "job-1", {}, None, plan, txn)

    assert "c1" not in mgr.escrow_contracts, f"{exit_case}: stale JOB_COMPLETED contract left cached"
    mgr.evict_contract.assert_called_with("c1")


@pytest.mark.asyncio
async def test_refund_works_after_a_failed_release_mark():
    """done_when: a release driven into an early exit leaves no completed mark;
    a refund through the same manager then settles normally."""
    contract = _contract()
    mgr = _mgr(contract)
    mgr.release_payment = AsyncMock(return_value=(False, "cannot release"))

    with pytest.raises(HTTPException):
        await er._release_settle_locked(mgr, "job-1", {}, None, _plan(None), MagicMock())
    assert "c1" not in mgr.escrow_contracts

    # The rebuilt contract (evicted -> reloaded from the row) comes back FUNDED;
    # the refund settles where a stale JOB_COMPLETED read would have refused.
    rebuilt = _contract()
    mgr.escrow_contracts["c1"] = rebuilt
    plan = er._RefundPlan(contract_id="c1", reason="job failed", locked_units=None)
    txn = MagicMock()
    txn.write = AsyncMock()
    with (
        patch.object(er, "_submit_refund_tx", new_callable=AsyncMock, return_value="0xrefundhash"),
        patch.object(er, "_to_canonical", side_effect=lambda a: a),
    ):
        result = await er._refund_settle_locked(mgr, "job-1", plan, txn)
    assert result["success"] is True
    assert result["refund_tx_hash"] == "0xrefundhash"


@pytest.mark.asyncio
async def test_refund_settle_evicts_when_the_submit_raises():
    """refund_contract marks REFUNDED in memory; a submit exception must evict
    or the cache shows a refund the chain never saw."""
    mgr = _mgr(_contract())
    plan = er._RefundPlan(contract_id="c1", reason="job failed", locked_units=None)
    with (
        patch.object(er, "_submit_refund_tx", new_callable=AsyncMock, side_effect=RuntimeError("rpc down")),
        patch.object(er, "_to_canonical", side_effect=lambda a: a),
        pytest.raises(RuntimeError),
    ):
        await er._refund_settle_locked(mgr, "job-1", plan, MagicMock())
    assert "c1" not in mgr.escrow_contracts
    mgr.evict_contract.assert_called_with("c1")


@pytest.mark.asyncio
async def test_refund_settle_evicts_when_refund_contract_fails():
    mgr = _mgr(_contract())
    mgr.refund_contract = AsyncMock(return_value=(False, "not refundable"))
    plan = er._RefundPlan(contract_id="c1", reason="job failed", locked_units=None)
    with pytest.raises(HTTPException):
        await er._refund_settle_locked(mgr, "job-1", plan, MagicMock())
    mgr.evict_contract.assert_called_with("c1")
