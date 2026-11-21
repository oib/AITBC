"""Pin for #2402: release submit ambiguity must not 502 an in-flight release.

``_submit_payment_tx`` returns None both when the submit genuinely failed
and when the node's response was lost after the tx was admitted to the
mempool. The settle path now re-checks sealed+mempool via
``_existing_settlement_tx_hash`` before declaring the release unsettled —
the same dedup the retry path already relies on. Green on the fix; the
first test fails on pre-fix main (unsettled result, provider unpaid
bookkeeping despite a live release tx).
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aitbc_chain.contracts.escrow import EscrowState
from aitbc_chain.rpc import escrow_routes as er


def _contract():
    contract = MagicMock()
    contract.state = EscrowState.FUNDED
    contract.protected = False
    contract.released_amount = Decimal("1.0")
    contract.refunded_amount = Decimal("0")
    contract.client_address = "0x4444444444444444444444444444444444444444"
    contract.agent_address = "0x3333333333333333333333333333333333333333"
    contract.milestones = [{"amount": "1.0", "completed": False, "verified": False}]
    contract.fee_rate = Decimal("0")
    return contract


def _mgr(contract):
    mgr = MagicMock()
    mgr.escrow_contracts = {"c1": contract}
    mgr.release_payment = AsyncMock(return_value=(True, "released"))
    mgr.evict_contract = MagicMock(side_effect=lambda cid: mgr.escrow_contracts.pop(cid, None))
    return mgr


def _txn():
    txn = MagicMock()
    txn.write = AsyncMock()
    return txn


async def _settle_with_submit_result(submit_result, recheck_result):
    contract = _contract()
    mgr = _mgr(contract)
    plan = er._ReleasePlan(escrow_record=None, contract_id="c1")
    with (
        patch.object(er, "_submit_payment_tx", new_callable=AsyncMock, return_value=submit_result),
        patch.object(er, "_existing_settlement_tx_hash", new_callable=AsyncMock, return_value=recheck_result) as recheck,
        patch.object(er, "_submit_receipt_claim_tx", new_callable=AsyncMock, return_value="0xclaim"),
    ):
        result = await er._release_settle_locked(mgr, "job-1", {}, None, plan, _txn())
    return result, mgr, recheck


@pytest.mark.asyncio
async def test_lost_submit_response_finds_in_flight_release():
    """Submit returns None but the tx is in mempool: adopt it, do not 502."""
    result, mgr, recheck = await _settle_with_submit_result(None, "0xpending-release")

    assert result["success"] is True
    assert result["tx_hash"] == "0xpending-release"
    assert result["settlement_status"] == "settled"
    recheck.assert_awaited_once_with("job-1", "ESCROW_RELEASE")
    mgr.evict_contract.assert_not_called()


@pytest.mark.asyncio
async def test_genuine_submit_failure_still_reports_unsettled():
    """Nothing in flight anywhere: the honest unsettled answer is preserved."""
    result, mgr, _recheck = await _settle_with_submit_result(None, None)

    assert result["success"] is False
    assert result["tx_hash"] is None
    assert result["settlement_status"] == "unsettled"
    mgr.evict_contract.assert_called_with("c1")


@pytest.mark.asyncio
async def test_successful_submit_skips_the_recheck():
    """The common path pays no extra lookup."""
    result, _mgr_obj, recheck = await _settle_with_submit_result("0xfresh", "0xshould-not-be-used")

    assert result["success"] is True
    assert result["tx_hash"] == "0xfresh"
    recheck.assert_not_awaited()
