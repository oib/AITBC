"""Regression tests for #1948 (R12-07-RESOURCE-EXHAUSTION-1).

Covers the four coordinator-api hardening fixes:

- F1: job TTL clamped to ``settings.job_ttl_seconds`` (+ schema ceiling),
  a per-client in-flight cap on non-terminal jobs, and paid-first dispatch
  ordering ahead of unpriced FIFO work.
- F2: ``MinerRegister.concurrency`` bounded by the schema and clamped
  server-side in ``MinerService.register``.
- F3: ``ExemptPrefixBodyGuardMiddleware`` rejects chunked bodies on the
  body-cap-exempt prefixes (``/v1/media/``).
- F4: ``/v1/inference/batch`` prompt length bounds and aggregate deadline.
"""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from aitbc.auth import create_access_token

from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain import Miner
from coordinator_api.contexts.infrastructure.routers import inference as inf_mod
from coordinator_api.contexts.infrastructure.services import jobs as jobs_module
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.infrastructure.services.miners import MinerService
from coordinator_api.main import ExemptPrefixBodyGuardMiddleware
from coordinator_api.schemas import JobCreate, MinerRegister


@pytest.fixture
def job_service(db_session):
    return JobService(db_session)


def _job_req(**kwargs) -> JobCreate:
    return JobCreate(payload={"type": "inference", "prompt": "x"}, **kwargs)


def _online_miner(miner_id: str = "miner-1948") -> Miner:
    return Miner(
        id=miner_id,
        concurrency=4,
        inflight=0,
        status="ONLINE",
        extra_metadata={},
        capabilities={"wallet_address": _PROVIDER},
        last_heartbeat=datetime.now(UTC),
    )


# --- F1: TTL clamp -------------------------------------------------------


def test_jobcreate_ttl_schema_bounds():
    # No upper bound at the schema: internal callers (market_gpu
    # duration-proportional TTLs up to ~8760h, services.py renders) legitimately
    # exceed any public-path ceiling — the cap is applied via ttl_cap instead.
    assert JobCreate(payload={}, ttl_seconds=86400).ttl_seconds == 86400
    assert JobCreate(payload={}, ttl_seconds=31_536_000).ttl_seconds == 31_536_000
    with pytest.raises(ValidationError):
        JobCreate(payload={}, ttl_seconds=0)


def test_create_job_ttl_clamped_only_with_cap(db_session, job_service):
    """The public submit path passes ttl_cap=settings.job_ttl_seconds;
    internal callers (paid GPU bookings, long renders) pass none and keep
    their server-computed TTL — the Validator FAIL on the first respin."""
    capped = job_service.create_job(client_id="client1", req=_job_req(ttl_seconds=900), ttl_cap=60)
    assert capped.ttl_seconds == 60
    assert (capped.expires_at - capped.requested_at).total_seconds() == pytest.approx(60)
    internal = job_service.create_job(client_id="client1", req=_job_req(ttl_seconds=900))
    assert internal.ttl_seconds == 900


def test_create_job_ttl_cap_never_below_one(db_session, job_service):
    """A degenerate cap cannot mint an already-expired job."""
    job = job_service.create_job(client_id="client1", req=_job_req(ttl_seconds=900), ttl_cap=0)
    assert job.ttl_seconds == 1


# --- F1: per-client in-flight cap ----------------------------------------


def test_inflight_cap_refuses_new_submits(db_session, job_service, monkeypatch):
    monkeypatch.setattr(jobs_module, "_MAX_INFLIGHT_JOBS_PER_CLIENT", 2)
    job_service.create_job(client_id="client1", req=_job_req(), enforce_inflight_cap=True)
    job_service.create_job(client_id="client1", req=_job_req(), enforce_inflight_cap=True)
    with pytest.raises(HTTPException) as exc_info:
        job_service.create_job(client_id="client1", req=_job_req(), enforce_inflight_cap=True)
    assert exc_info.value.status_code == 429


