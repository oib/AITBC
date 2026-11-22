"""Public view vs authenticated owner/provider views of the market job feed.

GET /v1/market/jobs and GET /v1/market/jobs/{job_id} answer anonymous callers
with a redacted row: customer file details (payload.cid/file_name/ipfs_api,
constraints.*), rental identifiers (access_key, client_id, client_ref) and
buyer_address never leave unauthenticated. Full rows go to the service API
key, the rental access credential (X-Access-Key/X-Access-Secret), or a
wallet-signed request from the job's buyer or provider.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_data
from aitbc.market.job_request_signature import jobs_request_message
from aitbc.utils.chain_id import resolve_chain_id
from market_service.config import settings
from market_service.main import app
from market_service.domain.market import MarketJob, MarketJobPayment, SoftwareService
from market_service.services.market_service import (
    PUBLIC_JOB_FIELDS,
    MarketService,
    public_job_view,
)
from market_service.storage import get_session_context

_TEST_PRIVATE_KEY = "0x" + "44" * 32
_OTHER_PRIVATE_KEY = "0x" + "55" * 32


def _address(private_key: str) -> str:
    return derive_ethereum_address(private_key)


def _signed_params(
    address: str,
    route: str,
    private_key: str = _TEST_PRIVATE_KEY,
    chain_id: str | None = None,
    issued_at: int | None = None,
    binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issued_at = int(time.time()) if issued_at is None else issued_at
    chain_id = chain_id or settings.default_chain_id or resolve_chain_id()
    signature = sign_transaction_data(jobs_request_message(address, chain_id, issued_at, route, binding=binding), private_key)
    params: dict[str, Any] = {
        "signer_address": address,
        "chain_id": chain_id,
        "issued_at": issued_at,
        "signature": signature,
    }
    if binding is not None:
        params["binding"] = binding
    return params


def _seed_job(**fields: Any) -> dict[str, Any]:
    async def _create() -> dict[str, Any]:
        async with get_session_context() as session:
            return await MarketService(session).create_market_job(fields)

    return asyncio.run(_create())


def _seed_ipfs_job(private_key: str = _TEST_PRIVATE_KEY, **overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "service_type": "ipfs",
        "model": "ipfs-host",
        "buyer_address": _address(_OTHER_PRIVATE_KEY),
        "provider_address": _address(private_key),
        "offer_id": "offer-sec4",
        "state": "QUEUED",
        "client_id": "client-1",
        "client_ref": "ref-1",
        "constraints": {"disk_quota_mb": 100},
        "payload": {
            "cid": "QmSec4",
            "file_name": "customer-file.txt",
            "ipfs_api": "http://127.0.0.1:5002",
            # #2607: job access_key is unique — the seed runs per test.
            "access_key": f"rental-ak-sec4-{time.time_ns()}",
            "access_secret": "rental-secret-sec4",
            "days": 3,
            "size": 2048,
        },
        "payment": {"amount": "1.0", "status": "escrowed", "escrow_address": "0xescrow", "refund_address": "0xrefund"},
    }
    fields.update(overrides)

    # #1564: create_market_job rejects unknown offer_ids — register the offer.
    # #2617: the service row carries the provider address — the pin-confirm
    # gate resolves the expected signer from it, never from the job row.
    # Upsert by offer_id: the module shares one DB, so repeated seeds would
    # otherwise leave duplicate offer_id rows and get_service_by_offer_id's
    # scalar_one_or_none would 500.
    async def _seed_offer() -> None:
        from sqlmodel import select

        async with get_session_context() as session:
            offer_id = str(fields["offer_id"])
            row = (
                (await session.execute(select(SoftwareService).where(SoftwareService.offer_id == offer_id))).scalars().first()
            )
            if row is None:
                session.add(SoftwareService(service_type="ipfs", offer_id=offer_id, provider_address=_address(private_key)))
            else:
                row.provider_address = _address(private_key)
                session.add(row)
            await session.commit()

    asyncio.run(_seed_offer())
    record = _seed_job(**fields)

    # #815: create_market_job ignores caller-set lifecycle fields — drive the
    # escrowed state the way the payment path would, then re-read the row.
    async def _settle_and_fetch() -> dict[str, Any]:
        async with get_session_context() as session:
            job = await session.get(MarketJob, record["job_id"])
            assert job is not None
            job.state = fields.get("state", "QUEUED")
            job.payment_status = "escrowed"
            payment = await session.get(MarketJobPayment, job.payment_id)
            assert payment is not None
            payment.status = "escrowed"
            session.add_all([job, payment])
            await session.commit()
            return await MarketService(session).get_market_job(record["job_id"])

    return asyncio.run(_settle_and_fetch())


@pytest.fixture(autouse=True)
def _rate_limiting_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable the shared rate-limit middleware for this module — and only for it.

    TestClient requests share one client host; the suite's request volume
    trips the 120/min middleware bucket otherwise (same pattern as
    apps/agent-coordinator tests). This used to be
    ``os.environ.setdefault`` at module import time, which leaked the flag
    into every suite collected afterwards in the same pytest process and
    silently disabled rate limiting for the trading/pool-hub 429 pins
    (#1657). ``monkeypatch`` restores the previous value after each test.
    """
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "false")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _walk_keys(value: Any, prefix: str = "") -> set[str]:
    """Every dotted key path in a response row, recursing into dict values."""
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, sub in value.items():
            keys.add(f"{prefix}{key}")
            keys |= _walk_keys(sub, f"{prefix}{key}.")
    return keys


