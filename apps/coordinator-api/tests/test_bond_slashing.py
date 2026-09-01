"""Tests for automatic provider-bond slashing (G5).

A bond is on-chain, but until now it could only be slashed by a manual admin call.
This suite checks the coordinator-driven automatic slash for downtime, fraud, and
bad-result conditions.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from aitbc_shared import JobPayment
from fastapi import HTTPException

from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.infrastructure.services.miners import MinerService
from coordinator_api.contexts.marketplace.domain.provider_bond import (
    ProviderBond,
    ProviderBondStatus,
    is_provider_eligible,
    set_provider_bond_status,
)
from sqlmodel import select
from coordinator_api.contexts.marketplace.services.bond_slash_sweeper import BondSlashSweeper
from coordinator_api.contexts.marketplace.services.bond_slashing import (
    SlashingCondition,
    BondSlashingService,
    _job_bond_required,
    _compute_slash_amount,
)
from coordinator_api.schemas import JobCreate, MinerRegister


PROVIDER_WALLET = "0x1111111111111111111111111111111111111111"


def _miner(db_session, miner_id: str = "miner1", wallet: str = PROVIDER_WALLET) -> Miner:
    payload = MinerRegister(capabilities={}, concurrency=1, region=None, wallet_address=wallet)
    return MinerService(db_session).register(miner_id, payload)


def _bonded_job(db_session, *, bond_required: bool = True, state: str = "FAILED") -> Job:
    service = JobService(db_session)
    req = JobCreate(
        payload={"type": "inference", "prompt": "test"},
        constraints={"bond_required": bond_required, "min_bond_amount": "5"},
        ttl_seconds=900,
        payment_amount=Decimal("5"),
        payment_currency="AITBC",
    )
    job = service.create_job(client_id="client1", req=req)
    payment = JobPayment(
        job_id=job.id,
        amount=Decimal("5"),
        currency="AITBC",
        payment_method="aitbc_token",
        status="escrowed",
        meta_data={},
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    job.payment_id = payment.id
    job.state = state
    if state in {"FAILED", "COMPLETED", "RUNNING"}:
        job.completed_at = datetime.now(UTC)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _provider_bond(db_session, provider_id: str, amount: str = "10", bond_id: str = "bond-test") -> ProviderBond:
    bond = ProviderBond(
        provider_id=provider_id,
        bond_id=bond_id,
        status=ProviderBondStatus.ACTIVE.value,
        amount=Decimal(amount),
        required_amount=Decimal("5"),
    )
    db_session.add(bond)
    db_session.commit()
    db_session.refresh(bond)
    return bond


def test_job_bond_required_reads_constraints():
    job = Job(constraints={"bond_required": True})
    assert _job_bond_required(job)
    job = Job(constraints={"bond_required": False})
    assert not _job_bond_required(job)
    job = Job(constraints=None)
    assert not _job_bond_required(job)


def test_slash_amount_computed_deterministically():
    bond = ProviderBond(amount=Decimal("10"))
    assert _compute_slash_amount(bond, SlashingCondition.DOWNTIME) == 1  # 10%
    assert _compute_slash_amount(bond, SlashingCondition.BAD_RESULT) == 3  # 30%
    assert _compute_slash_amount(bond, SlashingCondition.FRAUD) == 5  # 50%

    bond = ProviderBond(amount=Decimal("1"))
    assert _compute_slash_amount(bond, SlashingCondition.DOWNTIME) == 1


@pytest.fixture
def slash_env(monkeypatch):
    monkeypatch.setenv("BOND_SLASH_AUTHORITY_ADDRESS", "0x2222222222222222222222222222222222222222")
    monkeypatch.setenv(
        "BOND_SLASH_PRIVATE_KEY",
        "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    )
    monkeypatch.setenv("BOND_BURN_ADDRESS", "0x3333333333333333333333333333333333333333")


@pytest.mark.asyncio
async def test_slash_happens_for_bonded_bad_result(db_session, slash_env):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    with patch("coordinator_api.contexts.marketplace.services.bond_slashing.AITBCHTTPClient") as mock_client:
        client = mock_client.return_value
        client.get.return_value = {"nonce": 5}
        client.post.return_value = {"transaction_hash": "0xdeadbeef"}

        result = await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad output")

    assert result["slashed"] is True
    assert result["amount"] == 3
    assert result["tx_hash"] == "0xdeadbeef"
    db_session.refresh(bond)
    assert bond.amount == Decimal("7")
    assert bond.status == ProviderBondStatus.ACTIVE.value  # 7 >= required 5
    assert bond.meta["slash_condition"] == "bad_result"


@pytest.mark.asyncio
async def test_slash_marks_shortfall_when_remaining_below_required(db_session, slash_env):
    """A partial slash that leaves the bond below the required amount is a shortfall."""
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="6")

    with patch("coordinator_api.contexts.marketplace.services.bond_slashing.AITBCHTTPClient") as mock_client:
        client = mock_client.return_value
        client.get.return_value = {"nonce": 0}
        client.post.return_value = {"transaction_hash": "0xshortfall"}

        result = await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad output")

    assert result["slashed"] is True
    assert result["amount"] == 2  # 30% of 6 rounded up
    db_session.refresh(bond)
    assert bond.amount == Decimal("4")
    assert bond.status == ProviderBondStatus.SHORTFALL.value  # 4 < required 5


@pytest.mark.asyncio
async def test_slash_liquidates_bond_when_full(db_session, slash_env):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="1")

    with patch("coordinator_api.contexts.marketplace.services.bond_slashing.AITBCHTTPClient") as mock_client:
        client = mock_client.return_value
        client.get.return_value = {"nonce": 0}
        client.post.return_value = {"transaction_hash": "0xliquidated"}

        result = await BondSlashingService(db_session).slash(job, SlashingCondition.FRAUD, "fraud")

    assert result["slashed"] is True
    assert result["amount"] == 1
    db_session.refresh(bond)
    assert bond.status == ProviderBondStatus.LIQUIDATED.value


@pytest.mark.asyncio
async def test_slash_skips_without_bond(db_session, slash_env):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()

    with patch("coordinator_api.contexts.marketplace.services.bond_slashing.AITBCHTTPClient") as mock_client:
        result = await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")
    assert result["slashed"] is False
    assert result["reason"] == "no active bond"
    mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_slash_skips_unconfigured(db_session):
    for var in ("BOND_SLASH_AUTHORITY_ADDRESS", "BOND_SLASH_PRIVATE_KEY", "BOND_BURN_ADDRESS"):
        os.environ.pop(var, None)
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    _provider_bond(db_session, miner.id)

    with patch("coordinator_api.contexts.marketplace.services.bond_slashing.AITBCHTTPClient") as mock_client:
        result = await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")
    assert result["slashed"] is False
    assert result["reason"] == "slashing not configured"
    mock_client.assert_not_called()


@contextmanager
def _non_closing_session(session):
    yield session


@pytest.mark.asyncio
async def test_sweeper_finds_stale_running_job(db_session, slash_env):
    miner = _miner(db_session)
    miner.last_heartbeat = datetime.now(UTC) - timedelta(seconds=600)
    db_session.add(miner)
    job = _bonded_job(db_session, state="RUNNING")
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    _provider_bond(db_session, miner.id, amount="10")

    sweeper = BondSlashSweeper(
        interval_seconds=1,
        batch_size=10,
        session_factory=lambda: _non_closing_session(db_session),
    )

    with patch("coordinator_api.contexts.marketplace.services.bond_slash_sweeper.BondSlashingService") as mock_svc:
        instance = mock_svc.return_value
        instance.slash = AsyncMock(return_value={"slashed": True, "amount": 1})
        counts = await sweeper.run_once()
        assert counts["stale"] == 1
        assert counts["slashed"] == 1
        instance.slash.assert_awaited_once()
        _, args, _ = instance.slash.mock_calls[0]
        assert args[1] == SlashingCondition.DOWNTIME


# ---------------------------------------------------------------------------
# D1: only an operator's ruling slashes. A rejection is a claim, not a finding.
# ---------------------------------------------------------------------------


def _disputable_job(db_session, miner):
    """A bonded job whose escrow is sitting in the customer's acceptance window."""
    job = _bonded_job(db_session, state="COMPLETED")
    job.assigned_miner_id = miner.id
    job.payment_status = "pending_acceptance"
    payment = db_session.get(JobPayment, job.payment_id)
    payment.status = "pending_acceptance"
    payment.meta_data = {"acceptance_deadline": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}
    db_session.add(job)
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(job)
    return job