def test_inflight_cap_not_applied_to_internal_callers(db_session, job_service, monkeypatch):
    """#1972/#1993: market_gpu paid purchase (no job_id) still omits the flag."""
    monkeypatch.setattr(jobs_module, "_MAX_INFLIGHT_JOBS_PER_CLIENT", 1)
    job_service.create_job(client_id="client1", req=_job_req())
    job_service.create_job(client_id="client1", req=_job_req())


def test_inflight_cap_applied_to_public_service_callers(db_session, job_service, monkeypatch):
    """#1993: services.py and /market/gpu/quote pass enforce_inflight_cap=True."""
    monkeypatch.setattr(jobs_module, "_MAX_INFLIGHT_JOBS_PER_CLIENT", 1)
    job_service.create_job(client_id="client1", req=_job_req(), enforce_inflight_cap=True)
    with pytest.raises(HTTPException) as exc_info:
        job_service.create_job(client_id="client1", req=_job_req(), enforce_inflight_cap=True)
    assert exc_info.value.status_code == 429


def test_inflight_cap_is_per_client_and_terminal_jobs_free_slots(db_session, job_service, monkeypatch):
    monkeypatch.setattr(jobs_module, "_MAX_INFLIGHT_JOBS_PER_CLIENT", 1)
    first = job_service.create_job(client_id="client1", req=_job_req(), enforce_inflight_cap=True)
    # A different client is unaffected.
    job_service.create_job(client_id="client-1", req=_job_req(), enforce_inflight_cap=True)
    # Completing the job frees the slot.
    first.state = "COMPLETED"
    db_session.add(first)
    db_session.commit()
    job_service.create_job(client_id="client1", req=_job_req(), enforce_inflight_cap=True)


# --- F1: paid-first dispatch ordering ------------------------------------


_PROVIDER = "0x" + "a" * 40


