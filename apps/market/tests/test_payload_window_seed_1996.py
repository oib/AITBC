"""#1996 MARKET-PAYLOAD-WINDOW-SEED-1: caller payload cannot pre-seed the
#1976 release window.

``create_market_job`` accepts a fully caller-controlled ``payload``. Before
the fix nothing stripped the server-owned delivery/window keys
(``provider_confirmed``, ``provider_confirmed_at``, ``pinned``,
``pin_tx_hash``): a caller could create a job with a *past*
``provider_confirmed_at``, and when the signed pin-confirm later CASed
QUEUED->RUNNING, ``_pin_payload``'s ``setdefault`` kept the seeded
timestamp — so ``_provider_release_window_gate`` saw an already-expired
buyer-acceptance window and a provider-signed release passed immediately.

Pinned here:

* creation strips the server-owned keys from the stored payload while
  keeping caller-legit fields (``cid``, ``size``);
* the full exploit chain — seeded past timestamp -> real pin-confirm ->
  provider-signed release — is still window-held (403).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment, SoftwareService
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

from .test_market_settle_party_sig import _settle_signature, stub_escrow_rpc  # noqa: F401
from .test_provider_release_window_1976 import user_tier  # noqa: F401

pytestmark = pytest.mark.asyncio

_SEEDED = "2020-01-01T00:00:00"


async def _create_seeded_job() -> tuple[str, str]:
    """Create a job through the real ``create_market_job`` path with the
    exploit payload. Returns (job_id, provider_private_key)."""
    from aitbc.crypto.crypto import derive_ethereum_address

    buyer_key, provider_key = "0x" + "11" * 32, "0x" + "22" * 32
    async with get_session_context() as session:
        svc = MarketService(session)
        svc.session.add(SoftwareService(service_type="ipfs", offer_id="offer-1996"))
        await svc.session.commit()
        created = await svc.create_market_job(
            {
                "service_type": "ipfs",
                "buyer_address": derive_ethereum_address(buyer_key),
                "provider_address": derive_ethereum_address(provider_key),
                "offer_id": "offer-1996",
                "payload": {
                    "cid": "QmSeed1996",
                    "size": 10,
                    "provider_confirmed": True,
                    "provider_confirmed_at": _SEEDED,
                    "pinned": True,
                    "pin_tx_hash": "0xdeadbeef",
                },
                "payment": {"amount": "1.0", "status": "pending"},
            }
        )
        job_id = created["job_id"]
        # Drive the escrowed lifecycle the way settlement would (#815:
        # create ignores caller payment.status).
        job = await svc.session.get(MarketJob, job_id)
        assert job is not None
        job.state = "QUEUED"
        job.payment_status = "escrowed"
        payment = await svc.session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        payment.status = "escrowed"
        payment.escrowed_at = datetime.now(UTC).replace(tzinfo=None)
        payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
        svc.session.add_all([job, payment])
        await svc.session.commit()
    return job_id, provider_key


async def test_creation_strips_server_owned_payload_keys() -> None:
    job_id, _ = await _create_seeded_job()
    async with get_session_context() as session:
        fetched = await MarketService(session).get_market_job(job_id)
    assert fetched is not None
    payload = fetched["payload"]
    for key in ("provider_confirmed", "provider_confirmed_at", "pinned", "pin_tx_hash"):
        assert key not in payload, f"server-owned key {key} survived creation"
    # Caller-legit fields are untouched.
    assert payload["cid"] == "QmSeed1996"
    assert payload["size"] == 10


async def test_seeded_window_cannot_skip_release_gate(stub_escrow_rpc, user_tier) -> None:  # noqa: F811
    from aitbc.crypto.crypto import derive_ethereum_address
    from fastapi.testclient import TestClient
    from market_service.main import app

    job_id, provider_key = await _create_seeded_job()

    # Real signed pin-confirm mints RUNNING + the true window start.
    async with get_session_context() as session:
        await MarketService(session).confirm_market_job_pin(job_id, size=10, provider_confirmed=True)

    async with get_session_context() as session:
        fetched = await MarketService(session).get_market_job(job_id)
    assert fetched["state"] == "RUNNING"
    assert fetched["payload"]["provider_confirmed_at"] != _SEEDED

    # Provider-signed release inside the window is still refused — pre-fix
    # the seeded 2020 timestamp made opens_at already past and this returned 200.
    proof = _settle_signature(
        job_id,
        provider_key,
        derive_ethereum_address(provider_key),
        f"/v1/market/jobs/{job_id}/release",
    )
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/release", json=proof)
    assert r.status_code == 403
    assert "buyer-acceptance window" in r.json()["error"]
