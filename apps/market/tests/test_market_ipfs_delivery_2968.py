"""#2968 market-side delivery rescue endpoints.

The direct buyer→provider bitswap leg is unreliable across island IPFS
swarms. These pins cover the provider-signed hub CAR export proxy and the
signed persistent-delivery-error write: both are route- and CID-bound, both
resolve the provider from the service row rather than the caller-writable
job row, and neither leaks rental bytes or credential material to anyone
else.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_data
from aitbc.market.job_request_signature import jobs_request_message
from aitbc.utils.chain_id import resolve_chain_id
from market_service.config import settings
from market_service.main import app
from market_service.domain.market import MarketJob, MarketJobPayment, SoftwareService
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

_PROVIDER_KEY = "0x" + "46" * 32
_BUYER_KEY = "0x" + "57" * 32
_INTRUDER_KEY = "0x" + "68" * 32
_PROVIDER = derive_ethereum_address(_PROVIDER_KEY)
_BUYER = derive_ethereum_address(_BUYER_KEY)
_INTRUDER = derive_ethereum_address(_INTRUDER_KEY)
_CID = "QmR4aYSmdvQvUAnrPGvPsDB7FrJU4ZpfpP4mGuzn5SFRTa"


def _address(private_key: str) -> str:
    return derive_ethereum_address(private_key)


def _signed(address: str, private_key: str, route: str, binding: dict[str, Any]) -> dict[str, Any]:
    issued_at = int(time.time())
    chain_id = settings.default_chain_id or resolve_chain_id()
    signature = sign_transaction_data(jobs_request_message(address, chain_id, issued_at, route, binding=binding), private_key)
    return {
        "signer_address": address,
        "chain_id": chain_id,
        "issued_at": issued_at,
        "signature": signature,
    }


async def _seed_job_async(caller_quota_mb: int = 1) -> str:
    suffix = time.time_ns()
    offer_id = f"offer-ipfs-delivery-{suffix}"
    access_key = f"ak-ipfs-delivery-{suffix}"

    async def _create() -> str:
        async with get_session_context() as session:
            session.add(
                SoftwareService(
                    service_type="ipfs",
                    offer_id=offer_id,
                    provider_address=_PROVIDER,
                    disk_quota_mb=1,
                )
            )
            svc = MarketService(session)
            created = await svc.create_market_job(
                {
                    "service_type": "ipfs",
                    "buyer_address": _BUYER,
                    "provider_address": _PROVIDER,
                    "offer_id": offer_id,
                    "constraints": {"disk_quota_mb": caller_quota_mb},
                    "payload": {"cid": _CID, "access_key": access_key, "access_secret": "rental-secret"},
                    "payment": {"amount": "1.0"},
                }
            )
            job_id = created["job_id"]
            job = await session.get(MarketJob, job_id)
            assert job is not None and job.payment_id
            payment = await session.get(MarketJobPayment, job.payment_id)
            assert payment is not None
            payment.status = "escrowed"
            session.add_all([job, payment])
            await session.commit()
            return job_id

    return await _create()


def _seed_job() -> str:
    return asyncio.run(_seed_job_async())


async def _mark_job_terminal(job_id: str) -> None:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        job.state = "FAILED"
        session.add(job)
        await session.commit()


async def _payload(job_id: str) -> dict[str, Any]:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        return dict(job.payload or {})


async def _payment_status(job_id: str) -> str | None:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None and job.payment_id
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        return payment.status


def _response(*, text: str = "", chunks: list[bytes] | None = None, status: int = 200) -> Mock:
    response = Mock()
    response.status_code = status
    response.text = text
    response.iter_content = lambda *a, **k: iter(chunks or [])
    response.close = Mock()
    return response


@pytest.fixture(autouse=True)
def _rate_limiting_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_content_car_streams_only_for_signed_provider(client: TestClient) -> None:
    job_id = _seed_job()
    route = f"/v1/market/jobs/{job_id}/content-car"
    signed = _signed(_PROVIDER, _PROVIDER_KEY, route, {"cid": _CID})
    upstream_calls: list[str] = []

    def fake_post(url: str, **kwargs: Any) -> Mock:
        upstream_calls.append(url)
        if url.endswith("/api/v0/dag/stat"):
            return _response(text='{"TotalSize": 128}\n')
        if url.endswith("/api/v0/dag/export"):
            return _response(chunks=[b"car-", b"bytes"])
        raise AssertionError(f"unexpected upstream call: {url}")

    with patch("market_service.routers.jobs.requests.post", side_effect=fake_post):
        response = client.get(route, params=signed)

    assert response.status_code == 200
    assert response.content == b"car-bytes"
    assert response.headers["content-type"].startswith("application/vnd.ipld.car")
    assert upstream_calls[0].endswith("/api/v0/dag/stat")
    assert upstream_calls[1].endswith("/api/v0/dag/export")


@pytest.mark.parametrize(
    ("private_key", "claimed"),
    [
        (_BUYER_KEY, _BUYER),
        (_INTRUDER_KEY, _INTRUDER),
    ],
)
def test_content_car_rejects_buyer_and_intruder(client: TestClient, private_key: str, claimed: str) -> None:
    job_id = _seed_job()
    route = f"/v1/market/jobs/{job_id}/content-car"
    signed = _signed(claimed, private_key, route, {"cid": _CID})
    with patch("market_service.routers.jobs.requests.post") as upstream:
        response = client.get(route, params=signed)
    assert response.status_code == 403
    upstream.assert_not_called()


def test_content_car_rejects_cid_tampering(client: TestClient) -> None:
    job_id = _seed_job()
    route = f"/v1/market/jobs/{job_id}/content-car"
    # Valid signature, but over a different CID than the authoritative job row.
    signed = _signed(_PROVIDER, _PROVIDER_KEY, route, {"cid": "QmWrong"})
    with patch("market_service.routers.jobs.requests.post") as upstream:
        response = client.get(route, params=signed)
    assert response.status_code == 403
    upstream.assert_not_called()


def test_content_car_is_closed_once_the_rental_is_terminal(client: TestClient) -> None:
    job_id = _seed_job()
    route = f"/v1/market/jobs/{job_id}/content-car"
    signed = _signed(_PROVIDER, _PROVIDER_KEY, route, {"cid": _CID})
    asyncio.run(_mark_job_terminal(job_id))
    with patch("market_service.routers.jobs.requests.post") as upstream:
        response = client.get(route, params=signed)
    assert response.status_code == 409
    upstream.assert_not_called()


def test_content_car_enforces_preflight_size_cap(client: TestClient) -> None:
    job_id = _seed_job()
    route = f"/v1/market/jobs/{job_id}/content-car"
    signed = _signed(_PROVIDER, _PROVIDER_KEY, route, {"cid": _CID})

    def fake_post(url: str, **kwargs: Any) -> Mock:
        assert url.endswith("/api/v0/dag/stat")
        return _response(text='{"TotalSize": 3000000}\n')

    with patch("market_service.routers.jobs.requests.post", side_effect=fake_post):
        response = client.get(route, params=signed)
    assert response.status_code == 413


def test_content_car_uses_offer_quota_not_caller_writable_constraints(client: TestClient) -> None:
    """A buyer cannot widen the proxy cap by writing a huge constraints value:
    the service row's offer quota is the authority (#2968/#2853 rule)."""
    job_id = asyncio.run(_seed_job_async(caller_quota_mb=1000))
    route = f"/v1/market/jobs/{job_id}/content-car"
    signed = _signed(_PROVIDER, _PROVIDER_KEY, route, {"cid": _CID})

    def fake_post(url: str, **kwargs: Any) -> Mock:
        assert url.endswith("/api/v0/dag/stat")
        return _response(text='{"TotalSize": 3000000}\n')

    with patch("market_service.routers.jobs.requests.post", side_effect=fake_post):
        response = client.get(route, params=signed)
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_signed_pin_error_is_recorded_and_server_keys_stay_server_owned(client: TestClient) -> None:
    job_id = await _seed_job_async()
    route = f"/v1/market/jobs/{job_id}/pin-error"
    error = "direct swarm pin/add failed; hub CAR fallback failed"
    signed = _signed(_PROVIDER, _PROVIDER_KEY, route, {"cid": _CID, "error": error})
    response = client.post(
        route,
        json={
            "cid": _CID,
            "error": error,
            "binding": {"cid": _CID, "error": error},
            "provider_confirmed": True,
            "pinned": True,
            **signed,
        },
    )
    assert response.status_code == 200
    assert response.json()["error"] == error
    assert response.json()["state"] == "FAILED"
    assert response.json()["payment_status"] == "refund_pending"
    assert await _payment_status(job_id) == "refund_pending"
    payload = await _payload(job_id)
    assert payload["delivery_error"] == error
    assert "delivery_error_at" in payload
    public = client.get(f"/v1/market/jobs/{job_id}")
    assert public.status_code == 200
    assert public.json()["error"] == error
    assert "payload" not in public.json()
    # Server-owned delivery fields remain stripped from caller-controlled writes.
    assert "provider_confirmed" not in payload
    assert "pinned" not in payload


