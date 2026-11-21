"""#2365: provider-attested metered billing -> settlement-side partial release.

Pins the #2351 follow-up contract:

* ``POST /v1/market/jobs/{id}/billing`` stores provider-reported usage
  metrics under the server-owned ``payload.attested_billing`` key — a
  caller cannot seed that key at job creation. Reports are authorized by
  the job provider's wallet signature over the route-bound
  ``{"metrics", "final"}`` binding (#2365 respin): the buyer-issued
  access-token triple is only a secondary check, so the payer cannot
  attest the provider's usage;
* the settlement paths (``release_market_job_payment`` and the sweeper's
  ``_release_payment``) price the attested metrics against the offer's
  ``SoftwareService`` row and pass the result as ``{"amount": ...}`` to
  ``release_escrow`` — the settlement credential path, never the buyer
  relay's full-lock rule (#1912);
* no attestation (or an unpriceable one) falls back to the full-lock
  release exactly as before;
* the attested amount is clamped to the locked payment amount — a report
  can only reduce the charge, never exceed the escrow.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from market_service.domain.market import MarketJob, MarketJobPayment, SoftwareService
from market_service.services.market_job_sweeper import MarketJobSweeper
from market_service.services.market_service import MarketService
from market_service.services.market_service.billing import (
    PAYLOAD_BILLING_KEY,
    attested_release_amount,
    metered_actual_cost,
    validate_billing_metrics,
)
from market_service.storage import get_session_context
from sqlmodel import col, select

_ACCESS_KEY = "billingkey01"
_ACCESS_SECRET = "billingsecret01"

# #2365 respin: billing reports are authorized by the provider wallet
# signature, not the buyer-held access token. Seed jobs with real derived
# addresses so route tests can sign as the provider (or as the buyer, to
# prove the negative).
_PROVIDER_KEY = "0x" + "22" * 32
_BUYER_KEY = "0x" + "11" * 32
_PROVIDER_ADDRESS = None  # resolved lazily — derive needs the crypto stack
_BUYER_ADDRESS = None


def _provider_address() -> str:
    global _PROVIDER_ADDRESS
    if _PROVIDER_ADDRESS is None:
        from aitbc.crypto.crypto import derive_ethereum_address

        _PROVIDER_ADDRESS = derive_ethereum_address(_PROVIDER_KEY)
    return _PROVIDER_ADDRESS


def _buyer_address() -> str:
    global _BUYER_ADDRESS
    if _BUYER_ADDRESS is None:
        from aitbc.crypto.crypto import derive_ethereum_address

        _BUYER_ADDRESS = derive_ethereum_address(_BUYER_KEY)
    return _BUYER_ADDRESS


def _billing_body(
    job_id: str,
    metrics: dict,
    *,
    final: bool = True,
    private_key: str = _PROVIDER_KEY,
    address: str | None = None,
    binding: dict | None = None,
    chain_id: str | None = None,
    issued_at: int | None = None,
) -> dict:
    """A billing-report body signed exactly the way shop_gate signs it."""
    from aitbc.crypto.crypto import sign_transaction_data
    from aitbc.market.job_request_signature import jobs_request_message
    from aitbc.utils.chain_id import resolve_chain_id
    from market_service.config import settings

    address = address or _provider_address()
    chain_id = chain_id or settings.default_chain_id or resolve_chain_id()
    issued_at = int(time.time()) if issued_at is None else issued_at
    signed_binding = {"metrics": metrics, "final": final} if binding is None else binding
    route = f"/v1/market/jobs/{job_id}/billing"
    message = jobs_request_message(address, chain_id, issued_at, route, binding=signed_binding)
    return {
        "metrics": metrics,
        "final": final,
        "signer_address": address,
        "chain_id": chain_id,
        "issued_at": issued_at,
        "signature": sign_transaction_data(message, private_key),
    }


class _ReleaseStub:
    """Captures the release body the settlement path sends to the node."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    async def release_escrow(self, job_id: str, body: dict | None = None):
        self.calls.append((job_id, body))
        amount = (body or {}).get("amount")
        return {"success": True, "tx_hash": f"0xrelease_{job_id}", "released_amount": amount or "1.0"}


