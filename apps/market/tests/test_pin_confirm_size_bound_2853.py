"""#2853 AUDIT-MONEY-42: pin-confirm size/pin_tx_hash writes are bounded.

``size`` lands verbatim in ``job.payload`` and is summed into the
buyer/offer ``used_bytes`` usage aggregate. Before the fix any
``MARKET_API_KEY`` holder could pin-confirm an unbounded ``size`` (and an
unbounded ``pin_tx_hash``) onto any live job — poisoning the
usage/billing-adjacent total. The route now bounds ``size`` by the
offer's ``disk_quota_mb`` (bytes) with a configured absolute cap, and
caps ``pin_tx_hash`` at 128 chars.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment, SoftwareService
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio

_BUYER = "0x" + "11" * 20
_PROVIDER = "0x" + "22" * 20


async def _seed_job(offer_id: str, *, disk_quota_mb: int | None) -> str:
    """Live QUEUED ipfs job + already-escrowed payment (skips the on-chain
    escrow proof so the pin-confirm reaches the payload write)."""
    async with get_session_context() as session:
        svc = MarketService(session)
        session.add(
            SoftwareService(
                service_type="ipfs",
                offer_id=offer_id,
                disk_quota_mb=disk_quota_mb,
            )
        )
        created = await svc.create_market_job(
            {
                "service_type": "ipfs",
                "buyer_address": _BUYER,
                "provider_address": _PROVIDER,
                "offer_id": offer_id,
                "payload": {"cid": "QmBound"},
                "payment": {"amount": "1.0"},
            }
        )
        job_id = created["job_id"]
        job = await session.get(MarketJob, job_id)
        assert job is not None and job.payment_id
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        payment.status = "escrowed"
        payment.escrowed_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(payment)
        await session.commit()
    return job_id


async def _payload_size(job_id: str) -> int | None:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        return (job.payload or {}).get("size")


async def _post_pin_confirm(job_id: str, body: dict) -> object:
    from fastapi.testclient import TestClient
    from market_service.main import app

    with TestClient(app) as client:
        return client.post(f"/v1/market/jobs/{job_id}/pin-confirm", json=body)


async def test_size_within_quota_accepted() -> None:
    job_id = await _seed_job("offer-quota-ok", disk_quota_mb=1)
    r = await _post_pin_confirm(job_id, {"size": 100})
    assert r.status_code == 200
    assert await _payload_size(job_id) == 100


async def test_size_above_quota_rejected_and_not_recorded() -> None:
    """1 MB quota -> 1_048_576 byte bound; 2 MiB must 400 and leave no size."""
    job_id = await _seed_job("offer-quota-tight", disk_quota_mb=1)
    r = await _post_pin_confirm(job_id, {"size": 2 * 1024 * 1024})
    assert r.status_code == 400
    assert await _payload_size(job_id) is None


async def test_size_at_quota_boundary_accepted() -> None:
    job_id = await _seed_job("offer-quota-edge", disk_quota_mb=1)
    r = await _post_pin_confirm(job_id, {"size": 1024 * 1024})
    assert r.status_code == 200
    assert await _payload_size(job_id) == 1024 * 1024


async def test_size_above_global_cap_rejected_without_quota() -> None:
    """No disk_quota_mb -> the configured absolute cap (1 TiB) still binds."""
    job_id = await _seed_job("offer-no-quota", disk_quota_mb=None)
    r = await _post_pin_confirm(job_id, {"size": (1 << 40) + 1})
    assert r.status_code == 400
    assert await _payload_size(job_id) is None


async def test_oversized_pin_tx_hash_rejected() -> None:
    job_id = await _seed_job("offer-hash-cap", disk_quota_mb=None)
    r = await _post_pin_confirm(job_id, {"pin_tx_hash": "0x" + "ab" * 100})
    assert r.status_code == 400


async def test_normal_pin_tx_hash_still_accepted() -> None:
    job_id = await _seed_job("offer-hash-ok", disk_quota_mb=None)
    r = await _post_pin_confirm(job_id, {"pin_tx_hash": "0x" + "ab" * 32, "size": 5})
    assert r.status_code == 200
