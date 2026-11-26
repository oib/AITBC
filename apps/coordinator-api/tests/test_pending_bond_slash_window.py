"""#2976 (SLASH-AUTO-APPEAL-WINDOW-1): pre-burn appeal window for automatic
bond slashing.

Detection of ``downtime``/``bad_result`` enqueues a durable
``pending_bond_slash`` row and freezes eligibility through the #2966
suspension meta flag — it must NEVER submit a chain transaction. The sweeper's
executor pass submits the existing BOND_SLASH path only after
``window_ends_at``; an accepted appeal cancels the pending row and lifts the
suspension atomically. ``fraud`` and ``BOND_SLASH_WINDOW_ENABLED=false`` keep
the immediate inline path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from aitbc_shared import JobPayment
from eth_account import Account
from sqlmodel import select

from coordinator_api.contexts.blockchain.services.blockchain import BlockchainService
from coordinator_api.contexts.governance.domain.slash_appeal import SlashAppeal, SlashAppealStatus
from coordinator_api.contexts.governance.services.slash_appeal_review import resolve_slash_appeal
from coordinator_api.contexts.infrastructure.domain import Job, Miner
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.infrastructure.services.miners import MinerService
from coordinator_api.contexts.market.domain.pending_bond_slash import (
    PendingBondSlash,
    PendingBondSlashStatus,
)
from coordinator_api.contexts.market.domain.provider_bond import (
    ProviderBond,
    ProviderBondStatus,
    is_provider_eligible,
    suspension_event_id,
)
from coordinator_api.contexts.market.services.bond_slashing import (
    BondSlashingService,
    SlashingCondition,
    _appeal_window_seconds,
)
from coordinator_api.schemas import JobCreate, MinerRegister

PROVIDER_WALLET = "0x1111111111111111111111111111111111111111"
UNITS_PER_AIT = 36_000_000
SLASH_MODULE = "coordinator_api.contexts.market.services.bond_slashing"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _chain_bond_listing(db_session, monkeypatch):
    """Mirror the local projection as chain truth for dispatch re-verifies."""

    def fake_list(self, provider_address: str) -> dict:
        provider_ids = {
            m.id
            for m in db_session.exec(select(Miner)).all()
            if str((m.capabilities or {}).get("wallet_address") or "") == provider_address
        }
        entries = [
            {
                "bond_id": bond.bond_id,
                "amount": int((bond.amount or Decimal("0")) * UNITS_PER_AIT),
                "status": "active",
                "locked_until": None,
            }
            for bond in db_session.exec(select(ProviderBond)).all()
            if bond.provider_id in provider_ids
            and bond.status in {ProviderBondStatus.ACTIVE.value, ProviderBondStatus.LOCKED.value}
        ]
        return {"success": True, "provider": provider_address, "bonds": entries}

    monkeypatch.setattr(BlockchainService, "list_provider_bonds", fake_list)


@pytest.fixture
def slash_env(monkeypatch):
    """Configured slashing with the appeal window ENABLED (the #2976 default)."""
    monkeypatch.setenv("BOND_SLASH_WINDOW_ENABLED", "true")
    account = Account.create()
    monkeypatch.setenv("BOND_SLASH_AUTHORITY_ADDRESS", account.address)
    monkeypatch.setenv("BOND_SLASH_PRIVATE_KEY", account.key.hex())
    monkeypatch.setenv("BOND_BURN_ADDRESS", "0x3333333333333333333333333333333333333333")
    return account


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
        meta={"chain_provider": PROVIDER_WALLET},
    )
    db_session.add(bond)
    db_session.commit()
    db_session.refresh(bond)
    return bond


def _pending_rows(db_session) -> list[PendingBondSlash]:
    return list(db_session.exec(select(PendingBondSlash)).all())


def _expire_window(db_session, row: PendingBondSlash) -> None:
    row.window_ends_at = _utcnow() - timedelta(seconds=1)
    db_session.add(row)
    db_session.commit()


def _wire_submit(mock_client, tx_hash: str = "0xpending") -> None:
    """Route AITBCHTTPClient get/post to nonce probe + successful submit."""
    client = mock_client.return_value

    def _get(url):
        if "/mempool" in url:
            return {"transactions": []}
        return {"nonce": 0}

    client.get.side_effect = _get
    client.post.return_value = {"transaction_hash": tx_hash}