async def _seed_job(
    *,
    service_type: str = "ollama",
    model: str = "llama3",
    price: str = "0.0073",
    price_unit: str = "per_1k_tokens",
    offer_id: str | None = None,
    with_service: bool = True,
    payment_amount: str = "1.0",
    state: str = "RUNNING",
) -> tuple[str, MarketService]:
    """A metered job with an escrowed payment and a priced SoftwareService."""
    job_id = f"job-billing-{uuid4().hex[:12]}"
    offer_id = offer_id or f"offer-{job_id}"
    async with get_session_context() as session:
        svc = MarketService(session)
        if with_service:
            svc.session.add(
                SoftwareService(
                    service_type=service_type,
                    model=model,
                    price=Decimal(price),
                    price_unit=price_unit,
                    offer_id=offer_id,
                )
            )
        payload = {"access_key": _ACCESS_KEY, "access_secret": _ACCESS_SECRET}
        created = await svc.create_market_job(
            {
                "id": job_id,
                "service_type": service_type,
                "model": model,
                "offer_id": offer_id,
                "plugin_id": f"{service_type}-{model}",
                "buyer_address": _buyer_address(),
                "provider_address": _provider_address(),
                "payload": payload,
                "payment": {"amount": payment_amount, "status": "escrowed"},
            }
        )
        assert created["job_id"] == job_id
        # Drive the escrowed lifecycle the way settlement leaves it.
        job = await svc.session.get(MarketJob, job_id)
        assert job is not None
        job.state = state
        job.payment_status = "escrowed"
        payment = await svc.session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        payment.status = "escrowed"
        payment.escrowed_at = datetime.now(UTC).replace(tzinfo=None)
        payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
        svc.session.add_all([job, payment])
        await svc.session.commit()
    return job_id, svc


async def _fetch(job_id: str) -> dict:
    async with get_session_context() as session:
        return await MarketService(session).get_market_job(job_id)


async def _payment_of(job_id: str) -> MarketJobPayment:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None and job.payment_id
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        return payment


async def _record(job_id: str, metrics: dict, *, final: bool = True) -> dict:
    async with get_session_context() as session:
        return await MarketService(session).record_job_billing(job_id, metrics, final=final)


# ---------------------------------------------------------------------------
# validate_billing_metrics / metered_actual_cost — pure functions
# ---------------------------------------------------------------------------


def test_validate_billing_metrics_accepts_numbers() -> None:
    out = validate_billing_metrics({"eval_count": 123, "duration_minutes": "4.5", "ratio": 0.25})
    assert out == {"eval_count": Decimal("123"), "duration_minutes": Decimal("4.5"), "ratio": Decimal("0.25")}


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        [],
        {"eval_count": -1},
        {"eval_count": "NaN"},
        {"eval_count": "Infinity"},
        {"eval_count": True},
        {"eval_count": "not-a-number"},
        {"bad name!": 1},
        {"eval_count": 10**30},
    ],
)
def test_validate_billing_metrics_rejects_garbage(raw) -> None:
    with pytest.raises(ValueError):
        validate_billing_metrics(raw)


def test_validate_billing_metrics_bounds_count() -> None:
    with pytest.raises(ValueError):
        validate_billing_metrics({f"m{i}": 1 for i in range(40)})


def test_metered_actual_cost_formulas() -> None:
    price = Decimal("0.0073")
    assert metered_actual_cost("ollama", "per_1k_tokens", price, {"eval_count": 2000}) == price * 2
    assert metered_actual_cost("cloud_ollama", "per_1k_tokens", price, {"eval_count": 1000}) == price
    assert metered_actual_cost("whisper", "per_audio_min", Decimal("0.01"), {"duration_minutes": 5}) == Decimal("0.05")
    assert metered_actual_cost("whisper", "flat", Decimal("0.01"), {"duration_minutes": 5}) == Decimal("0.01")
    assert metered_actual_cost("ffmpeg", "per_processing_hour", Decimal("0.02"), {"processing_time_hours": 2}) == Decimal(
        "0.04"
    )
    assert metered_actual_cost("hermes", "per_minute", Decimal("0.01"), {"duration_minutes": 10}) == Decimal("0.1")
    assert metered_actual_cost("hermes", "per_processing_hour", Decimal("0.6"), {"duration_minutes": 30}) == Decimal("0.3")
    assert metered_actual_cost("ipfs", "per_day", Decimal("0.5"), {"duration_minutes": 10}) is None
    assert metered_actual_cost("ollama", "per_1k_tokens", price, {"other": 1}) is None


