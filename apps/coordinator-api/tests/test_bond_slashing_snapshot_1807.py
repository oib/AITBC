"""#1807: bond_slashing binds a unique bond row and CAS-applies the slash."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from aitbc_shared import JobPayment
from eth_account import Account

from coordinator_api.contexts.infrastructure.domain import Job
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.infrastructure.services.miners import MinerService
from coordinator_api.contexts.market.domain.provider_bond import (
    ProviderBond,
    ProviderBondStatus,
    apply_bond_slash_cas,
)
from coordinator_api.contexts.market.services.bond_slashing import BondSlashingService, SlashingCondition
from coordinator_api.schemas import JobCreate, MinerRegister

PROVIDER_WALLET = "0x1111111111111111111111111111111111111111"


def _miner(db_session, miner_id: str = "miner1", wallet: str = PROVIDER_WALLET):
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


@pytest.fixture
def slash_env(monkeypatch):
    account = Account.create()
    monkeypatch.setenv("BOND_SLASH_AUTHORITY_ADDRESS", account.address)
    monkeypatch.setenv("BOND_SLASH_PRIVATE_KEY", account.key.hex())
    monkeypatch.setenv("BOND_BURN_ADDRESS", "0x3333333333333333333333333333333333333333")


def _second_bond(db_session, provider_id: str, *, bond_id: str, amount: str) -> ProviderBond:
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


@pytest.mark.asyncio
async def test_slash_updates_named_bond_when_provider_has_two_rows(db_session, slash_env):
    """With two active rows per provider_id, constraints.bond_id picks the target."""
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    job.constraints = {**(job.constraints or {}), "bond_id": "bond-target"}
    db_session.add(job)
    db_session.commit()

    untouched = _provider_bond(db_session, miner.id, amount="20", bond_id="bond-other")
    target = _provider_bond(db_session, miner.id, amount="10", bond_id="bond-target")

    with patch("coordinator_api.contexts.market.services.bond_slashing.AITBCHTTPClient") as mock_client:
        client = mock_client.return_value
        client.get.return_value = {"nonce": 0}
        client.post.return_value = {"transaction_hash": "0xbind"}

        result = await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")

    assert result["slashed"] is True
    assert result.get("bond_record_applied") is True
    db_session.refresh(untouched)
    db_session.refresh(target)
    assert untouched.amount == Decimal("20")
    assert target.amount == Decimal("7")


@pytest.mark.asyncio
async def test_slash_refuses_ambiguous_provider_without_bond_id(db_session, slash_env):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()

    _provider_bond(db_session, miner.id, amount="10", bond_id="bond-a")
    _second_bond(db_session, miner.id, bond_id="bond-b", amount="12")

    with patch("coordinator_api.contexts.market.services.bond_slashing.AITBCHTTPClient") as mock_client:
        result = await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")

    assert result["slashed"] is False
    assert result["reason"] == "no active bond"
    mock_client.assert_not_called()


def test_apply_bond_slash_cas_rejects_stale_amount(db_session):
    bond = _provider_bond(db_session, "miner-x", amount="10", bond_id="bond-cas")
    snapshot_amount = bond.amount
    snapshot_updated = bond.updated_at

    bond.amount = Decimal("12")
    db_session.add(bond)
    db_session.commit()
    db_session.refresh(bond)

    applied = apply_bond_slash_cas(
        db_session,
        bond.id,
        expected_amount=snapshot_amount,
        expected_updated_at=snapshot_updated,
        new_amount=Decimal("7"),
        status=ProviderBondStatus.ACTIVE,
        meta={**(bond.meta or {}), "slash_condition": "bad_result"},
    )
    assert applied is None
    row = db_session.get(ProviderBond, bond.id)
    assert row is not None and row.amount == Decimal("12")


@pytest.mark.asyncio
async def test_on_chain_slash_with_stale_snapshot_skips_blind_write(db_session, slash_env):
    """A concurrent top-up between snapshot and CAS must not apply a blind write."""
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    job.constraints = {**(job.constraints or {}), "bond_id": "bond-solo"}
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10", bond_id="bond-solo")

    def _post(url, json=None, **_kw):
        row = db_session.get(ProviderBond, bond.id)
        assert row is not None
        row.amount = Decimal("12")
        db_session.add(row)
        db_session.commit()
        return {"transaction_hash": "0xstale"}

    with patch("coordinator_api.contexts.market.services.bond_slashing.AITBCHTTPClient") as mock_client:
        client = mock_client.return_value
        client.get.return_value = {"nonce": 0}
        client.post.side_effect = _post

        result = await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")

    assert result["slashed"] is True
    assert result.get("bond_record_applied") is False
    row = db_session.get(ProviderBond, bond.id)
    assert row is not None and row.amount == Decimal("12")
    assert row.meta.get("slash_condition") is None