# ---------------------------------------------------------------------------
# Window policy
# ---------------------------------------------------------------------------


def test_window_policy_per_condition(monkeypatch):
    monkeypatch.setenv("BOND_SLASH_WINDOW_ENABLED", "true")
    monkeypatch.delenv("BOND_SLASH_WINDOW_DOWNTIME_SECONDS", raising=False)
    monkeypatch.delenv("BOND_SLASH_WINDOW_BAD_RESULT_SECONDS", raising=False)
    assert _appeal_window_seconds(SlashingCondition.DOWNTIME) == 900
    assert _appeal_window_seconds(SlashingCondition.BAD_RESULT) == 3600
    assert _appeal_window_seconds(SlashingCondition.FRAUD) is None

    monkeypatch.setenv("BOND_SLASH_WINDOW_ENABLED", "false")
    assert _appeal_window_seconds(SlashingCondition.DOWNTIME) is None
    assert _appeal_window_seconds(SlashingCondition.BAD_RESULT) is None

    monkeypatch.setenv("BOND_SLASH_WINDOW_ENABLED", "true")
    monkeypatch.setenv("BOND_SLASH_WINDOW_DOWNTIME_SECONDS", "0")
    assert _appeal_window_seconds(SlashingCondition.DOWNTIME) == 0


# ---------------------------------------------------------------------------
# Detection: enqueue + suspension, never a chain submit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detection_enqueues_pending_and_suspends_without_chain_tx(db_session, slash_env):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        result = await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad output")

    # WIRING PIN: reverting detect() to the inline path submits a tx and this
    # assert_not_called fails.
    mock_client.assert_not_called()
    assert result["slashed"] is False
    assert result["reason"] == "slash pending appeal window"

    rows = _pending_rows(db_session)
    assert len(rows) == 1
    pending = rows[0]
    assert pending.status == PendingBondSlashStatus.PENDING.value
    assert pending.condition == "bad_result"
    assert pending.slash_amount_units == 3  # 30% of 10 AIT, snapshotted at detection
    assert pending.job_id == job.id
    assert pending.bond_id == bond.bond_id
    assert pending.provider_id == miner.id
    assert pending.window_ends_at > pending.detected_at

    db_session.refresh(bond)
    assert bond.status == ProviderBondStatus.ACTIVE.value  # status untouched
    assert suspension_event_id(bond) == pending.id
    assert (bond.meta or {}).get("suspended_by") == "bond-slash-window"
    assert is_provider_eligible(db_session, miner.id) is False


@pytest.mark.asyncio
async def test_detection_does_not_clobber_existing_suspension(db_session, slash_env):
    """An operator suspension stays owned by the operator; the pending row
    just records the live event."""
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")
    bond.meta = {
        **(bond.meta or {}),
        "suspension_event_id": "bs_operator",
        "suspended_at": "2026-01-01T00:00:00+00:00",
        "suspended_by": "admin-1",
        "suspension_reason": "operator review",
    }
    db_session.add(bond)
    db_session.commit()

    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        result = await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")

    mock_client.assert_not_called()
    assert result["reason"] == "slash pending appeal window"
    pending = _pending_rows(db_session)[0]
    assert pending.suspension_event_id == "bs_operator"
    db_session.refresh(bond)
    assert (bond.meta or {}).get("suspended_by") == "admin-1"
    assert suspension_event_id(bond) == "bs_operator"


@pytest.mark.asyncio
async def test_compound_violations_enqueue_independent_rows(db_session, slash_env):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        await BondSlashingService(db_session).slash(job, SlashingCondition.DOWNTIME, "silent")
        await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")

    mock_client.assert_not_called()
    rows = _pending_rows(db_session)
    assert len(rows) == 2
    assert {r.condition for r in rows} == {"downtime", "bad_result"}
    assert {r.slash_amount_units for r in rows} == {1, 3}
    # One shared suspension event — the first row owns it.
    assert len({r.suspension_event_id for r in rows}) == 1
    db_session.refresh(bond)
    assert suspension_event_id(bond) == rows[0].suspension_event_id


@pytest.mark.asyncio
async def test_fraud_executes_immediately_no_pending_row(db_session, slash_env):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        _wire_submit(mock_client, "0xfraud")
        result = await BondSlashingService(db_session).slash(job, SlashingCondition.FRAUD, "fraud")

    assert result["slashed"] is True
    assert _pending_rows(db_session) == []
    db_session.refresh(bond)
    assert bond.amount == Decimal("5")