@pytest.mark.asyncio
async def test_customer_rejection_does_not_slash_the_bond(db_session, slash_env):
    """Rejecting opens a dispute and leaves the bond alone (D1).

    Slashing here would let a buyer burn half a provider's stake by typing a reason,
    with no operator in the loop -- the mirror of the unilateral release the
    acceptance window was built to remove.
    """
    from coordinator_api.contexts.infrastructure.routers.client import reject_job
    from coordinator_api.schemas import JobRejection

    miner = _miner(db_session)
    job = _disputable_job(db_session, miner)
    bond = _provider_bond(db_session, miner.id, amount="10")

    with patch("coordinator_api.contexts.marketplace.services.bond_slashing.AITBCHTTPClient") as mock_client:
        view = await reject_job(
            request=None,
            job_id=job.id,
            req=JobRejection(reason="the transcript is empty"),
            session=db_session,
            user={"sub": "client1"},
        )

    assert view.payment_status == "disputed"
    mock_client.assert_not_called()
    db_session.refresh(bond)
    assert bond.amount == Decimal("10")
    assert bond.status == ProviderBondStatus.ACTIVE.value


# ---------------------------------------------------------------------------
# Bond-floor enforcement (G3 follow-up)
# ---------------------------------------------------------------------------


def test_is_provider_eligible_requires_active_or_locked_status(db_session):
    assert is_provider_eligible(db_session, "unknown") is False
    _provider_bond(db_session, "miner1", amount="10")
    assert is_provider_eligible(db_session, "miner1") is True

    bond = db_session.exec(select(ProviderBond).where(ProviderBond.provider_id == "miner1")).first()
    bond.status = ProviderBondStatus.SHORTFALL.value
    db_session.add(bond)
    db_session.commit()
    assert is_provider_eligible(db_session, "miner1") is False


