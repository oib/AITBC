"""Regression tests — market job dispute freeze (#1783).

* ``POST /jobs/{id}/dispute`` accepts a party wallet signature (same rule as
  cancel, #1634) or the unsigned operator API-key path; a foreign signer is
  rejected and must not set the freeze.
* ``POST /jobs/{id}/dispute/resolve`` clears the freeze so the sweeper can
  settle/refund again.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import MarketJob
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio


def _uid() -> str:
    return uuid4().hex[:8]


async def _seed_job() -> tuple[str, str, str]:
    """Return (job_id, buyer_private_key, provider_private_key).

    #1835 F7: dispute_market_job now requires a live escrowed payment — the
    seed attaches one so the dispute/resolve routes have something to freeze.
    """
    from decimal import Decimal

    from aitbc.crypto.crypto import derive_ethereum_address
    from market_service.domain.market import MarketJobPayment

    buyer_key, provider_key = "0x" + "11" * 32, "0x" + "22" * 32
    async with get_session_context() as session:
        job_id = f"job_disp_{_uid()}"
        payment = MarketJobPayment(id=f"pay_{_uid()}", job_id=job_id, amount=Decimal("1.0"), status="escrowed")
        session.add(
            MarketJob(
                id=job_id,
                buyer_address=derive_ethereum_address(buyer_key),
                provider_address=derive_ethereum_address(provider_key),
                service_type="ipfs",
                state="RUNNING",
                offer_id="offer_x",
                payload={},
                payment_id=payment.id,
                payment_status="escrowed",
            )
        )
        session.add(payment)
        await session.commit()
    return job_id, buyer_key, provider_key


def _dispute_signature(job_id: str, private_key: str, address: str, route: str) -> dict:
    from aitbc.crypto.crypto import sign_transaction_data
    from aitbc.market.job_request_signature import jobs_request_message
    from aitbc.utils.chain_id import resolve_chain_id
    from market_service.config import settings

    chain_id = settings.default_chain_id or resolve_chain_id()
    issued_at = int(time.time())
    return {
        "signer_address": address,
        "chain_id": chain_id,
        "issued_at": issued_at,
        "signature": sign_transaction_data(jobs_request_message(address, chain_id, issued_at, route), private_key),
    }


async def _dispute_fields(job_id: str) -> MarketJob:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        return job


async def test_dispute_signed_by_job_party_freezes() -> None:
    from fastapi.testclient import TestClient
    from market_service.main import app

    job_id, buyer_key, _ = await _seed_job()
    from aitbc.crypto.crypto import derive_ethereum_address

    proof = _dispute_signature(job_id, buyer_key, derive_ethereum_address(buyer_key), f"/v1/market/jobs/{job_id}/dispute")
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/dispute", json={"reason": "buyer claims non-delivery", **proof})
    assert r.status_code == 200
    assert r.json()["disputed_at"] is not None

    job = await _dispute_fields(job_id)
    assert job.disputed_at is not None
    assert job.dispute_reason == "buyer claims non-delivery"
    assert job.dispute_cleared_at is None


async def test_dispute_signed_by_non_party_is_403_and_does_not_freeze() -> None:
    from fastapi.testclient import TestClient
    from market_service.main import app

    job_id, _, _ = await _seed_job()
    from aitbc.crypto.crypto import derive_ethereum_address

    stranger_key = "0x" + "33" * 32
    proof = _dispute_signature(
        job_id, stranger_key, derive_ethereum_address(stranger_key), f"/v1/market/jobs/{job_id}/dispute"
    )
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/dispute", json={"reason": "sabotage", **proof})
    assert r.status_code == 403

    job = await _dispute_fields(job_id)
    assert job.disputed_at is None


async def test_dispute_unsigned_api_key_path_works() -> None:
    from fastapi.testclient import TestClient
    from market_service.main import app

    job_id, _, _ = await _seed_job()
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/dispute", json={"reason": "operator freeze"})
    assert r.status_code == 200

    job = await _dispute_fields(job_id)
    assert job.disputed_at is not None


async def test_dispute_resolve_clears_freeze() -> None:
    from fastapi.testclient import TestClient
    from market_service.main import app

    job_id, _, _ = await _seed_job()
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/dispute", json={"reason": "operator freeze"})
        assert r.status_code == 200
        r = client.post(f"/v1/market/jobs/{job_id}/dispute/resolve")
    assert r.status_code == 200
    assert r.json()["dispute_cleared_at"] is not None

    job = await _dispute_fields(job_id)
    assert job.disputed_at is not None
    assert job.dispute_cleared_at is not None


async def test_dispute_resolve_unknown_job_is_404() -> None:
    from fastapi.testclient import TestClient
    from market_service.main import app

    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/nonexistent_{_uid()}/dispute/resolve")
    assert r.status_code == 404


# --- dispute adjudication can reroute funds (#2852) ----------------------------


async def _seed_completed_disputed_job() -> str:
    """COMPLETED job (provider attested) + escrowed payment + open dispute —
    the exact state where resolution used to be able to pay only the
    provider."""
    from decimal import Decimal

    from aitbc.crypto.crypto import derive_ethereum_address
    from market_service.domain.market import MarketJobPayment
    from market_service.services.market_service import MarketService

    buyer_key, provider_key = "0x" + "44" * 32, "0x" + "55" * 32
    async with get_session_context() as session:
        job_id = f"job_cmp_{_uid()}"
        payment = MarketJobPayment(id=f"pay_{_uid()}", job_id=job_id, amount=Decimal("1.0"), status="escrowed")
        session.add(
            MarketJob(
                id=job_id,
                buyer_address=derive_ethereum_address(buyer_key),
                provider_address=derive_ethereum_address(provider_key),
                service_type="ipfs",
                state="COMPLETED",
                offer_id="offer_x",
                payload={"provider_confirmed": True},
                payment_id=payment.id,
                payment_status="escrowed",
            )
        )
        session.add(payment)
        await session.commit()
        # Open the dispute through the real path.
        await MarketService(session).dispute_market_job(job_id, reason="buyer claims defective delivery")
    return job_id


async def _payment_status(job_id: str) -> str | None:
    from market_service.domain.market import MarketJobPayment

    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None and job.payment_id
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        return payment.status


async def test_resolve_buyer_adjudication_flips_escrow_to_refund_pending() -> None:
    """#2852: resolution='buyer' must leave the payment on the refund rail —
    before this, a cleared dispute on COMPLETED could only pay the provider."""
    from market_service.services.market_service import MarketService

    job_id = await _seed_completed_disputed_job()
    assert await _payment_status(job_id) == "escrowed"

    async with get_session_context() as session:
        out = await MarketService(session).resolve_market_job_dispute(job_id, resolution="buyer")
    assert out["dispute_cleared_at"] is not None
    assert await _payment_status(job_id) == "refund_pending"


async def test_resolve_provider_adjudication_keeps_release_path() -> None:
    """Default/'provider' resolution is unchanged: escrow stays for release."""
    from market_service.services.market_service import MarketService

    job_id = await _seed_completed_disputed_job()
    async with get_session_context() as session:
        await MarketService(session).resolve_market_job_dispute(job_id, resolution="provider")
        await MarketService(session).resolve_market_job_dispute(job_id)  # default arg
    assert await _payment_status(job_id) == "escrowed"


async def test_unknown_resolution_rejected() -> None:
    from market_service.services.market_service import MarketService

    job_id = await _seed_completed_disputed_job()
    async with get_session_context() as session:
        with pytest.raises(ValueError, match="resolution"):
            await MarketService(session).resolve_market_job_dispute(job_id, resolution="split")
    # The dispute must still be open — a rejected resolution changes nothing.
    job = await _dispute_fields(job_id)
    assert job.dispute_cleared_at is None
    assert await _payment_status(job_id) == "escrowed"


async def test_refund_settles_completed_job_after_buyer_adjudication() -> None:
    """The end-to-end claim: after buyer adjudication the manual refund
    path (and therefore the sweeper) can actually pay the buyer on a
    COMPLETED job — refund_market_job_payment used to refuse it for every
    caller."""
    from unittest.mock import AsyncMock

    from market_service.services.market_service import MarketService

    job_id = await _seed_completed_disputed_job()
    async with get_session_context() as session:
        svc = MarketService(session)
        await svc.resolve_market_job_dispute(job_id, resolution="buyer")
        svc._rpc_client.refund_escrow = AsyncMock(
            return_value={"success": True, "tx_hash": "0xBuyerRefund", "refunded_amount": "1.0"}
        )
        out = await svc.refund_market_job_payment(job_id, reason="dispute adjudicated for buyer")
    assert out["state"] == "REFUNDED"
    assert await _payment_status(job_id) == "refunded"