# ---------------------------------------------------------------------------
# record_job_billing — storage + state rules
# ---------------------------------------------------------------------------


async def test_record_job_billing_stores_metrics_and_completes() -> None:
    job_id, _ = await _seed_job()
    out = await _record(job_id, {"eval_count": Decimal("1234")}, final=True)
    assert out["accepted"] is True
    assert out["state"] == "COMPLETED"

    fetched = await _fetch(job_id)
    assert fetched["state"] == "COMPLETED"
    billing = fetched["payload"][PAYLOAD_BILLING_KEY]
    assert billing["metrics"] == {"eval_count": "1234"}
    assert billing["final"] is True


async def test_record_job_billing_merges_and_rejects_terminal_state() -> None:
    job_id, _ = await _seed_job(service_type="whisper", price_unit="per_audio_min", price="0.01")
    await _record(job_id, {"duration_minutes": Decimal("2")}, final=False)
    await _record(job_id, {"extra": Decimal("1")}, final=False)
    fetched = await _fetch(job_id)
    metrics = fetched["payload"][PAYLOAD_BILLING_KEY]["metrics"]
    assert metrics == {"duration_minutes": "2", "extra": "1"}
    assert fetched["state"] == "RUNNING"  # non-final report does not complete

    # Terminal states refuse further reports.
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        job.state = "CANCELED"
        session.add(job)
        await session.commit()
    async with get_session_context() as session:
        with pytest.raises(ValueError, match="does not accept billing reports"):
            await MarketService(session).record_job_billing(job_id, {"eval_count": Decimal("1")}, final=True)


async def test_buyer_cannot_seed_attested_billing_at_creation() -> None:
    """``attested_billing`` is a server-owned payload key (#2365)."""
    async with get_session_context() as session:
        svc = MarketService(session)
        created = await svc.create_market_job(
            {
                "id": f"job-seed-{uuid4().hex[:12]}",
                "service_type": "ollama",
                "buyer_address": _buyer_address(),
                "provider_address": _provider_address(),
                "payload": {
                    "access_key": _ACCESS_KEY,
                    "access_secret": _ACCESS_SECRET,
                    PAYLOAD_BILLING_KEY: {"metrics": {"eval_count": "1"}},
                },
                "payment": {"amount": "1.0"},
            }
        )
    fetched = await _fetch(created["job_id"])
    assert PAYLOAD_BILLING_KEY not in (fetched["payload"] or {})


# ---------------------------------------------------------------------------
# attested_release_amount — pricing + clamp + fallbacks
# ---------------------------------------------------------------------------


async def test_attested_release_amount_prices_metrics() -> None:
    job_id, _ = await _seed_job(price="0.0073", payment_amount="1.0")
    await _record(job_id, {"eval_count": Decimal("2000")}, final=True)
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert job is not None and payment is not None
        # 2000 tokens at 0.0073 AIT/1k = 0.0146 AIT.
        assert await attested_release_amount(session, job, payment) == Decimal("0.0146")


async def test_attested_release_amount_clamps_to_locked_amount() -> None:
    job_id, _ = await _seed_job(price="0.0073", payment_amount="1.0")
    await _record(job_id, {"eval_count": Decimal("999999999")}, final=True)
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert job is not None and payment is not None
        billed = await attested_release_amount(session, job, payment)
        assert billed == payment.amount


async def test_attested_release_amount_none_without_attestation() -> None:
    job_id, _ = await _seed_job()
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert job is not None and payment is not None
        assert await attested_release_amount(session, job, payment) is None