@pytest.mark.asyncio
async def test_kill_switch_restores_immediate_execution(db_session, slash_env, monkeypatch):
    monkeypatch.setenv("BOND_SLASH_WINDOW_ENABLED", "false")
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    _provider_bond(db_session, miner.id, amount="10")

    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        _wire_submit(mock_client, "0xnow")
        result = await BondSlashingService(db_session).slash(job, SlashingCondition.DOWNTIME, "silent")

    assert result["slashed"] is True
    assert _pending_rows(db_session) == []


@pytest.mark.asyncio
async def test_zero_window_executes_immediately(db_session, slash_env, monkeypatch):
    monkeypatch.setenv("BOND_SLASH_WINDOW_BAD_RESULT_SECONDS", "0")
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    _provider_bond(db_session, miner.id, amount="10")

    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        _wire_submit(mock_client, "0xnow")
        result = await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")

    assert result["slashed"] is True
    assert _pending_rows(db_session) == []


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_waits_for_window_then_submits_once(db_session, slash_env):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    result = await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")
    assert result["reason"] == "slash pending appeal window"

    # Window still open: executor skips, nothing submitted, row stays pending.
    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        counts = await BondSlashingService(db_session).execute_due_pending()
        mock_client.assert_not_called()
    assert counts["executed"] == 0
    assert _pending_rows(db_session)[0].status == PendingBondSlashStatus.PENDING.value

    # Window expires: executor submits BOND_SLASH once and finalizes.
    _expire_window(db_session, _pending_rows(db_session)[0])
    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        _wire_submit(mock_client)
        counts = await BondSlashingService(db_session).execute_due_pending()
        assert counts["executed"] == 1
        assert mock_client.return_value.post.call_count == 1

    pending = _pending_rows(db_session)[0]
    assert pending.status == PendingBondSlashStatus.EXECUTED.value
    assert pending.submitted_tx_hash == "0xpending"
    db_session.refresh(bond)
    assert bond.amount == Decimal("7")
    assert bond.status == ProviderBondStatus.ACTIVE.value
    # Suspension lifted: no open pending rows remain and the suspension was
    # the detector's own.
    assert suspension_event_id(bond) is None
    assert is_provider_eligible(db_session, miner.id) is True

    # A second pass is a no-op — the row is terminal.
    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client2:
        counts = await BondSlashingService(db_session).execute_due_pending()
        assert counts["executed"] == 0
        mock_client2.assert_not_called()


@pytest.mark.asyncio
async def test_executor_keeps_suspension_until_last_compound_row(db_session, slash_env):
    """Compound violations share one suspension event: it lifts only when the
    LAST open pending row resolves."""
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    await BondSlashingService(db_session).slash(job, SlashingCondition.DOWNTIME, "silent")
    await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")
    rows = _pending_rows(db_session)
    assert len(rows) == 2

    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        _wire_submit(mock_client)
        # Expire only the downtime row (900s) — the bad_result row (3600s)
        # stays inside its window.
        downtime = next(r for r in rows if r.condition == "downtime")
        _expire_window(db_session, downtime)
        counts = await BondSlashingService(db_session).execute_due_pending()
        assert counts["executed"] == 1
        db_session.refresh(bond)
        assert suspension_event_id(bond) is not None  # bad_result row still open

        # Now expire the second: executes, suspension lifts.
        bad = next(r for r in rows if r.condition == "bad_result")
        _expire_window(db_session, bad)
        counts = await BondSlashingService(db_session).execute_due_pending()
        assert counts["executed"] == 1
        db_session.refresh(bond)
        assert suspension_event_id(bond) is None


@pytest.mark.asyncio
async def test_executor_never_lifts_operator_suspension(db_session, slash_env):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")
    bond.meta = {
        **(bond.meta or {}),
        "suspension_event_id": "bs_operator",
        "suspended_at": "2026-01-01T00:00:00+00:00",
        "suspended_by": "admin-1",
        "suspension_reason": "operator review",
    }
    db_session.add(bond)
    db_session.commit()

    await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")
    pending = _pending_rows(db_session)[0]
    _expire_window(db_session, pending)

    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        _wire_submit(mock_client)
        counts = await BondSlashingService(db_session).execute_due_pending()

    assert counts["executed"] == 1
    db_session.refresh(bond)
    assert suspension_event_id(bond) == "bs_operator"
    assert (bond.meta or {}).get("suspended_by") == "admin-1"