@pytest.mark.asyncio
async def test_unsigned_or_intruder_pin_error_does_not_mutate_job(client: TestClient) -> None:
    job_id = await _seed_job_async()
    route = f"/v1/market/jobs/{job_id}/pin-error"
    error = "persistent delivery failure"
    unsigned = client.post(route, json={"cid": _CID, "error": error, "binding": {"cid": _CID, "error": error}})
    assert unsigned.status_code == 403
    signed = _signed(_INTRUDER, _INTRUDER_KEY, route, {"cid": _CID, "error": error})
    intruder = client.post(
        route,
        json={"cid": _CID, "error": error, "binding": {"cid": _CID, "error": error}, **signed},
    )
    assert intruder.status_code == 403
    assert "delivery_error" not in await _payload(job_id)


@pytest.mark.asyncio
async def test_pin_error_rejects_cid_mismatch_without_mutating_job(client: TestClient) -> None:
    job_id = await _seed_job_async()
    route = f"/v1/market/jobs/{job_id}/pin-error"
    error = "persistent delivery failure"
    wrong_cid = "QmNotTheJobCid"
    # The signature itself is valid over the caller's wrong-CID binding; the
    # route must still refuse it because the job row's stored CID is authoritative.
    signed = _signed(_PROVIDER, _PROVIDER_KEY, route, {"cid": wrong_cid, "error": error})
    response = client.post(
        route,
        json={"cid": wrong_cid, "error": error, "binding": {"cid": wrong_cid, "error": error}, **signed},
    )
    assert response.status_code == 403
    payload = await _payload(job_id)
    assert "delivery_error" not in payload
    assert await _payment_status(job_id) == "escrowed"


