"""#3079 (AUDIT-ZK-CIRCULAR-1): the decorative ZK gate must not carry value.

The only shipped circuit is a toy and the proof binds nothing job-specific,
yet the gate used to default ON at 10 AIT: paid jobs were accepted,
escrowed, executed, then failed ``unsupported_model`` at completion —
unreleasable by every in-code path — while the default-enabled refund
sweeper auto-refunded the buyer and ``_zk_gate_failure`` could slash the
provider's bond for the platform's own incoherence. These pins hold the
remediation: the gate is off by default, gate-failed escrows park for
operator review instead of refunding, and only provider-attributable output
failures may slash.
"""

from __future__ import annotations

import asyncio
import importlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.domain.miner import Miner
from coordinator_api.contexts.payments.services import payments as payments_module

_SLASH = "coordinator_api.contexts.market.services.bond_slashing.BondSlashingService.slash"


def _bonded_running_job(session: Session, job_id: str) -> Job:
    job = Job(
        id=job_id,
        client_id="client-1",
        state="RUNNING",
        payload={"type": "inference", "model": "linear-1"},
        constraints={"bond_required": True},
        assigned_miner_id="miner-b",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(job)
    if session.get(Miner, "miner-b") is None:
        session.add(Miner(id="miner-b", inflight=1, status="ONLINE", extra_metadata={}, capabilities={}))
    session.commit()
    return job


# ---------------------------------------------------------------------------
# 1. The gate cannot carry value by default
# ---------------------------------------------------------------------------


def test_default_threshold_is_disabled(monkeypatch) -> None:
    """With no env override the gate threshold is -1 — the codebase's disabled
    convention — in BOTH modules that read it."""
    monkeypatch.delenv("COORDINATOR_ZK_HIGH_VALUE_THRESHOLD", raising=False)
    monkeypatch.delenv("COORDINATOR_ZK_REQUIRE", raising=False)
    importlib.reload(payments_module)
    from coordinator_api.contexts.infrastructure.routers import miner as miner_module

    # miner.py binds its copy at import; reload it too so the pin reads the
    # same env-free defaults a fresh process would.
    importlib.reload(miner_module)
    try:
        assert payments_module._ZK_THRESHOLD_AIT == Decimal("-1")
        assert miner_module._ZK_THRESHOLD_AIT == Decimal("-1")
    finally:
        importlib.reload(payments_module)
        importlib.reload(miner_module)


def test_default_config_never_requires_zk_proof(monkeypatch) -> None:
    """Under the default config no job is gated by price alone, so release
    cannot be blocked by the decorative proof."""
    monkeypatch.delenv("COORDINATOR_ZK_HIGH_VALUE_THRESHOLD", raising=False)
    monkeypatch.delenv("COORDINATOR_ZK_REQUIRE", raising=False)
    reloaded = importlib.reload(payments_module)
    try:
        assert reloaded._ZK_THRESHOLD_AIT == Decimal("-1")
        assert reloaded._zk_required_for_constraints(None, Decimal("1000")) is False
    finally:
        importlib.reload(payments_module)


def test_default_threshold_still_honours_explicit_require(monkeypatch) -> None:
    """-1 disables only the *automatic* amount trigger: a buyer who explicitly
    sets zk_proof_required (or an operator who sets COORDINATOR_ZK_REQUIRE)
    still gets the gate — the documented '-1 disables the automatic
    high-value gate' contract, not a silent master-off."""
    monkeypatch.setattr(payments_module, "_ZK_THRESHOLD_AIT", Decimal("-1"))
    monkeypatch.setattr(payments_module, "_ZK_REQUIRE_PROOF", False)
    assert payments_module._zk_required_for_constraints({"zk_proof_required": True}, None) is True
    monkeypatch.setattr(payments_module, "_ZK_REQUIRE_PROOF", True)
    assert payments_module._zk_required_for_constraints(None, Decimal("1")) is True


def test_explicit_threshold_still_gates(monkeypatch) -> None:
    """An operator who deliberately configures a threshold re-enables the gate —
    the default change does not alter explicitly-configured deployments."""
    monkeypatch.setattr(payments_module, "_ZK_THRESHOLD_AIT", Decimal("10"))
    monkeypatch.setattr(payments_module, "_ZK_REQUIRE_PROOF", False)
    assert payments_module._zk_required_for_constraints(None, Decimal("15")) is True
    assert payments_module._zk_required_for_constraints(None, Decimal("5")) is False


def test_env_reload_picks_up_disabled_default(monkeypatch) -> None:
    """Reloading the module with the env var unset yields the disabled default —
    proving the '-1' is the shipped default, not a test artifact."""
    monkeypatch.delenv("COORDINATOR_ZK_HIGH_VALUE_THRESHOLD", raising=False)
    monkeypatch.delenv("COORDINATOR_ZK_REQUIRE", raising=False)
    reloaded = importlib.reload(payments_module)
    try:
        assert reloaded._ZK_THRESHOLD_AIT == Decimal("-1")
    finally:
        importlib.reload(payments_module)


# ---------------------------------------------------------------------------
# 2. Gate failure must not slash the provider for platform incoherence
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unsupported_model_gate_failure_does_not_slash(db_session) -> None:
    """``unsupported_model`` is the gate's own incoherence — no circuit exists —
    so the bonded provider's bond must survive it (#3079)."""
    from coordinator_api.contexts.infrastructure.routers.miner import _zk_gate_failure

    job = _bonded_running_job(db_session, "job-3079-noslash")
    with patch(_SLASH, new_callable=AsyncMock) as slash:
        asyncio.run(_zk_gate_failure(db_session, job, "unsupported_model"))
    slash.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.parametrize(
    "status",
    ["service_unavailable", "generation_failed", "computation_incorrect", "error: boom", "output_check_error"],
)
def test_platform_side_gate_failures_do_not_slash(db_session, status) -> None:
    """Every non-provider-attributable zk_status leaves the bond alone."""
    from coordinator_api.contexts.infrastructure.routers.miner import _zk_gate_failure

    job = _bonded_running_job(db_session, f"job-3079-{abs(hash(status)) % 10**8}")
    with patch(_SLASH, new_callable=AsyncMock) as slash:
        asyncio.run(_zk_gate_failure(db_session, job, status))
    slash.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.parametrize("status", ["output_mismatch", "output_unparseable"])
def test_provider_fault_gate_failures_still_slash(db_session, status) -> None:
    """A miner that returns the wrong (or unparseable) circuit output on a
    registered deterministic model IS provider fault — the slash stays."""
    from coordinator_api.contexts.infrastructure.routers.miner import _zk_gate_failure

    job = _bonded_running_job(db_session, f"job-3079-slash-{status}")
    with patch(_SLASH, new_callable=AsyncMock) as slash:
        asyncio.run(_zk_gate_failure(db_session, job, status))
    slash.assert_awaited_once()


# ---------------------------------------------------------------------------
# 3. The market GPU purchase path cannot reach the unsatisfiable gate
# ---------------------------------------------------------------------------


def test_gpu_purchase_refused_when_zk_gate_active(monkeypatch) -> None:
    """gpu_compute has no circuit model — under an active ZK gate the purchase
    is refused up front instead of burning the provider's rental (#3079)."""
    from coordinator_api.contexts.market.routers.market_gpu_purchase import _refuse_zk_gated_gpu_rental

    # Explicit operator opt-in (COORDINATOR_ZK_REQUIRE) gates even at the
    # disabled threshold — gpu_compute can never satisfy it, so refuse.
    monkeypatch.setattr(payments_module, "_ZK_THRESHOLD_AIT", Decimal("-1"))
    monkeypatch.setattr(payments_module, "_ZK_REQUIRE_PROOF", True)
    job = type("J", (), {"constraints": {"gpu": "H100", "region": "eu"}})()
    with pytest.raises(HTTPException) as exc:
        _refuse_zk_gated_gpu_rental(job, Decimal("50"))
    assert exc.value.status_code == 422


def test_gpu_purchase_allowed_when_gate_disabled(monkeypatch) -> None:
    """Under the default disabled gate the same purchase passes the guard."""
    from coordinator_api.contexts.market.routers.market_gpu_purchase import _refuse_zk_gated_gpu_rental

    monkeypatch.setattr(payments_module, "_ZK_THRESHOLD_AIT", Decimal("-1"))
    monkeypatch.setattr(payments_module, "_ZK_REQUIRE_PROOF", False)
    job = type("J", (), {"constraints": {"gpu": "H100", "region": "eu"}})()
    _refuse_zk_gated_gpu_rental(job, Decimal("50"))  # no raise


def test_gpu_purchase_allowed_under_threshold(monkeypatch) -> None:
    """A configured threshold above the rental price does not block it."""
    from coordinator_api.contexts.market.routers.market_gpu_purchase import _refuse_zk_gated_gpu_rental

    monkeypatch.setattr(payments_module, "_ZK_THRESHOLD_AIT", Decimal("100"))
    monkeypatch.setattr(payments_module, "_ZK_REQUIRE_PROOF", False)
    job = type("J", (), {"constraints": {"gpu": "H100", "region": "eu"}})()
    _refuse_zk_gated_gpu_rental(job, Decimal("50"))  # no raise