@pytest.mark.asyncio
async def test_executor_closes_bound_appeals_as_rejected(db_session, slash_env):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")
    pending = _pending_rows(db_session)[0]
    appeal = SlashAppeal(
        bond_id=bond.bond_id,
        provider_id=miner.id,
        slash_event_id=pending.id,
        reason="false positive",
        status=SlashAppealStatus.SUBMITTED.value,
    )
    db_session.add(appeal)
    db_session.commit()
    _expire_window(db_session, pending)

    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        _wire_submit(mock_client)
        counts = await BondSlashingService(db_session).execute_due_pending()

    assert counts["executed"] == 1
    db_session.refresh(appeal)
    assert appeal.status == SlashAppealStatus.REJECTED.value
    assert "window expired" in appeal.reviewer_notes


@pytest.mark.asyncio
async def test_executor_bounded_retry_then_failed(db_session, slash_env):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    _provider_bond(db_session, miner.id, amount="10")

    await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")
    pending = _pending_rows(db_session)[0]
    _expire_window(db_session, pending)

    from aitbc.exceptions import NetworkError

    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        client = mock_client.return_value
        client.get.side_effect = lambda url: {"transactions": []} if "/mempool" in url else {"nonce": 0}
        client.post.side_effect = NetworkError("rpc down")
        for _ in range(3):
            counts = await BondSlashingService(db_session).execute_due_pending()
        assert counts["failed"] == 1

    pending = _pending_rows(db_session)[0]
    assert pending.status == PendingBondSlashStatus.FAILED.value
    assert pending.attempts == 3
    assert "rpc down" in pending.last_error


@pytest.mark.asyncio
async def test_cas_claim_only_one_executor_submits(db_session, slash_env):
    """Two executor instances racing the same due row: the pending->executing
    CAS admits exactly one."""
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    _provider_bond(db_session, miner.id, amount="10")

    await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")
    pending = _pending_rows(db_session)[0]
    _expire_window(db_session, pending)

    svc_a = BondSlashingService(db_session)
    svc_b = BondSlashingService(db_session)
    assert svc_a._claim_pending(pending) is True
    # A second claim on the same row loses the CAS.
    fresh = db_session.get(PendingBondSlash, pending.id)
    assert svc_b._claim_pending(fresh) is False

    # And the due-row pass does not even select the claimed row.
    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        counts = await svc_b.execute_due_pending()
        mock_client.assert_not_called()
    assert counts["executed"] == 0


@pytest.mark.asyncio
async def test_stale_executing_reclaim_via_chain_point_read(db_session, slash_env, monkeypatch):
    """Crash between submit and record: the stale executing row is reconciled
    from chain state — slash landed -> EXECUTED, no resubmit."""
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")
    pending = _pending_rows(db_session)[0]
    pending.status = PendingBondSlashStatus.EXECUTING.value
    pending.claimed_at = _utcnow() - timedelta(seconds=3600)
    pending.attempts = 1
    db_session.add(pending)
    db_session.commit()

    chain_record = {
        "success": True,
        "bond_id": bond.bond_id,
        "provider": PROVIDER_WALLET,
        "amount": int(Decimal("7") * UNITS_PER_AIT),
        "status": "active",
        "slashed_tx_hash": "0xlanded",
    }
    monkeypatch.setattr(BlockchainService, "get_bond", lambda self, bond_id: chain_record)

    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        counts = await BondSlashingService(db_session).execute_due_pending()
        mock_client.assert_not_called()  # reconciled, never resubmitted

    assert counts["reconciled"] == 1
    pending = _pending_rows(db_session)[0]
    assert pending.status == PendingBondSlashStatus.EXECUTED.value
    assert pending.submitted_tx_hash == "0xlanded"
    db_session.refresh(bond)
    assert suspension_event_id(bond) is None