@pytest.mark.asyncio
async def test_pin_error_after_delivery_confirmation_is_ignored(client: TestClient) -> None:
    job_id = await _seed_job_async()
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        payload = dict(job.payload or {})
        payload["provider_confirmed"] = True
        job.payload = payload
        session.add(job)
        await session.commit()

    route = f"/v1/market/jobs/{job_id}/pin-error"
    error = "late stale sweeper failure"
    signed = _signed(_PROVIDER, _PROVIDER_KEY, route, {"cid": _CID, "error": error})
    response = client.post(
        route,
        json={"cid": _CID, "error": error, "binding": {"cid": _CID, "error": error}, **signed},
    )
    assert response.status_code == 409
    assert "delivery_error" not in await _payload(job_id)


@pytest.mark.asyncio
async def test_pin_error_loses_race_to_concurrent_delivery_confirmation() -> None:
    """The SQL CAS, not just the endpoint's stale-read check, must yield to a
    provider confirmation that lands in the read/write race window."""
    job_id = await _seed_job_async()
    original_execute = AsyncSession.execute

    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        job.payment_id = None  # keep the race fixture free of a payment write lock
        session.add(job)
        await session.commit()

    async with get_session_context() as session:
        svc = MarketService(session)
        raced = False

        async def racing_execute(self: AsyncSession, statement: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal raced
            table = getattr(statement, "table", None)
            if self is session and not raced and getattr(table, "name", None) == "marketplace_jobs":
                raced = True
                async with get_session_context() as confirmation_session:
                    confirmation_job = await confirmation_session.get(MarketJob, job_id)
                    assert confirmation_job is not None
                    payload = dict(confirmation_job.payload or {})
                    payload["provider_confirmed"] = True
                    confirmation_job.payload = payload
                    confirmation_session.add(confirmation_job)
                    await confirmation_session.commit()
            return await original_execute(self, statement, *args, **kwargs)

        try:
            AsyncSession.execute = racing_execute  # type: ignore[method-assign]
            result = await svc.report_market_job_pin_error(job_id, _CID, "racing delivery failure")
        finally:
            AsyncSession.execute = original_execute  # type: ignore[method-assign]

    assert raced is True
    assert result.get("state") != "FAILED"
    payload = await _payload(job_id)
    assert payload.get("provider_confirmed") is True
    assert "delivery_error" not in payload


@pytest.mark.asyncio
async def test_pin_error_is_terminal_and_marks_refund_pending(client: TestClient) -> None:
    job_id = await _seed_job_async()
    route = f"/v1/market/jobs/{job_id}/pin-error"
    error = "direct swarm pin/add timed out"
    signed = _signed(_PROVIDER, _PROVIDER_KEY, route, {"cid": _CID, "error": error})
    response = client.post(route, json={"cid": _CID, "error": error, **signed})
    assert response.status_code == 200
    assert response.json()["error"] == error

    async with get_session_context() as session:
        svc = MarketService(session)
        confirmed = await svc.confirm_market_job_pin(job_id, size=32, provider_confirmed=True)

    assert confirmed["state"] == "FAILED"
    assert confirmed["error"] == error
    assert confirmed["payment_status"] == "refund_pending"
    public = client.get(f"/v1/market/jobs/{job_id}")
    assert public.status_code == 200
    assert public.json()["error"] == error
