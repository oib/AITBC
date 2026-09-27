"""Regression tests for the coordinator-api write-authorisation hardening.

Covers the four findings from the payment/settlement/reputation review:

* method-aware ``get_auth_level`` — ``/v1/reputation*`` is public for reads but
  writes hit the ``ROUTE_WRITE_FLOORS`` floor instead of staying ``NONE``;
* ``PaymentService.refund_payment`` — a client's refund window ends at
  delivery; ``pending_acceptance``/``disputed``/``settlement_failed`` are
  admin-only, so a client can no longer collect the result and refund escrow;
* ``JobService.fail_job`` / ``submit_result`` — only the assigned miner may
  write to a job, and only while it is running; the caller can no longer
  overwrite ``assigned_miner_id``;
* ``complete_job`` — the URL ``miner_id`` must be the authenticated miner.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from aitbc.auth.security_matrix import AuthLevel, get_auth_level
from aitbc_shared import JobPayment, PaymentEscrow

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.main import app


# --------------------------------------------------------------------------
# Route matrix: method-aware lookups
# --------------------------------------------------------------------------


@pytest.mark.unit
class TestReputationWriteFloor:
    """/v1/reputation* is NONE for reads but must not open writes."""

    def test_reads_stay_public(self):
        for path in (
            "/v1/reputation/profile/abc",
            "/v1/reputation/trust-score/abc",
            "/v1/reputation/leaderboard",
        ):
            assert get_auth_level(path, "GET") is AuthLevel.NONE, path
            assert get_auth_level(path, "HEAD") is AuthLevel.NONE, path

    def test_writes_hit_the_floor(self):
        for method, path in (
            ("POST", "/v1/reputation/profile/abc"),
            ("POST", "/v1/reputation/feedback/abc"),
            ("PUT", "/v1/reputation/profile/abc/specialization"),
            ("PUT", "/v1/reputation/profile/abc/region"),
            ("POST", "/v1/reputation/abc/cross-chain/sync"),
            ("POST", "/v1/reputation/cross-chain/events"),
        ):
            assert get_auth_level(path, method) is AuthLevel.ANY, (method, path)

    def test_unregistered_still_denied(self):
        assert get_auth_level("/v1/definitely-not-a-route", "GET") is AuthLevel.DENY
        assert get_auth_level("/v1/definitely-not-a-route", "POST") is AuthLevel.DENY

    def test_floors_apply_only_to_listed_patterns(self):
        """A NONE wildcard with no floor keeps resolving writes to NONE at
        matrix level — the served-write invariant below guards those."""
        assert get_auth_level("/v1/explorer/anything", "POST") is AuthLevel.NONE


def _write_routes() -> dict[str, set[str]]:
    """Served paths -> write methods, for routes published by the app."""
    routes: dict[str, set[str]] = {}
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        writes = methods - {"GET", "HEAD", "OPTIONS"}
        if writes:
            routes.setdefault(route.path, set()).update(writes)
    return routes


# Public-by-design write endpoints: signup and login cannot require auth, and
# the GPU quote route writes an unsigned quote + bound job before the buyer has
# funded anything (purchase happens on a later, authenticated call).
PUBLIC_WRITES: set[str] = {
    "/v1/register",
    "/v1/login",
    "/v1/auth/nonce",
    "/v1/market/gpu/quote",
}


@pytest.mark.unit
def test_no_served_write_route_is_matrix_public():
    """Every served write route must resolve above NONE (or be allow-listed).

    A NONE wildcard used to open writes along with reads — that is how
    /v1/reputation* exposed every mutation on the router. This fails if a new
    write route ever resolves to NONE without being deliberately allow-listed.
    """
    violations = {
        f"{method} {path}"
        for path, methods in _write_routes().items()
        for method in methods
        if get_auth_level(path, method) is AuthLevel.NONE and path not in PUBLIC_WRITES
    }
    assert not violations, f"write routes reachable at AuthLevel.NONE: {sorted(violations)}"


# --------------------------------------------------------------------------
# Refund gate: client window ends at delivery
# --------------------------------------------------------------------------


def _make_escrowed(
    session: Session,
    job_id: str,
    payment_id: str,
    *,
    job_state: str = "QUEUED",
    payment_status: str = "escrowed",
    client_id: str = "client-1",
    with_result: bool = False,
) -> None:
    job = Job(
        id=job_id,
        client_id=client_id,
        state=job_state,
        payload={},
        payment_id=payment_id,
        payment_status=payment_status,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        result={"output": "delivered"} if with_result else None,
    )
    payment = JobPayment(
        id=payment_id,
        job_id=job_id,
        client_id=client_id,
        amount=5,
        currency="AITBC",
        status=payment_status,
        payment_method="aitbc_token",
        escrow_address="escrow_abc123",
        escrowed_at=datetime.now(UTC),
    )
    escrow = PaymentEscrow(
        payment_id=payment_id,
        amount=5,
        currency="AITBC",
        address="escrow_address_for_payment",
        is_active=True,
        is_released=False,
        is_refunded=False,
    )
    session.add(job)
    session.add(payment)
    session.add(escrow)
    session.commit()


@pytest.fixture
def funded_chain():
    """Escrow reports funded; refund posts succeed."""
    with patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient") as cls:
        client = AsyncMock()
        client.get.return_value = {"state": "funded"}
        client.post.return_value = {"success": True, "refund_tx_hash": "0xrefundtx"}
        cls.return_value = client
        yield client


@pytest.mark.unit
class TestRefundAuthorization:
    def test_client_refunds_undelivered_escrow(self, db_session, funded_chain):
        _make_escrowed(db_session, "job-r1", "pay-r1", job_state="QUEUED")
        result = asyncio.run(PaymentService(db_session).refund_payment("client-1", "job-r1", "pay-r1", "changed mind"))
        assert result is True
        assert db_session.get(JobPayment, "pay-r1").status == "refunded"

    def test_client_cannot_refund_after_delivery(self, db_session, funded_chain):
        """Escrowed but the job is done: refunding now keeps the work AND the money."""
        _make_escrowed(db_session, "job-r2", "pay-r2", job_state="COMPLETED", with_result=True)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(PaymentService(db_session).refund_payment("client-1", "job-r2", "pay-r2", "gimme"))
        assert exc.value.status_code == 403
        funded_chain.post.assert_not_called()
        assert db_session.get(JobPayment, "pay-r2").status == "escrowed"

    @pytest.mark.parametrize("status_", ["pending_acceptance", "disputed", "settlement_failed"])
    def test_client_cannot_refund_held_or_failed_states(self, db_session, funded_chain, status_):
        _make_escrowed(db_session, f"job-{status_}", f"pay-{status_}", job_state="COMPLETED", payment_status=status_)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(PaymentService(db_session).refund_payment("client-1", f"job-{status_}", f"pay-{status_}", "refund me"))
        assert exc.value.status_code == 403
        funded_chain.post.assert_not_called()

    def test_admin_can_refund_pending_acceptance(self, db_session, funded_chain):
        _make_escrowed(db_session, "job-admin", "pay-admin", job_state="COMPLETED", payment_status="pending_acceptance")
        result = asyncio.run(
            PaymentService(db_session).refund_payment(
                "ignored-admin-client", "job-admin", "pay-admin", "arbiter decision", is_admin=True
            )
        )
        assert result is True
        funded_chain.post.assert_called_once()

    def test_cross_client_refund_still_rejected(self, db_session, funded_chain):
        _make_escrowed(db_session, "job-r3", "pay-r3", job_state="QUEUED")
        with pytest.raises(HTTPException):
            asyncio.run(PaymentService(db_session).refund_payment("client-unknown", "job-r3", "pay-r3", "x"))
        funded_chain.post.assert_not_called()

    def test_refunded_row_reconcile_not_blocked(self, db_session):
        """An already-refunded row reconciles (fixes cache / returns chain hash)
        regardless of delivery state — the gate must not block the no-op path."""
        _make_escrowed(db_session, "job-r4", "pay-r4", job_state="COMPLETED", payment_status="refunded", with_result=True)
        with patch("coordinator_api.contexts.payments.services.payments.AsyncAITBCHTTPClient") as cls:
            client = AsyncMock()
            client.get.return_value = {"state": "refunded", "refund_tx_hash": "0xstale"}
            client.get_json.return_value = [
                {"tx_hash": "0xrealrefund", "payload": {"job_id": "job-r4", "action": "escrow_refund"}}
            ]
            cls.return_value = client
            result = asyncio.run(PaymentService(db_session).refund_payment("client-1", "job-r4", "pay-r4", "x"))
        assert result is True


# --------------------------------------------------------------------------
# Miner assignment: fail_job service checks
# --------------------------------------------------------------------------


def _make_running_job(session: Session, job_id: str, miner_id: str, *, state: str = "RUNNING") -> Job:
    job = Job(
        id=job_id,
        client_id="client-1",
        state=state,
        payload={},
        assigned_miner_id=miner_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(job)
    session.commit()
    return job


@pytest.mark.unit
class TestFailJobAssignment:
    def test_assigned_miner_fails_running_job(self, db_session):
        _make_running_job(db_session, "job-f1", "miner-a")
        job = JobService(db_session).fail_job("job-f1", "miner-a", "gpu blew up")
        assert job.state == "FAILED"
        assert job.error == "gpu blew up"

    def test_wrong_miner_cannot_fail_job(self, db_session):
        _make_running_job(db_session, "job-f2", "miner-a")
        with pytest.raises(HTTPException) as exc:
            JobService(db_session).fail_job("job-f2", "miner-b", "sabotage")
        assert exc.value.status_code == 403

    def test_failure_cannot_reassign_job(self, db_session):
        """The old code overwrote assigned_miner_id with the caller's id."""
        _make_running_job(db_session, "job-f3", "miner-a")
        with pytest.raises(HTTPException):
            JobService(db_session).fail_job("job-f3", "miner-b", "sabotage")
        assert db_session.get(Job, "job-f3").assigned_miner_id == "miner-a"

    def test_non_running_job_cannot_be_failed(self, db_session):
        _make_running_job(db_session, "job-f4", "miner-a", state="QUEUED")
        with pytest.raises(HTTPException) as exc:
            JobService(db_session).fail_job("job-f4", "miner-a", "too late")
        assert exc.value.status_code == 409
        assert db_session.get(Job, "job-f4").state == "QUEUED"