@pytest.mark.asyncio
async def test_stale_executing_not_landed_returns_to_pending(db_session, slash_env, monkeypatch):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    _provider_bond(db_session, miner.id, amount="10")

    await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")
    pending = _pending_rows(db_session)[0]
    pending.status = PendingBondSlashStatus.EXECUTING.value
    pending.claimed_at = _utcnow() - timedelta(seconds=3600)
    db_session.add(pending)
    db_session.commit()

    chain_record = {
        "success": True,
        "bond_id": "bond-test",
        "provider": PROVIDER_WALLET,
        "amount": int(Decimal("10") * UNITS_PER_AIT),
        "status": "active",
        "slashed_tx_hash": None,
    }
    monkeypatch.setattr(BlockchainService, "get_bond", lambda self, bond_id: chain_record)

    counts = await BondSlashingService(db_session).execute_due_pending()
    assert counts["retried"] == 1
    pending = _pending_rows(db_session)[0]
    assert pending.status == PendingBondSlashStatus.PENDING.value
    assert pending.claimed_at is None


# ---------------------------------------------------------------------------
# Appeal accept during the window — atomic cancel + suspension lift
# ---------------------------------------------------------------------------


def _chain_active_bond(bond_id: str, amount_ait: str = "10") -> dict:
    return {
        "success": True,
        "bond_id": bond_id,
        "provider": PROVIDER_WALLET,
        "amount": int(Decimal(amount_ait) * UNITS_PER_AIT),
        "status": "active",
        "slashed_tx_hash": None,
    }


def _seed_appeal(db_session, bond: ProviderBond, pending: PendingBondSlash, miner: Miner) -> SlashAppeal:
    appeal = SlashAppeal(
        bond_id=bond.bond_id,
        provider_id=miner.id,
        slash_event_id=pending.id,
        reason="false positive",
        status=SlashAppealStatus.SUBMITTED.value,
    )
    db_session.add(appeal)
    db_session.commit()
    return appeal


@pytest.mark.asyncio
async def test_accepted_appeal_cancels_pending_and_lifts_suspension_atomically(db_session, slash_env, monkeypatch):
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")
    pending = _pending_rows(db_session)[0]
    appeal = _seed_appeal(db_session, bond, pending, miner)

    monkeypatch.setattr(BlockchainService, "get_bond", lambda self, bond_id: _chain_active_bond(bond_id))
    resolved = resolve_slash_appeal(db_session, appeal.id, decision="accepted", reviewer="gov-1", notes="provider wins")
    assert resolved["status"] == "accepted"

    # WIRING PIN: reverting the pending-cancel leaves the row 'pending' and
    # the executor would still burn the bond — this assert fails.
    db_session.refresh(pending)
    assert pending.status == PendingBondSlashStatus.CANCELLED.value
    assert pending.appeal_id == appeal.id
    db_session.refresh(bond)
    assert suspension_event_id(bond) is None
    assert is_provider_eligible(db_session, miner.id) is True

    # The cancelled row is never executed.
    with patch(f"{SLASH_MODULE}.AITBCHTTPClient") as mock_client:
        counts = await BondSlashingService(db_session).execute_due_pending()
        mock_client.assert_not_called()
    assert counts["executed"] == 0


@pytest.mark.asyncio
async def test_accepted_appeal_after_window_does_not_cancel_pending(db_session, slash_env, monkeypatch):
    """Accept past window_ends_at cannot unburn: the pending row is already
    the executor's problem and stays live."""
    miner = _miner(db_session)
    job = _bonded_job(db_session)
    job.assigned_miner_id = miner.id
    db_session.add(job)
    db_session.commit()
    bond = _provider_bond(db_session, miner.id, amount="10")

    await BondSlashingService(db_session).slash(job, SlashingCondition.BAD_RESULT, "bad")
    pending = _pending_rows(db_session)[0]
    _expire_window(db_session, pending)  # window already passed
    appeal = _seed_appeal(db_session, bond, pending, miner)

    monkeypatch.setattr(BlockchainService, "get_bond", lambda self, bond_id: _chain_active_bond(bond_id))
    resolve_slash_appeal(db_session, appeal.id, decision="accepted", reviewer="gov-1", notes="late")

    db_session.refresh(pending)
    assert pending.status == PendingBondSlashStatus.PENDING.value  # NOT cancelled
    db_session.refresh(bond)
    # The accepted appeal still lifts the suspension per the existing #2966
    # rule — eligibility returns even though the slash will still execute.
    assert suspension_event_id(bond) is None