def test_is_provider_eligible_checks_amount_against_min_amount(db_session):
    _provider_bond(db_session, "miner1", amount="10")
    assert is_provider_eligible(db_session, "miner1", min_amount=Decimal("5")) is True
    assert is_provider_eligible(db_session, "miner1", min_amount=Decimal("15")) is False


def test_is_provider_eligible_uses_required_amount_as_floor(db_session):
    bond = _provider_bond(db_session, "miner1", amount="3")
    bond.required_amount = Decimal("5")
    db_session.add(bond)
    db_session.commit()
    assert is_provider_eligible(db_session, "miner1") is False

    bond.amount = Decimal("6")
    db_session.add(bond)
    db_session.commit()
    assert is_provider_eligible(db_session, "miner1") is True


def test_set_provider_bond_status_preserves_amount_and_required_amount(db_session):
    _provider_bond(db_session, "miner1", amount="10")
    set_provider_bond_status(db_session, "miner1", ProviderBondStatus.LOCKED)
    bond = db_session.exec(select(ProviderBond).where(ProviderBond.provider_id == "miner1")).first()
    assert bond.status == ProviderBondStatus.LOCKED.value
    assert bond.amount == Decimal("10")
    assert bond.required_amount == Decimal("5")


def test_job_service_filters_providers_below_bond_floor(db_session, monkeypatch):
    monkeypatch.setenv("COORDINATOR_BOND_MIN_AMOUNT", "5")
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    bond = _provider_bond(db_session, miner.id, amount="2")
    assert JobService(db_session)._satisfies_constraints(job, miner) is False

    bond.amount = Decimal("10")
    db_session.add(bond)
    db_session.commit()
    assert JobService(db_session)._satisfies_constraints(job, miner) is True


def test_job_service_uses_constraints_min_bond_amount(db_session, monkeypatch):
    monkeypatch.setenv("COORDINATOR_BOND_MIN_AMOUNT", "1")
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.constraints = {"bond_required": True, "min_bond_amount": "15"}
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")
    assert JobService(db_session)._satisfies_constraints(job, miner) is False

    bond.amount = Decimal("20")
    db_session.add(bond)
    db_session.commit()
    assert JobService(db_session)._satisfies_constraints(job, miner) is True