def _secure_payment(db_session, job) -> JobPayment:
    """Give ``job`` a real escrowed JobPayment row (what verified payment means)."""
    payment = JobPayment(
        job_id=job.id,
        amount=Decimal("5"),
        currency="AITBC",
        payment_method="aitbc_token",
        status="escrowed",
        meta_data={"provider_address": _PROVIDER},
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    job.payment_id = payment.id
    job.payment_status = "escrowed"
    db_session.add(job)
    db_session.commit()
    return payment


def test_paid_job_dispatched_before_older_unpriced(db_session, job_service):
    miner = _online_miner()
    db_session.add(miner)
    db_session.commit()

    unpriced = job_service.create_job(client_id="client1", req=_job_req())
    priced = job_service.create_job(
        client_id="client1",
        req=_job_req(payment_amount=Decimal("5"), payment_currency="AITBC"),
    )
    _secure_payment(db_session, priced)

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == priced.id

    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == unpriced.id


def test_unfunded_priced_jobs_neither_outrank_nor_crowd_the_window(db_session, job_service, monkeypatch):
    """#1972: client-asserted payment_amount/payment_status=pending must not rank
    ahead of legitimate work, nor occupy the scan window, even when they are the
    only rows older than the legitimate job."""
    miner = _online_miner()
    db_session.add(miner)
    db_session.commit()
    monkeypatch.setattr(jobs_module.JobService, "_QUEUE_SCAN_LIMIT", 3)
    monkeypatch.setattr(jobs_module, "_PAYMENT_REQUIRE", True)
    for _ in range(5):
        job_service.create_job(client_id="client-1", req=_job_req(payment_amount=Decimal("9"), payment_currency="AITBC"))
    legit = job_service.create_job(client_id="client1", req=_job_req())
    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == legit.id


def test_unpriced_still_dispatches_when_no_paid_work(db_session, job_service):
    miner = _online_miner()
    db_session.add(miner)
    db_session.commit()
    job = job_service.create_job(client_id="client1", req=_job_req())
    acquired = job_service.acquire_next_job(miner)
    assert acquired is not None
    assert acquired.id == job.id


# --- F2: miner concurrency clamp ------------------------------------------


def test_minerregister_concurrency_schema_bounds():
    assert MinerRegister(capabilities={}, concurrency=64).concurrency == 64
    with pytest.raises(ValidationError):
        MinerRegister(capabilities={}, concurrency=65)
    with pytest.raises(ValidationError):
        MinerRegister(capabilities={}, concurrency=0)


def test_register_clamps_concurrency_server_side(db_session):
    service = MinerService(db_session)
    bypassed = MinerRegister.model_construct(capabilities={}, concurrency=500)
    miner = service.register("miner-clamp", bypassed)
    assert miner.concurrency == 64
    low = MinerRegister.model_construct(capabilities={}, concurrency=0)
    miner = service.register("miner-clamp-2", low)
    assert miner.concurrency == 1


# --- F3: exempt-prefix body guard -----------------------------------------


class _InnerApp:
    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _run_guard(app, path: str, headers: list[tuple[bytes, bytes]]):
    scope = {"type": "http", "path": path, "headers": headers}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return sent


def test_media_upload_chunked_body_rejected():
    inner = _InnerApp()
    guard = ExemptPrefixBodyGuardMiddleware(inner, ("/v1/media/",))
    sent = _run_guard(guard, "/v1/media/upload", [(b"transfer-encoding", b"chunked")])
    assert sent[0]["status"] == 411
    assert inner.called is False


def test_media_upload_content_length_passes():
    inner = _InnerApp()
    guard = ExemptPrefixBodyGuardMiddleware(inner, ("/v1/media/",))
    sent = _run_guard(guard, "/v1/media/upload", [(b"content-length", b"11")])
    assert sent[0]["status"] == 200
    assert inner.called is True


def test_non_exempt_path_untouched_by_guard():
    inner = _InnerApp()
    guard = ExemptPrefixBodyGuardMiddleware(inner, ("/v1/media/",))
    sent = _run_guard(guard, "/v1/jobs", [(b"transfer-encoding", b"chunked")])
    assert sent[0]["status"] == 200
    assert inner.called is True


# --- F4: inference batch bounds --------------------------------------------


def _inference_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u', 'client')}"}


def test_batch_rejects_oversized_prompt(client):
    resp = client.post(
        "/v1/inference/batch",
        json={"prompts": ["x" * 100_001]},
        headers=_inference_headers(),
    )
    assert resp.status_code == 422


def test_generate_rejects_oversized_prompt(client):
    resp = client.post(
        "/v1/inference/generate",
        json={"prompt": "x" * 100_001},
        headers=_inference_headers(),
    )
    assert resp.status_code == 422


def test_batch_deadline_skips_remaining_prompts(client, monkeypatch):
    monkeypatch.setattr(inf_mod, "_BATCH_DEADLINE_SECONDS", 0)

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"response": "hi"}

    class _FakeClient:
        @classmethod
        async def post(cls, url, **kw):
            return _FakeResponse()

    monkeypatch.setattr(inf_mod, "SharedHttpClient", _FakeClient)
    resp = client.post(
        "/v1/inference/batch",
        json={"prompts": ["a", "b"]},
        headers=_inference_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["completed"] == 0
    assert body["failed"] == 1
    assert "deadline" in body["errors"][0]["error"]


def test_media_upload_still_works_end_to_end(client, tmp_path, monkeypatch):
    """The guard must not break a normal Content-Length multipart upload."""
    from coordinator_api.config import settings as app_settings

    monkeypatch.setattr(app_settings, "media_storage_dir", str(tmp_path / "media"))
    token = create_access_token("client1", "client")
    resp = client.post(
        "/v1/media/upload",
        files={"file": ("t.txt", io.BytesIO(b"hello"), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