async def test_attested_release_amount_none_when_service_row_missing() -> None:
    # create_market_job validates offer_id against SoftwareService, so seed
    # the row then delete it — the pricing lookup must fail closed to full
    # lock. whisper + duration_minutes is a priceable metric, so None can
    # only come from the missing service row.
    job_id, _ = await _seed_job(
        service_type="whisper",
        model="whisper-1",
        price_unit="per_audio_min",
        price="0.01",
        offer_id="offer-billing-missing",
    )
    async with get_session_context() as session:
        rows = (
            (await session.execute(select(SoftwareService).where(col(SoftwareService.offer_id) == "offer-billing-missing")))
            .scalars()
            .all()
        )
        for row in rows:
            await session.delete(row)
        await session.commit()
    await _record(job_id, {"duration_minutes": Decimal("5")}, final=True)
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert job is not None and payment is not None
        assert await attested_release_amount(session, job, payment) is None


async def test_attested_release_amount_none_for_unpriceable_metrics() -> None:
    job_id, _ = await _seed_job(service_type="ollama")
    # A whisper-style metric on an ollama job cannot be priced.
    await _record(job_id, {"duration_minutes": Decimal("5")}, final=True)
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert job is not None and payment is not None
        assert await attested_release_amount(session, job, payment) is None


# ---------------------------------------------------------------------------
# Settlement paths — release_escrow body carries the attested amount
# ---------------------------------------------------------------------------


async def test_release_market_job_payment_sends_attested_amount() -> None:
    job_id, _ = await _seed_job(price="0.0073", payment_amount="1.0")
    await _record(job_id, {"eval_count": Decimal("2000")}, final=True)
    async with get_session_context() as session:
        svc = MarketService(session)
        rpc = _ReleaseStub()
        svc._rpc_client = rpc  # type: ignore[assignment]
        out = await svc.release_market_job_payment(job_id)
    assert out["state"] == "RELEASED"
    assert len(rpc.calls) == 1 and rpc.calls[0][0] == job_id
    assert Decimal(str(rpc.calls[0][1]["amount"])) == Decimal("0.0146")
    payment = await _payment_of(job_id)
    assert payment.status == "released"
    assert payment.released_amount == Decimal("0.0146")


async def test_release_market_job_payment_full_lock_without_attestation() -> None:
    # COMPLETED, not RUNNING: the #1922 fail-closed gate refuses a RUNNING
    # job with no provider pin attestation — the state a metered job only
    # reaches through the billing report's final flag.
    job_id, _ = await _seed_job(state="COMPLETED")
    async with get_session_context() as session:
        svc = MarketService(session)
        rpc = _ReleaseStub()
        svc._rpc_client = rpc  # type: ignore[assignment]
        await svc.release_market_job_payment(job_id)
    # No attested billing -> body is None -> the node bills the whole lock.
    assert rpc.calls == [(job_id, None)]


async def _age_for_sweep(job_id: str) -> None:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        job.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        job.updated_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        session.add(job)
        await session.commit()


async def test_sweeper_release_sends_attested_amount() -> None:
    job_id, _ = await _seed_job(price="0.0073", payment_amount="1.0")
    await _record(job_id, {"eval_count": Decimal("2000")}, final=True)
    await _age_for_sweep(job_id)

    rpc = _ReleaseStub()
    sw = MarketJobSweeper(rpc_client=rpc, session_factory=lambda: get_session_context())
    await sw.sweep_once()
    call = next(c for c in rpc.calls if c[0] == job_id)
    assert Decimal(str(call[1]["amount"])) == Decimal("0.0146")
    payment = await _payment_of(job_id)
    assert payment.status == "released"
    assert payment.released_amount == Decimal("0.0146")


async def test_sweeper_release_full_lock_without_attestation() -> None:
    job_id, _ = await _seed_job(state="COMPLETED")
    await _age_for_sweep(job_id)

    rpc = _ReleaseStub()
    sw = MarketJobSweeper(rpc_client=rpc, session_factory=lambda: get_session_context())
    await sw.sweep_once()
    assert (job_id, None) in rpc.calls
    payment = await _payment_of(job_id)
    assert payment.status == "released"