@pytest.mark.asyncio
async def test_operator_ruling_for_refund_slashes_the_bond(db_session, slash_env):
    """The refund branch of the admin ruling is where the fraud slash lives."""
    from coordinator_api.contexts.infrastructure.routers.admin import resolve_dispute
    from coordinator_api.schemas import DisputeResolution

    miner = _miner(db_session)
    job = _disputable_job(db_session, miner)
    job.payment_status = "disputed"
    db_session.add(job)
    db_session.commit()
    payment = db_session.get(JobPayment, job.payment_id)
    payment.status = "disputed"
    db_session.add(payment)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    with (
        patch("coordinator_api.contexts.marketplace.services.bond_slashing.AITBCHTTPClient") as mock_client,
        patch(
            "coordinator_api.contexts.payments.services.payments.PaymentService.refund_payment",
            new=AsyncMock(return_value=True),
        ),
    ):
        client = mock_client.return_value
        client.get.return_value = {"nonce": 1}
        client.post.return_value = {"transaction_hash": "0xruled"}
        result = await resolve_dispute(
            request=None,
            job_id=job.id,
            req=DisputeResolution(outcome="refund", reason="output did not match the prompt"),
            session=db_session,
            user={"sub": "admin1"},
        )

    assert result["payment_status"] == "refunded"
    db_session.refresh(bond)
    assert bond.amount == Decimal("5")
    assert bond.meta["slash_condition"] == "fraud"


@pytest.mark.asyncio
async def test_a_refund_that_does_not_settle_leaves_the_bond_intact(db_session, slash_env):
    """A 502 keeps the ruling re-issuable, so the bond must not be spent on it."""
    from coordinator_api.contexts.infrastructure.routers.admin import resolve_dispute
    from coordinator_api.schemas import DisputeResolution

    miner = _miner(db_session)
    job = _disputable_job(db_session, miner)
    job.payment_status = "disputed"
    db_session.add(job)
    db_session.commit()
    payment = db_session.get(JobPayment, job.payment_id)
    payment.status = "disputed"
    db_session.add(payment)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    with (
        patch("coordinator_api.contexts.marketplace.services.bond_slashing.AITBCHTTPClient") as mock_client,
        patch(
            "coordinator_api.contexts.payments.services.payments.PaymentService.refund_payment",
            new=AsyncMock(return_value=False),
        ),
        pytest.raises(HTTPException) as exc,
    ):
        await resolve_dispute(
            request=None,
            job_id=job.id,
            req=DisputeResolution(outcome="refund", reason="output did not match the prompt"),
            session=db_session,
            user={"sub": "admin1"},
        )

    assert exc.value.status_code == 502
    mock_client.assert_not_called()
    db_session.refresh(bond)
    assert bond.amount == Decimal("10")
    assert bond.status == ProviderBondStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_operator_ruling_for_release_does_not_slash(db_session, slash_env):
    """Ruling for the provider pays it and leaves its bond where it was."""
    from coordinator_api.contexts.infrastructure.routers.admin import resolve_dispute
    from coordinator_api.schemas import DisputeResolution

    miner = _miner(db_session)
    job = _disputable_job(db_session, miner)
    job.payment_status = "disputed"
    db_session.add(job)
    db_session.commit()
    payment = db_session.get(JobPayment, job.payment_id)
    payment.status = "disputed"
    db_session.add(payment)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    with (
        patch("coordinator_api.contexts.marketplace.services.bond_slashing.AITBCHTTPClient") as mock_client,
        patch(
            "coordinator_api.contexts.payments.services.payments.PaymentService.release_payment",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await resolve_dispute(
            request=None,
            job_id=job.id,
            req=DisputeResolution(outcome="release", reason="the result matches the prompt"),
            session=db_session,
            user={"sub": "admin1"},
        )

    assert result["payment_status"] == "released"
    mock_client.assert_not_called()
    db_session.refresh(bond)
    assert bond.amount == Decimal("10")
    assert bond.status == ProviderBondStatus.ACTIVE.value