# --- public view unit test -------------------------------------------------


def test_public_job_view_strips_customer_fields() -> None:
    job = _seed_ipfs_job()  # create_market_job returns the full record
    view = public_job_view(job)

    for stripped in (
        "access_key",
        "buyer_address",
        "client_id",
        "client_ref",
        "payload",
        "constraints",
    ):
        assert stripped not in view

    for kept in (
        "job_id",
        "offer_id",
        "service_type",
        "model",
        "provider_address",
        "state",
        "payment_id",
        "payment_status",
        "escrow_contract_id",
        "tx_hash",
        "refund_tx_hash",
        "requested_at",
        "created_at",
        "receipt",
        "result",
    ):
        assert kept in view

    assert isinstance(view["payment"], dict)
    for stripped in ("escrow_address", "refund_address", "meta_data"):
        assert stripped not in view["payment"]
    assert view["payment"]["status"] == "escrowed"
    assert set(view.keys()) <= set(PUBLIC_JOB_FIELDS) | {"payment"}


# --- feed shape ------------------------------------------------------------

_STRIPPED_KEYS = {
    "access_key",
    "buyer_address",
    "client_id",
    "client_ref",
    "payload",
    "payload.access_key",
    "payload.access_secret",
    "payload.cid",
    "payload.file_name",
    "payload.ipfs_api",
    "payload.days",
    "payload.pinned",
    "payload.provider_confirmed",
    "payload.public_endpoint",
    "payload.size",
    "constraints",
    "constraints.disk_quota_mb",
    "payment.escrow_address",
    "payment.refund_address",
    "payment.meta_data",
}