# ---------------------------------------------------------------------------
# Route — credential binding
# ---------------------------------------------------------------------------


async def test_billing_route_requires_access_triple() -> None:
    job_id, _ = await _seed_job()
    from market_service.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(f"/v1/market/jobs/{job_id}/billing", json={"metrics": {"eval_count": 1}})
    assert resp.status_code == 401

    resp = client.post(
        f"/v1/market/jobs/{job_id}/billing",
        json={"metrics": {"eval_count": 1}},
        headers={"X-Access-Key": _ACCESS_KEY, "X-Access-Secret": "wrong", "X-Job-Id": job_id},
    )
    assert resp.status_code == 403

    resp = client.post(
        f"/v1/market/jobs/{job_id}/billing",
        json={"metrics": {"eval_count": 1}},
        headers={"X-Access-Key": _ACCESS_KEY, "X-Access-Secret": _ACCESS_SECRET, "X-Job-Id": "other-job"},
    )
    assert resp.status_code == 403


def _billing_headers(job_id: str) -> dict[str, str]:
    return {"X-Access-Key": _ACCESS_KEY, "X-Access-Secret": _ACCESS_SECRET, "X-Job-Id": job_id}


async def test_billing_route_accepts_valid_report() -> None:
    job_id, _ = await _seed_job()
    from market_service.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/v1/market/jobs/{job_id}/billing",
        json=_billing_body(job_id, {"eval_count": 4321}, final=True),
        headers=_billing_headers(job_id),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["accepted"] is True
    fetched = await _fetch(job_id)
    assert fetched["payload"][PAYLOAD_BILLING_KEY]["metrics"] == {"eval_count": "4321"}
    assert fetched["state"] == "COMPLETED"


async def test_billing_route_rejects_unsigned_report() -> None:
    """#2365 respin: the buyer-held access token alone cannot attest usage —
    a report with valid credentials but no provider signature is refused."""
    job_id, _ = await _seed_job()
    from market_service.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/v1/market/jobs/{job_id}/billing",
        json={"metrics": {"eval_count": 1}, "final": True},
        headers=_billing_headers(job_id),
    )
    assert resp.status_code == 403


async def test_billing_route_rejects_buyer_signed_report() -> None:
    """The exploit the respin closes: the buyer signs the under-billing
    report with its own wallet — valid signature, wrong party -> 403."""
    job_id, _ = await _seed_job()
    from market_service.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/v1/market/jobs/{job_id}/billing",
        json=_billing_body(
            job_id,
            {"eval_count": 1},
            final=True,
            private_key=_BUYER_KEY,
            address=_buyer_address(),
        ),
        headers=_billing_headers(job_id),
    )
    assert resp.status_code == 403
    fetched = await _fetch(job_id)
    assert PAYLOAD_BILLING_KEY not in (fetched["payload"] or {})
    assert fetched["state"] == "RUNNING"


async def test_billing_route_rejects_tampered_metrics() -> None:
    """A signature over different metrics cannot be re-pointed at new values."""
    job_id, _ = await _seed_job()
    from market_service.main import app

    client = TestClient(app, raise_server_exceptions=False)
    body = _billing_body(job_id, {"eval_count": 999999}, final=True)
    body["metrics"] = {"eval_count": 1}  # swap after signing
    resp = client.post(f"/v1/market/jobs/{job_id}/billing", json=body, headers=_billing_headers(job_id))
    assert resp.status_code == 403


async def test_billing_route_rejects_bad_metrics() -> None:
    job_id, _ = await _seed_job()
    from market_service.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/v1/market/jobs/{job_id}/billing",
        json=_billing_body(job_id, {"eval_count": -5}),
        headers=_billing_headers(job_id),
    )
    assert resp.status_code == 400


async def test_billing_route_404_for_unknown_job() -> None:
    from market_service.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/v1/market/jobs/no-such-job/billing",
        json={"metrics": {"eval_count": 1}},
        headers={"X-Access-Key": _ACCESS_KEY, "X-Access-Secret": _ACCESS_SECRET, "X-Job-Id": "no-such-job"},
    )
    assert resp.status_code == 404
