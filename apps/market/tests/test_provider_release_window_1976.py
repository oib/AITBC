"""#1976 PIN-CONFIRM-PROVIDER-SELF-RELEASE-1: the provider alone cannot release.

The #1922 pin attestation is the provider's own signature, so provider-attested
delivery plus a provider-signed release used to pay out with no buyer input.
A release signed only by the provider is held until the buyer-acceptance window
since ``provider_confirmed_at`` has elapsed; the buyer's signature or the
operator credential release immediately.
"""

from __future__ import annotations

import pytest
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

from .test_market_settle_party_sig import _payment_status, _seed_settle_job, _settle_signature, stub_escrow_rpc  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest.fixture
def user_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the caller a plain user-key holder (not the operator tier)."""
    from market_service import main

    monkeypatch.setattr(main, "_is_operator", lambda request: False)


async def _release(job_id: str, key: str):
    from aitbc.crypto.crypto import derive_ethereum_address
    from fastapi.testclient import TestClient
    from market_service.main import app

    proof = _settle_signature(job_id, key, derive_ethereum_address(key), f"/v1/market/jobs/{job_id}/release")
    with TestClient(app) as client:
        return client.post(f"/v1/market/jobs/{job_id}/release", json=proof)


async def test_provider_signed_release_inside_window_is_refused(stub_escrow_rpc, user_tier) -> None:  # noqa: F811
    job_id, _, provider_key = await _seed_settle_job()
    r = await _release(job_id, provider_key)
    assert r.status_code == 403
    assert "buyer-acceptance window" in r.json()["error"]
    assert "release_opens_at" in r.json()
    assert await _payment_status(job_id) == ("RUNNING", "escrowed")


async def test_provider_signed_release_after_window_is_allowed(stub_escrow_rpc, user_tier, monkeypatch) -> None:  # noqa: F811
    monkeypatch.setenv("MARKET_BUYER_ACCEPTANCE_SECONDS", "0")
    job_id, _, provider_key = await _seed_settle_job()
    r = await _release(job_id, provider_key)
    assert r.status_code == 200
    assert r.json()["state"] == "RELEASED"


async def test_buyer_signed_release_is_immediate(stub_escrow_rpc, user_tier) -> None:  # noqa: F811
    job_id, buyer_key, _ = await _seed_settle_job()
    r = await _release(job_id, buyer_key)
    assert r.status_code == 200


async def test_operator_release_is_immediate(stub_escrow_rpc) -> None:  # noqa: F811
    from fastapi.testclient import TestClient
    from market_service.main import app

    job_id, _, _ = await _seed_settle_job()
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/release", json={})
    assert r.status_code == 200


async def test_pin_confirm_records_window_start_once() -> None:
    from .test_pin_confirm_gate_1922 import _seed

    job_id, _ = await _seed(payment_status="escrowed")
    async with get_session_context() as session:
        out = await MarketService(session).confirm_market_job_pin(job_id, size=1, provider_confirmed=True)
    first = out["payload"]["provider_confirmed_at"]
    async with get_session_context() as session:
        again = await MarketService(session).confirm_market_job_pin(job_id, size=2, provider_confirmed=True)
    assert again["payload"]["provider_confirmed_at"] == first