def test_public_list_feed_shape(client: TestClient) -> None:
    _seed_ipfs_job()
    response = client.get("/v1/market/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert jobs, "expected seeded rows in the feed"
    for job in jobs:
        leaked = _walk_keys(job) & _STRIPPED_KEYS
        assert not leaked, f"public feed leaked {leaked}"
        for required in ("job_id", "state", "service_type", "payment_status", "escrow_contract_id"):
            assert required in job


def test_public_single_job_shape(client: TestClient) -> None:
    job = _seed_ipfs_job()
    response = client.get(f"/v1/market/jobs/{job['job_id']}")
    assert response.status_code == 200
    view = response.json()
    leaked = _walk_keys(view) & _STRIPPED_KEYS
    assert not leaked, f"public job view leaked {leaked}"
    assert view["job_id"] == job["job_id"]


# --- authenticated views ----------------------------------------------------


def test_signed_provider_gets_full_rows(client: TestClient) -> None:
    job = _seed_ipfs_job()
    provider = _address(_TEST_PRIVATE_KEY)
    params = _signed_params(provider, "/v1/market/jobs", private_key=_TEST_PRIVATE_KEY)
    params["service_type"] = "ipfs"
    response = client.get("/v1/market/jobs", params=params)
    assert response.status_code == 200
    rows = [row for row in response.json() if row["job_id"] == job["job_id"]]
    assert rows, "provider signature should return the provider's job rows"
    assert rows[0]["payload"]["cid"] == "QmSec4"
    assert rows[0]["buyer_address"]


def test_signed_buyer_gets_full_rows(client: TestClient) -> None:
    job = _seed_ipfs_job()
    buyer = _address(_OTHER_PRIVATE_KEY)
    params = _signed_params(buyer, "/v1/market/jobs", private_key=_OTHER_PRIVATE_KEY)
    response = client.get("/v1/market/jobs", params=params)
    assert response.status_code == 200
    rows = [row for row in response.json() if row["job_id"] == job["job_id"]]
    assert rows
    assert "payload" in rows[0]


def test_signature_wrong_address_is_403(client: TestClient) -> None:
    _seed_ipfs_job()
    provider = _address(_TEST_PRIVATE_KEY)
    params = _signed_params(provider, "/v1/market/jobs", private_key=_OTHER_PRIVATE_KEY)
    response = client.get("/v1/market/jobs", params=params)
    assert response.status_code == 403


def test_signature_stale_issued_at_is_403(client: TestClient) -> None:
    _seed_ipfs_job()
    provider = _address(_TEST_PRIVATE_KEY)
    params = _signed_params(provider, "/v1/market/jobs", issued_at=int(time.time()) - 3600)
    response = client.get("/v1/market/jobs", params=params)
    assert response.status_code == 403


def test_signature_wrong_chain_is_403(client: TestClient) -> None:
    _seed_ipfs_job()
    provider = _address(_TEST_PRIVATE_KEY)
    params = _signed_params(provider, "/v1/market/jobs", chain_id="wrong-chain")
    response = client.get("/v1/market/jobs", params=params)
    assert response.status_code == 403


def test_address_filter_mismatch_with_signer_is_403(client: TestClient) -> None:
    _seed_ipfs_job()
    provider = _address(_TEST_PRIVATE_KEY)
    params = _signed_params(provider, "/v1/market/jobs")
    params["provider_address"] = _address(_OTHER_PRIVATE_KEY)
    response = client.get("/v1/market/jobs", params=params)
    assert response.status_code == 403


def test_signed_single_job_full_record(client: TestClient) -> None:
    job = _seed_ipfs_job()
    route = f"/v1/market/jobs/{job['job_id']}"
    params = _signed_params(_address(_TEST_PRIVATE_KEY), route)
    response = client.get(route, params=params)
    assert response.status_code == 200
    row = response.json()
    assert row["payload"]["access_key"] == job["payload"]["access_key"]
    assert row["buyer_address"]


def test_signed_single_job_not_a_party_is_403(client: TestClient) -> None:
    job = _seed_ipfs_job()
    route = f"/v1/market/jobs/{job['job_id']}"
    params = _signed_params(_address("0x" + "66" * 32), route, private_key="0x" + "66" * 32)
    response = client.get(route, params=params)
    assert response.status_code == 403


def test_access_credential_gets_owner_record(client: TestClient) -> None:
    job = _seed_ipfs_job()
    route = f"/v1/market/jobs/{job['job_id']}"
    access_key = job["payload"]["access_key"]
    response = client.get(route, headers={"X-Access-Key": access_key, "X-Access-Secret": "rental-secret-sec4"})
    assert response.status_code == 200
    assert response.json()["payload"]["cid"] == "QmSec4"

    wrong = client.get(route, headers={"X-Access-Key": access_key, "X-Access-Secret": "nope"})
    assert wrong.status_code == 403


def test_user_key_gets_public_rows_not_full(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """#2606: the user-tier key is distributed — it no longer counts as
    'market admin' on the job reads; rows stay redacted."""
    _seed_ipfs_job()
    monkeypatch.setattr(settings, "api_key", "test-admin-key")
    response = client.get("/v1/market/jobs", headers={"X-Api-Key": "test-admin-key"})
    assert response.status_code == 200
    for job in response.json():
        assert "payload" not in job


def test_operator_key_gets_full_rows(client: TestClient, market_api_keys: dict[str, str]) -> None:
    job = _seed_ipfs_job()
    response = client.get("/v1/market/jobs", headers={"X-Api-Key": "test-operator-key"})
    assert response.status_code == 200
    rows = [row for row in response.json() if row["job_id"] == job["job_id"]]
    assert rows and "payload" in rows[0]


def test_wrong_admin_key_stays_public(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_ipfs_job()
    monkeypatch.setattr(settings, "api_key", "test-admin-key")
    response = client.get("/v1/market/jobs", headers={"X-Api-Key": "wrong"})
    assert response.status_code == 200
    for job in response.json():
        assert "payload" not in job


# --- pin-confirm signature ---------------------------------------------------


def test_pin_confirm_provider_confirmed_requires_signature(client: TestClient) -> None:
    # Unique client_ref: create_market_job replays on client_ref, and the
    # suite shares one DB — a reused ref would return a row an earlier
    # pin-confirm test already mutated.
    job = _seed_ipfs_job(client_ref=f"ref-pin-signed-{time.time_ns()}")
    route = f"/v1/market/jobs/{job['job_id']}/pin-confirm"
    unsigned = client.post(route, json={"size": 2048, "provider_confirmed": True})
    assert unsigned.status_code == 403

    # #1922: the attestation must be signed over a {cid, size} binding that
    # matches the job — an unbound signature is refused.
    unbound = client.post(
        route,
        json={
            "size": 2048,
            "provider_confirmed": True,
            **_signed_params(_address(_TEST_PRIVATE_KEY), route),
        },
    )
    assert unbound.status_code == 403

    binding = {"cid": "QmSec4", "size": 2048}
    body = {
        "size": 2048,
        "provider_confirmed": True,
        **_signed_params(_address(_TEST_PRIVATE_KEY), route, binding=binding),
    }
    signed = client.post(route, json=body)
    assert signed.status_code == 200
    assert signed.json()["payload"]["provider_confirmed"] is True
    assert signed.json()["state"] == "RUNNING"


def test_pin_confirm_size_only_stays_open(client: TestClient) -> None:
    """The buyer's host flow reports size without provider credentials.

    #1922: unsigned reports are informational — they record the size but
    must not mint delivery evidence or the RUNNING state."""
    # Unique client_ref — see test_pin_confirm_provider_confirmed_requires_signature.
    job = _seed_ipfs_job(client_ref=f"ref-pin-size-{time.time_ns()}")
    response = client.post(f"/v1/market/jobs/{job['job_id']}/pin-confirm", json={"size": 2048})
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "QUEUED"
    assert body["payload"]["size"] == 2048
    assert body["payload"].get("pinned") is not True
    assert body["payload"].get("provider_confirmed") is not True


def test_pin_confirm_binding_must_match_job(client: TestClient) -> None:
    """#1922: a valid provider signature over the wrong cid, or a binding whose
    size differs from the reported size, is refused — the attestation is
    bound to this job's stored CID and the recorded size."""
    job = _seed_ipfs_job(client_ref=f"ref-pin-bind-{time.time_ns()}")
    route = f"/v1/market/jobs/{job['job_id']}/pin-confirm"
    address = _address(_TEST_PRIVATE_KEY)

    cases = [
        # Signed binding names a different CID than the job stores.
        ({"cid": "QmOther", "size": 2048}, 2048),
        # Signed binding attests a different size than the body records —
        # the recorded size must be the attested one.
        ({"cid": "QmSec4", "size": 9999}, 2048),
    ]
    for binding, reported_size in cases:
        body = {
            "size": reported_size,
            "provider_confirmed": True,
            **_signed_params(address, route, binding=binding),
        }
        response = client.post(route, json=body)
        assert response.status_code == 403, (binding, reported_size, response.text)


def test_pin_confirm_wrong_provider_is_403(client: TestClient) -> None:
    job = _seed_ipfs_job()
    route = f"/v1/market/jobs/{job['job_id']}/pin-confirm"
    binding = {"cid": "QmSec4", "size": 2048}
    body = {
        "size": 2048,
        "provider_confirmed": True,
        **_signed_params(_address(_OTHER_PRIVATE_KEY), route, private_key=_OTHER_PRIVATE_KEY, binding=binding),
    }
    response = client.post(route, json=body)
    assert response.status_code == 403


def test_pin_confirm_signer_must_be_offer_provider_not_job_provider(client: TestClient) -> None:
    """#2617: ``provider_address`` is caller-writable at job creation, so the
    attestation must verify against the offer's SoftwareService provider —
    a buyer naming its own wallet as job provider cannot self-attest."""
    from sqlmodel import select

    job = _seed_ipfs_job(client_ref=f"ref-pin-offerprov-{time.time_ns()}")

    # Flip the service's registered provider to the other wallet: the job
    # row still claims _TEST_PRIVATE_KEY's address — exactly the
    # caller-writable field the fix stops trusting.
    async def _flip() -> None:
        async with get_session_context() as session:
            row = (await session.execute(select(SoftwareService).where(SoftwareService.offer_id == "offer-sec4"))).scalar_one()
            row.provider_address = _address(_OTHER_PRIVATE_KEY)
            session.add(row)
            await session.commit()

    asyncio.run(_flip())
    route = f"/v1/market/jobs/{job['job_id']}/pin-confirm"
    binding = {"cid": "QmSec4", "size": 2048}
    body = {
        "size": 2048,
        "provider_confirmed": True,
        **_signed_params(_address(_TEST_PRIVATE_KEY), route, binding=binding),
    }
    response = client.post(route, json=body)
    assert response.status_code == 403


# --- job access route party gate (#2515) -------------------------------------


@pytest.fixture
def market_api_keys(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Arm both key tiers the way production runs them.

    ``require_market_api_key`` authenticates via the authenticator
    singletons; ``_is_operator`` reads the same objects plus
    ``settings.auth_enabled`` — all four must agree or the gate sees an
    auth-disabled deployment and waves everyone through.
    """
    from market_service import main as market_main

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "api_key", "test-market-key")
    monkeypatch.setattr(settings, "operator_api_key", "test-operator-key")
    monkeypatch.setattr(market_main._market_user_key_auth, "auth_enabled", True)
    monkeypatch.setattr(market_main._market_user_key_auth, "expected_key", "test-market-key")
    monkeypatch.setattr(market_main._market_operator_key_auth, "auth_enabled", True)
    monkeypatch.setattr(market_main._market_operator_key_auth, "expected_key", "test-operator-key")
    return {"X-Api-Key": "test-market-key"}


def _access_route(job: dict[str, Any]) -> str:
    return f"/v1/market/jobs/{job['job_id']}/access"


def test_job_access_user_key_alone_is_403(client: TestClient, market_api_keys: dict[str, str]) -> None:
    """#2515 repro: any holder of the distributed user-tier key could read
    cid/ipfs_api/access_key for any job — now refused."""
    job = _seed_ipfs_job()
    response = client.get(_access_route(job), headers=market_api_keys)
    assert response.status_code == 403


def test_job_access_operator_key_gets_metadata(client: TestClient, market_api_keys: dict[str, str]) -> None:
    job = _seed_ipfs_job()
    response = client.get(_access_route(job), headers={"X-Api-Key": "test-operator-key"})
    assert response.status_code == 200
    body = response.json()
    assert body["cid"] == "QmSec4"
    assert body["access_key"] == job["payload"]["access_key"]
    assert "access_secret" not in body


def test_job_access_credential_gets_metadata(client: TestClient, market_api_keys: dict[str, str]) -> None:
    job = _seed_ipfs_job()
    access_key = job["payload"]["access_key"]
    headers = {
        **market_api_keys,
        "X-Access-Key": access_key,
        "X-Access-Secret": "rental-secret-sec4",
    }
    response = client.get(_access_route(job), headers=headers)
    assert response.status_code == 200
    assert response.json()["cid"] == "QmSec4"

    wrong = client.get(
        _access_route(job),
        headers={**market_api_keys, "X-Access-Key": access_key, "X-Access-Secret": "nope"},
    )
    assert wrong.status_code == 403


def test_job_access_signed_party_gets_metadata(client: TestClient, market_api_keys: dict[str, str]) -> None:
    job = _seed_ipfs_job()
    route = _access_route(job)
    provider = _address(_TEST_PRIVATE_KEY)
    params = _signed_params(provider, route)
    response = client.get(route, params=params, headers=market_api_keys)
    assert response.status_code == 200
    assert response.json()["cid"] == "QmSec4"

    buyer = _address(_OTHER_PRIVATE_KEY)
    buyer_params = _signed_params(buyer, route, private_key=_OTHER_PRIVATE_KEY)
    buyer_response = client.get(route, params=buyer_params, headers=market_api_keys)
    assert buyer_response.status_code == 200


def test_job_access_foreign_signer_is_403(client: TestClient, market_api_keys: dict[str, str]) -> None:
    job = _seed_ipfs_job()
    route = _access_route(job)
    foreign = "0x" + "66" * 32
    params = _signed_params(_address(foreign), route, private_key=foreign)
    response = client.get(route, params=params, headers=market_api_keys)
    assert response.status_code == 403


def test_job_access_bad_signature_is_403(client: TestClient, market_api_keys: dict[str, str]) -> None:
    job = _seed_ipfs_job()
    route = _access_route(job)
    params = _signed_params(_address(_TEST_PRIVATE_KEY), route, issued_at=int(time.time()) - 3600)
    response = client.get(route, params=params, headers=market_api_keys)
    assert response.status_code == 403
