"""Targeted branch-coverage tests for EscrowManager validation and state transitions.

These tests cover branches not exercised by the existing escrow test suite:
- invalid client/agent addresses
- negative amounts
- duplicate job IDs
- invalid milestone configurations
- wrong-state transitions
- missing/already-completed milestones
- evidence path validation
- partial billing
- protected energy-floor branches
- dispute creation/resolution
- contract expiration
- add_milestone edge cases
- agent failure / job failure / reassignment
- process_refund / process_partial_payment
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest

from aitbc_chain.contracts.escrow import (
    DisputeReason,
    EscrowManager,
    EscrowState,
)


BUYER = "0xe8b0db006F34bf5b5d2B22553C017431E8e86e4F"
PROVIDER = "0xD4d85501E6cD447972Db19370307F1E3B1510016"
OTHER = "0xADC923a0928B8415E666206D3703a870C1d578CE"


@pytest.fixture
def mgr() -> EscrowManager:
    return EscrowManager()


async def _make_funded(mgr: EscrowManager, job_id: str = "job1", amount: Decimal = Decimal("1.0")) -> str:
    ok, _, cid = await mgr.create_contract(job_id, BUYER, PROVIDER, amount)
    assert ok, "setup create failed"
    ok, _ = await mgr.fund_contract(cid, "0xhash")
    assert ok, "setup fund failed"
    return cid


async def _make_completed(mgr: EscrowManager, job_id: str = "job1", amount: Decimal = Decimal("1.0")) -> str:
    cid = await _make_funded(mgr, job_id, amount)
    ok, _ = await mgr.complete_milestone(cid, "milestone_1")
    assert ok
    mgr.escrow_contracts[cid].state = EscrowState.JOB_COMPLETED
    return cid


# --- create_contract validation ---------------------------------------------


class TestCreateContractValidation:
    async def test_invalid_client_address(self, mgr: EscrowManager):
        ok, msg, cid = await mgr.create_contract("j", "0xnothex", PROVIDER, Decimal("1"))
        assert not ok and cid is None
        assert "Invalid" in msg

    async def test_invalid_agent_address(self, mgr: EscrowManager):
        ok, msg, cid = await mgr.create_contract("j", BUYER, "short", Decimal("1"))
        assert not ok and cid is None

    async def test_negative_amount(self, mgr: EscrowManager):
        ok, msg, cid = await mgr.create_contract("j", BUYER, PROVIDER, Decimal("-1"))
        assert not ok and cid is None

    async def test_empty_job_id(self, mgr: EscrowManager):
        ok, msg, cid = await mgr.create_contract("", BUYER, PROVIDER, Decimal("1"))
        assert not ok and cid is None

    async def test_duplicate_job_id(self, mgr: EscrowManager):
        ok, _, _ = await mgr.create_contract("dup", BUYER, PROVIDER, Decimal("1"))
        assert ok
        ok2, msg2, _ = await mgr.create_contract("dup", BUYER, PROVIDER, Decimal("1"))
        assert not ok2
        assert "Invalid" in msg2

    async def test_protected_with_energy_fee_bps(self, mgr: EscrowManager):
        ok, _, cid = await mgr.create_contract(
            "prot",
            BUYER,
            PROVIDER,
            Decimal("1"),
            protected=True,
            energy_fee_basis_points=500,
        )
        assert ok
        c = mgr.escrow_contracts[cid]
        assert c.fee_rate == Decimal("500") / Decimal("10000")
        assert c.protected


# --- milestone validation ----------------------------------------------------


class TestMilestoneValidation:
    async def test_missing_milestone_field(self, mgr: EscrowManager):
        ms = [{"milestone_id": "m1", "description": "d"}]  # no amount
        ok, msg, _ = await mgr.create_contract("j", BUYER, PROVIDER, Decimal("1"), milestones=ms)
        assert not ok and "milestones" in msg.lower()

    async def test_milestone_below_minimum(self, mgr: EscrowManager):
        ms = [{"milestone_id": "m1", "description": "d", "amount": Decimal("0.001")}]
        ok, msg, _ = await mgr.create_contract("j", BUYER, PROVIDER, Decimal("0.001"), milestones=ms)
        assert not ok

    async def test_milestone_total_mismatch(self, mgr: EscrowManager):
        ms = [{"milestone_id": "m1", "description": "d", "amount": Decimal("0.5")}]
        ok, msg, _ = await mgr.create_contract("j", BUYER, PROVIDER, Decimal("1.0"), milestones=ms)
        assert not ok

    async def test_too_many_milestones(self, mgr: EscrowManager):
        ms = [{"milestone_id": f"m{i}", "description": "d", "amount": Decimal("0.1")} for i in range(mgr.max_milestones + 1)]
        ok, _, _ = await mgr.create_contract("j", BUYER, PROVIDER, Decimal("1.0"), milestones=ms)
        assert not ok


# --- fund_contract / start_job state guards ---------------------------------


class TestStateGuards:
    async def test_fund_nonexistent(self, mgr: EscrowManager):
        ok, msg = await mgr.fund_contract("nope", "0x")
        assert not ok and "not found" in msg

    async def test_fund_already_funded(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        ok, msg = await mgr.fund_contract(cid, "0x")
        assert not ok and "funded" in msg

    async def test_start_job_wrong_state(self, mgr: EscrowManager):
        ok, _, cid = await mgr.create_contract("j", BUYER, PROVIDER, Decimal("1"))
        ok2, msg = await mgr.start_job(cid)
        assert not ok2 and "created" in msg

    async def test_start_job_nonexistent(self, mgr: EscrowManager):
        ok, msg = await mgr.start_job("nope")
        assert not ok


# --- complete_milestone / verify_milestone ----------------------------------


class TestMilestoneLifecycle:
    async def test_complete_nonexistent_milestone(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        ok, msg = await mgr.complete_milestone(cid, "nope")
        assert not ok and "not found" in msg

    async def test_complete_already_completed(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        await mgr.complete_milestone(cid, "milestone_1")
        ok, msg = await mgr.complete_milestone(cid, "milestone_1")
        assert not ok and "already" in msg

    async def test_verify_uncompleted_milestone(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        ok, msg = await mgr.verify_milestone(cid, "milestone_1")
        assert not ok and "not completed" in msg

    async def test_verify_already_verified(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        await mgr.complete_milestone(cid, "milestone_1")
        await mgr.verify_milestone(cid, "milestone_1")
        ok, msg = await mgr.verify_milestone(cid, "milestone_1")
        assert not ok and "already verified" in msg

    async def test_complete_with_evidence(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        ok, _ = await mgr.complete_milestone(cid, "milestone_1", evidence={"url": "http://x"})
        assert ok
        ms = mgr.escrow_contracts[cid].milestones[0]
        assert ms.get("evidence") == {"url": "http://x"}

    async def test_complete_milestone_wrong_state(self, mgr: EscrowManager):
        ok, _, cid = await mgr.create_contract("j", BUYER, PROVIDER, Decimal("1"))
        ok2, msg = await mgr.complete_milestone(cid, "milestone_1")
        assert not ok2 and "created" in msg


# --- release_payment --------------------------------------------------------


class TestReleasePayment:
    async def test_release_wrong_state(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        ok, msg = await mgr.release_payment(cid)
        assert not ok and "funded" in msg

    async def test_release_unverified_milestones(self, mgr: EscrowManager):
        cid = await _make_completed(mgr)
        ok, msg = await mgr.release_payment(cid)
        assert not ok and "verified" in msg.lower()

    async def test_release_zero_billed(self, mgr: EscrowManager):
        cid = await _make_completed(mgr)
        await mgr.verify_milestone(cid, "milestone_1")
        ok, msg = await mgr.release_payment(cid, billed_amount=Decimal("0"))
        assert not ok and "positive" in msg

    async def test_release_clamps_over_escrow(self, mgr: EscrowManager):
        cid = await _make_completed(mgr)
        await mgr.verify_milestone(cid, "milestone_1")
        ok, _ = await mgr.release_payment(cid, billed_amount=Decimal("999"))
        assert ok
        c = mgr.escrow_contracts[cid]
        assert c.state == EscrowState.RELEASED

    async def test_release_partial_billing(self, mgr: EscrowManager):
        cid = await _make_completed(mgr, amount=Decimal("2.0"))
        await mgr.verify_milestone(cid, "milestone_1")
        ok, _ = await mgr.release_payment(cid, billed_amount=Decimal("1.0"))
        assert ok
        c = mgr.escrow_contracts[cid]
        # verify_milestone already released 2.0-0.05=1.95; partial bill adds nothing
        assert c.released_amount == Decimal("1.9500")

    async def test_release_protected_underpay_energy_floor(self, mgr: EscrowManager):
        ok, _, cid = await mgr.create_contract(
            "prot",
            BUYER,
            PROVIDER,
            Decimal("1.0"),
            protected=True,
            energy_net_floor_units=200_000_000,  # 0.2 AIT in units (8 decimals)
            energy_provider_credit_units=500_000_000,  # 0.5 AIT
        )
        await mgr.fund_contract(cid, "0x")
        await mgr.complete_milestone(cid, "milestone_1")
        await mgr.verify_milestone(cid, "milestone_1")
        mgr.escrow_contracts[cid].state = EscrowState.JOB_COMPLETED
        # Bill below the provider credit floor
        ok2, msg = await mgr.release_payment(cid, billed_amount=Decimal("0.1"))
        assert not ok2 and "energy floor" in msg.lower()

    async def test_release_nonexistent(self, mgr: EscrowManager):
        ok, msg = await mgr.release_payment("nope")
        assert not ok and "not found" in msg


# --- dispute lifecycle ------------------------------------------------------


class TestDisputeLifecycle:
    async def test_create_dispute_nonexistent(self, mgr: EscrowManager):
        ok, msg = await mgr.create_dispute("nope", DisputeReason.TECHNICAL_ISSUES, "d")
        assert not ok and "not found" in msg

    async def test_create_dispute_already_disputed(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        await mgr.create_dispute(cid, DisputeReason.TECHNICAL_ISSUES, "d")
        ok, msg = await mgr.create_dispute(cid, DisputeReason.TECHNICAL_ISSUES, "d")
        assert not ok and "already" in msg

    async def test_create_dispute_wrong_state(self, mgr: EscrowManager):
        ok, _, cid = await mgr.create_contract("j", BUYER, PROVIDER, Decimal("1"))
        ok2, msg = await mgr.create_dispute(cid, DisputeReason.TECHNICAL_ISSUES, "d")
        assert not ok2 and "created" in msg

    async def test_create_dispute_too_much_evidence(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        ev = [{"x": i} for i in range(mgr.max_dispute_evidence + 1)]
        ok, msg = await mgr.create_dispute(cid, DisputeReason.TECHNICAL_ISSUES, "d", evidence=ev)
        assert not ok and "evidence" in msg.lower()

    async def test_resolve_dispute_wrong_state(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        ok, msg = await mgr.resolve_dispute(cid, {"winner": "client", "client_refund": "0.5", "agent_payment": "0.5"})
        assert not ok and "not in disputed" in msg.lower()

    async def test_resolve_dispute_invalid_format(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        await mgr.create_dispute(cid, DisputeReason.TECHNICAL_ISSUES, "d")
        ok, msg = await mgr.resolve_dispute(cid, {"winner": "client"})
        assert not ok and "format" in msg.lower()

    async def test_resolve_dispute_exceeds_amount(self, mgr: EscrowManager):
        cid = await _make_funded(mgr, amount=Decimal("1.0"))
        await mgr.create_dispute(cid, DisputeReason.TECHNICAL_ISSUES, "d")
        ok, msg = await mgr.resolve_dispute(cid, {"winner": "client", "client_refund": "2.0", "agent_payment": "0.5"})
        assert not ok and "exceed" in msg.lower()

    async def test_resolve_dispute_success(self, mgr: EscrowManager):
        cid = await _make_funded(mgr, amount=Decimal("1.0"))
        await mgr.create_dispute(cid, DisputeReason.TECHNICAL_ISSUES, "d")
        ok, _ = await mgr.resolve_dispute(cid, {"winner": "client", "client_refund": "0.5", "agent_payment": "0.5"})
        assert ok
        c = mgr.escrow_contracts[cid]
        assert c.state == EscrowState.RESOLVED
        assert c.released_amount == Decimal("0.5")
        assert c.refunded_amount == Decimal("0.5")


# --- refund / expire --------------------------------------------------------


class TestRefundExpire:
    async def test_refund_nonexistent(self, mgr: EscrowManager):
        ok, msg = await mgr.refund_contract("nope")
        assert not ok and "not found" in msg

    async def test_refund_released_contract(self, mgr: EscrowManager):
        cid = await _make_completed(mgr)
        await mgr.verify_milestone(cid, "milestone_1")
        await mgr.release_payment(cid)
        ok, msg = await mgr.refund_contract(cid)
        assert not ok and "released" in msg

    async def test_refund_no_amount_available(self, mgr: EscrowManager):
        cid = await _make_funded(mgr, amount=Decimal("1.0"))
        c = mgr.escrow_contracts[cid]
        c.released_amount = Decimal("1.0")  # exhaust
        ok, msg = await mgr.refund_contract(cid)
        assert not ok and "No amount" in msg

    async def test_expire_not_yet_expired(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        ok, msg = await mgr.expire_contract(cid)
        assert not ok and "not expired" in msg.lower()

    async def test_expire_already_released(self, mgr: EscrowManager):
        cid = await _make_completed(mgr)
        await mgr.verify_milestone(cid, "milestone_1")
        await mgr.release_payment(cid)
        c = mgr.escrow_contracts[cid]
        c.expires_at = time.time() - 1
        ok, msg = await mgr.expire_contract(cid)
        assert not ok and "final" in msg.lower()

    async def test_expire_funded_triggers_refund(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        c = mgr.escrow_contracts[cid]
        c.expires_at = time.time() - 1
        ok, msg = await mgr.expire_contract(cid)
        assert ok
        assert c.state == EscrowState.REFUNDED


# --- add_milestone ----------------------------------------------------------


class TestAddMilestone:
    async def test_add_milestone_nonexistent(self, mgr: EscrowManager):
        ok, msg = await mgr.add_milestone("nope", "m2", Decimal("0.5"))
        assert not ok and "not found" in msg

    async def test_add_milestone_wrong_state(self, mgr: EscrowManager):
        ok, _, cid = await mgr.create_contract("j", BUYER, PROVIDER, Decimal("1"))
        ok2, msg = await mgr.add_milestone(cid, "m2", Decimal("0.5"))
        assert not ok2 and "active" in msg.lower()

    async def test_add_milestone_below_minimum(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        ok, msg = await mgr.add_milestone(cid, "m2", Decimal("0.001"))
        assert not ok and "at least" in msg.lower()

    async def test_add_milestone_max_reached(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        c = mgr.escrow_contracts[cid]
        # Fill to max
        for i in range(mgr.max_milestones - 1):
            c.milestones.append({"milestone_id": f"fill{i}", "description": "", "amount": Decimal("0.01"), "completed": False})
        ok, msg = await mgr.add_milestone(cid, "mX", Decimal("0.01"))
        assert not ok and "Maximum" in msg

    async def test_add_milestone_success(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        ok, _ = await mgr.add_milestone(cid, "m2", Decimal("0.5"), "extra")
        assert ok
        c = mgr.escrow_contracts[cid]
        assert len(c.milestones) == 2


# --- agent failure / fail_job / reassignment -------------------------------


class TestFailureReassignment:
    async def test_report_agent_failure_wrong_agent(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        ok, msg = await mgr.report_agent_failure(cid, OTHER, "no work")
        assert not ok and "mismatch" in msg.lower()

    async def test_report_agent_failure_wrong_state(self, mgr: EscrowManager):
        ok, _, cid = await mgr.create_contract("j", BUYER, PROVIDER, Decimal("1"))
        ok2, msg = await mgr.report_agent_failure(cid, PROVIDER, "no work")
        assert not ok2 and "active" in msg.lower()

    async def test_report_agent_failure_success(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        ok, _ = await mgr.report_agent_failure(cid, PROVIDER, "no work")
        assert ok
        c = mgr.escrow_contracts[cid]
        assert c.state == EscrowState.DISPUTED
        assert cid in mgr.disputed_contracts

    async def test_fail_job_wrong_state(self, mgr: EscrowManager):
        ok, _, cid = await mgr.create_contract("j", BUYER, PROVIDER, Decimal("1"))
        ok2, msg = await mgr.fail_job(cid)
        assert not ok2 and "failable" in msg.lower()

    async def test_fail_job_success(self, mgr: EscrowManager):
        cid = await _make_funded(mgr, amount=Decimal("1.0"))
        ok, msg = await mgr.fail_job(cid)
        assert ok
        c = mgr.escrow_contracts[cid]
        assert c.state == EscrowState.REFUNDED
        assert "refund amount" in msg.lower()

    async def test_reassign_wrong_state(self, mgr: EscrowManager):
        ok, _, cid = await mgr.create_contract("j", BUYER, PROVIDER, Decimal("1"))
        ok2, msg = await mgr.reassign_job(cid, OTHER)
        assert not ok2 and "reassignable" in msg.lower()

    async def test_reassign_from_disputed(self, mgr: EscrowManager):
        cid = await _make_funded(mgr)
        await mgr.report_agent_failure(cid, PROVIDER, "bad")
        ok, _ = await mgr.reassign_job(cid, OTHER)
        assert ok
        c = mgr.escrow_contracts[cid]
        assert c.agent_address == OTHER
        assert c.state == EscrowState.JOB_STARTED
        assert cid not in mgr.disputed_contracts


# --- process_refund / process_partial_payment ------------------------------


class TestProcessRefundPartial:
    async def test_process_refund_nonexistent(self, mgr: EscrowManager):
        ok, amt = await mgr.process_refund("nope")
        assert not ok and amt == Decimal("0")

    async def test_process_refund_success(self, mgr: EscrowManager):
        cid = await _make_funded(mgr, amount=Decimal("1.0"))
        ok, amt = await mgr.process_refund(cid)
        assert ok and amt == Decimal("1.0")
        c = mgr.escrow_contracts[cid]
        assert c.state == EscrowState.REFUNDED

    async def test_process_partial_payment_nonexistent(self, mgr: EscrowManager):
        agent, client = await mgr.process_partial_payment("nope")
        assert agent == Decimal("0") and client == Decimal("0")

    async def test_process_partial_payment_with_completed(self, mgr: EscrowManager):
        cid = await _make_funded(mgr, amount=Decimal("2.0"))
        await mgr.complete_milestone(cid, "milestone_1")
        agent, client = await mgr.process_partial_payment(cid)
        assert agent > Decimal("0")
        assert client == Decimal("0.0")  # full milestone completed, nothing left


# --- query helpers ----------------------------------------------------------


class TestQueryHelpers:
    async def test_get_contracts_by_client(self, mgr: EscrowManager):
        await _make_funded(mgr, "j1")
        await _make_funded(mgr, "j2")
        results = await mgr.get_contracts_by_client(BUYER)
        assert len(results) == 2

    async def test_get_contracts_by_agent(self, mgr: EscrowManager):
        await _make_funded(mgr, "j1")
        results = await mgr.get_contracts_by_agent(PROVIDER)
        assert len(results) == 1

    async def test_get_active_contracts(self, mgr: EscrowManager):
        await _make_funded(mgr, "j1")
        active = await mgr.get_active_contracts()
        assert len(active) == 1

    async def test_get_disputed_contracts(self, mgr: EscrowManager):
        cid = await _make_funded(mgr, "j1")
        await mgr.create_dispute(cid, DisputeReason.TECHNICAL_ISSUES, "d")
        disputed = await mgr.get_disputed_contracts()
        assert len(disputed) == 1

    async def test_get_escrow_statistics(self, mgr: EscrowManager):
        await _make_funded(mgr, "j1", amount=Decimal("1.0"))
        stats = await mgr.get_escrow_statistics()
        assert stats["total_contracts"] == 1
        assert stats["active_contracts"] == 1
        assert stats["disputed_contracts"] == 0
        assert "state_distribution" in stats
