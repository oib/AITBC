"""No refund path may return more than the buyer locked.

``create_contract`` used to store ``amount + platform_fee`` as the contract's
amount, a fee-on-top model that nothing else in the system implements. The
buyer's ESCROW_LOCK moves exactly ``amount`` into the node wallet, the Escrow row
records exactly ``amount``, and ``release_payment`` takes the platform fee *out*
of that. Meanwhile every refund path returns ``amount - released_amount``, so the
inflated principal paid buyers 2.5% more than they had locked -- and the excess
came out of the node wallet.

The tell was that only some refunds were wrong: ``load_from_db`` rebuilds a
contract with ``amount = units_to_ait(record.amount)``, the true lock, so an
escrow refunded after a restart settled correctly while the same escrow refunded
by the process that created it over-paid.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from aitbc_chain.base_models import Escrow as EscrowRecord
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.contracts.escrow import EscrowManager, EscrowState
from aitbc.utils import ait_to_units
from sqlmodel import Session, create_engine

BUYER = "0x1234567890123456789012345678901234567890"
PROVIDER = "0x2345678901234567890123456789012345678901"
LOCK = Decimal("100.0")
FEE_RATE = Decimal("0.025")


@pytest.fixture
def mgr():
    return EscrowManager()


async def _funded(mgr, job_id="job_1", amount=LOCK, milestones=None):
    """Create and fund a contract, returning its id."""
    success, message, contract_id = await mgr.create_contract(
        job_id=job_id,
        client_address=BUYER,
        agent_address=PROVIDER,
        amount=amount,
        milestones=milestones,
    )
    assert success, message
    success, message = await mgr.fund_contract(contract_id, "0xlock")
    assert success, message
    return contract_id


class TestPrincipal:
    @pytest.mark.asyncio
    async def test_contract_amount_is_the_locked_principal(self, mgr):
        contract_id = await _funded(mgr)
        contract = mgr.escrow_contracts[contract_id]
        assert contract.amount == LOCK

    @pytest.mark.asyncio
    async def test_milestones_sum_to_the_principal(self, mgr):
        """They always did; the principal is what drifted away from them."""
        contract_id = await _funded(mgr)
        contract = mgr.escrow_contracts[contract_id]
        assert sum(Decimal(str(ms["amount"])) for ms in contract.milestones) == contract.amount


class TestRefundNeverExceedsTheLock:
    @pytest.mark.asyncio
    async def test_full_refund_returns_exactly_the_lock(self, mgr):
        contract_id = await _funded(mgr)
        success, message = await mgr.refund_contract(contract_id, "buyer_requested")
        assert success, message
        contract = mgr.escrow_contracts[contract_id]
        assert contract.state == EscrowState.REFUNDED
        # The regression: this was LOCK * 1.025 == 102.5.
        assert contract.refunded_amount == LOCK

    @pytest.mark.asyncio
    async def test_expiry_refund_returns_exactly_the_lock(self, mgr):
        contract_id = await _funded(mgr, job_id="job_expired")
        mgr.escrow_contracts[contract_id].expires_at = 0
        success, message = await mgr.expire_contract(contract_id)
        assert success, message
        assert mgr.escrow_contracts[contract_id].refunded_amount == LOCK

    @pytest.mark.asyncio
    async def test_failed_job_refund_returns_exactly_the_lock(self, mgr):
        contract_id = await _funded(mgr, job_id="job_failed")
        success, message = await mgr.fail_job(contract_id, "provider_unreachable")
        assert success, message
        assert mgr.escrow_contracts[contract_id].refunded_amount == LOCK

    @pytest.mark.asyncio
    async def test_process_refund_returns_exactly_the_lock(self, mgr):
        contract_id = await _funded(mgr, job_id="job_processed")
        success, amount = await mgr.process_refund(contract_id)
        assert success
        assert amount == LOCK

    @pytest.mark.asyncio
    async def test_dispute_resolution_cannot_split_more_than_the_lock(self, mgr):
        contract_id = await _funded(mgr, job_id="job_disputed")
        from aitbc_chain.contracts.escrow import DisputeReason

        await mgr.create_dispute(contract_id, DisputeReason.INCOMPLETE_WORK, "half done")
        # LOCK * 1.025 used to fit inside the contract amount and settle.
        success, message = await mgr.resolve_dispute(
            contract_id,
            {"winner": "client", "client_refund": LOCK, "agent_payment": LOCK * FEE_RATE},
        )
        assert not success, message


class TestBothConstructionPathsAgree:
    """A restart must not change what an escrow refunds.

    ``load_from_db`` takes the principal from the locked compute-units on the
    Escrow row, so it was always right; ``create_contract`` was the path that
    inflated it. The two now settle the same escrow identically.
    """

    @pytest.mark.asyncio
    async def test_a_contract_rebuilt_from_the_row_refunds_the_same(self, monkeypatch):
        engine = create_engine("sqlite://")
        chain_metadata.create_all(engine)
        session = Session(engine)
        session.add(
            EscrowRecord(
                job_id="job_reloaded",
                chain_id="test-chain",
                buyer=BUYER,
                provider=PROVIDER,
                amount=ait_to_units(LOCK),
                status="locked",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()

        @contextmanager
        def _scope(chain_id=""):
            yield session

        monkeypatch.setattr("aitbc_chain.database.session_scope", _scope)

        reloaded = EscrowManager()
        await reloaded.load_from_db()
        (contract_id,) = list(reloaded.escrow_contracts)
        assert reloaded.escrow_contracts[contract_id].amount == LOCK

        success, message = await reloaded.refund_contract(contract_id, "buyer_requested")
        assert success, message
        assert reloaded.escrow_contracts[contract_id].refunded_amount == LOCK

        in_process = EscrowManager()
        fresh_id = await _funded(in_process, job_id="job_reloaded")
        await in_process.refund_contract(fresh_id, "buyer_requested")
        assert in_process.escrow_contracts[fresh_id].refunded_amount == reloaded.escrow_contracts[contract_id].refunded_amount
        session.close()


class TestTheFeeStillComesOutOfTheEscrow:
    """Fixing the principal must not stop the platform from earning its fee."""

    @pytest.mark.asyncio
    async def test_a_full_release_pays_the_lock_less_the_fee(self, mgr):
        milestones = [
            {"milestone_id": "milestone_1", "description": "Setup", "amount": Decimal("50.0")},
            {"milestone_id": "milestone_2", "description": "Delivery", "amount": Decimal("50.0")},
        ]
        contract_id = await _funded(mgr, job_id="job_released", milestones=milestones)
        await mgr.start_job(contract_id)
        for ms in milestones:
            await mgr.complete_milestone(contract_id, ms["milestone_id"])
        for ms in milestones:
            await mgr.verify_milestone(contract_id, ms["milestone_id"])
        success, message = await mgr.release_payment(contract_id)
        assert success, message
        contract = mgr.escrow_contracts[contract_id]
        assert contract.released_amount == LOCK - LOCK * FEE_RATE

    @pytest.mark.asyncio
    async def test_statistics_report_the_retained_fee(self, mgr):
        """``total_amount - released - refunded`` is the operator's cut.

        With the principal inflated it double-counted: the fee taken out of the
        release plus the fee added on top of the lock.
        """
        milestones = [
            {"milestone_id": "milestone_1", "description": "Setup", "amount": Decimal("50.0")},
            {"milestone_id": "milestone_2", "description": "Delivery", "amount": Decimal("50.0")},
        ]
        contract_id = await _funded(mgr, job_id="job_stats", milestones=milestones)
        await mgr.start_job(contract_id)
        for ms in milestones:
            await mgr.complete_milestone(contract_id, ms["milestone_id"])
        for ms in milestones:
            await mgr.verify_milestone(contract_id, ms["milestone_id"])
        await mgr.release_payment(contract_id)
        stats = await mgr.get_escrow_statistics()
        assert Decimal(stats["total_amount"]) == LOCK
        assert Decimal(stats["total_fees"]) == LOCK * FEE_RATE