# --------------------------------------------------------------------------
# Route level: submit_result / complete_job reject the wrong miner
# --------------------------------------------------------------------------


@pytest.fixture
def miner_client(db_session):
    """TestClient with an overridden miner identity and the in-memory DB."""
    from fastapi.testclient import TestClient

    from aitbc.auth.dependencies import require_miner
    from coordinator_api.storage import get_session

    caller = {"sub": "miner-b", "role": "miner"}

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_miner] = lambda: caller
    yield TestClient(app), caller
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(require_miner, None)


@pytest.mark.unit
class TestMinerRouteAssignment:
    def test_submit_result_rejects_wrong_miner(self, miner_client, db_session):
        client, _ = miner_client
        _make_running_job(db_session, "job-sr1", "miner-a")
        resp = client.post("/v1/miners/job-sr1/result", json={"result": {"output": "junk"}})
        assert resp.status_code == 403
        assert db_session.get(Job, "job-sr1").state == "RUNNING"

    def test_submit_result_rejects_non_running_job(self, miner_client, db_session):
        client, _ = miner_client
        _make_running_job(db_session, "job-sr2", "miner-b", state="COMPLETED")
        resp = client.post("/v1/miners/job-sr2/result", json={"result": {"output": "junk"}})
        assert resp.status_code == 409

    def test_complete_job_rejects_url_miner_mismatch(self, miner_client, db_session):
        """URL miner_id 'miner-a' vs authenticated 'miner-b' — rejected before touching the job."""
        client, _ = miner_client
        _make_running_job(db_session, "job-cj1", "miner-a")
        resp = client.post(
            "/v1/miners/miner-a/jobs/job-cj1/complete",
            json={"output": {"x": 1}, "receipt": {"price": "999"}},
        )
        assert resp.status_code == 403

    def test_complete_job_rejects_wrong_assignee(self, miner_client, db_session):
        """URL matches the caller, but the job belongs to another miner."""
        client, _ = miner_client
        _make_running_job(db_session, "job-cj2", "miner-a")
        resp = client.post(
            "/v1/miners/miner-b/jobs/job-cj2/complete",
            json={"output": {"x": 1}, "receipt": {"price": "999"}},
        )
        assert resp.status_code == 403
        assert db_session.get(Job, "job-cj2").state == "RUNNING"

    def test_fail_route_rejects_url_miner_mismatch(self, miner_client, db_session):
        client, _ = miner_client
        _make_running_job(db_session, "job-fl1", "miner-a")
        resp = client.post("/v1/miners/miner-a/jobs/job-fl1/fail", json={"error_code": "ERR", "error_message": "x"})
        assert resp.status_code == 403

    def test_submit_failure_rejects_wrong_assignee(self, miner_client, db_session):
        """POST /miners/{job_id}/fail — service-level assignment check fires."""
        client, _ = miner_client
        _make_running_job(db_session, "job-fl2", "miner-a")
        resp = client.post("/v1/miners/job-fl2/fail", json={"error_code": "ERR", "error_message": "sabotage"})
        assert resp.status_code == 403
        job = db_session.get(Job, "job-fl2")
        assert job.state == "RUNNING"
        assert job.assigned_miner_id == "miner-a"
