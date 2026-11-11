"""Regression tests — party signatures on market job release/refund (#1784).

A presented wallet signature on ``POST /jobs/{id}/release`` or ``/refund``
must verify AND recover to a job party (buyer or provider) — the same rule
cancel got in #1634. A foreign signer gets 403 and escrow state is
untouched. The unsigned API-key path stays for the operator/sweeper tier.
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio


def _uid() -> str:
    return uuid4().hex[:8]


async def _seed_settle_job(state: str = "RUNNING") -> tuple[str, str, str]:
    """Return (job_id, buyer_private_key, provider_private_key) with an
    escrowed payment — releasable from RUNNING, refundable once CANCELED."""
    from aitbc.crypto.crypto import derive_ethereum_address

    buyer_key, provider_key = "0x" + "11" * 32, "0x" + "22" * 32
    async with get_session_context() as session:
        job_id = f"job_settle_{_uid()}"
        payment = MarketJobPayment(
            job_id=job_id,
            amount=Decimal("1.0"),
            status="escrowed",
            escrowed_at=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(payment)
        await session.flush()
        session.add(
            MarketJob(
                id=job_id,
                buyer_address=derive_ethereum_address(buyer_key),
                provider_address=derive_ethereum_address(provider_key),
                service_type="ipfs",
                state=state,
                offer_id="offer_x",
                payload={},
                payment_id=payment.id,
                payment_status="escrowed",
            )
        )
        await session.commit()
    return job_id, buyer_key, provider_key


def _settle_signature(job_id: str, private_key: str, address: str, route: str) -> dict:
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


@pytest.fixture
def stub_escrow_rpc(monkeypatch: pytest.MonkeyPatch):
    """Stub the on-chain escrow calls the service makes without a tx_hash."""
    from aitbc.market import BlockchainRPCClient

    async def _release(self, job_id: str, body: dict | None = None):
        return {"success": True, "tx_hash": f"0xrelease_{job_id}"}

    async def _refund(self, job_id: str, body: dict | None = None):
        return {"success": True, "tx_hash": f"0xrefund_{job_id}"}

    monkeypatch.setattr(BlockchainRPCClient, "release_escrow", _release)
    monkeypatch.setattr(BlockchainRPCClient, "refund_escrow", _refund)


async def _payment_status(job_id: str) -> tuple[str | None, str | None]:
    """Return (job.state, payment.status) straight from the DB."""
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id) if job and job.payment_id else None
        return (job.state if job else None, payment.status if payment else None)


async def test_party_signed_release_returns_200(stub_escrow_rpc) -> None:
    from aitbc.crypto.crypto import derive_ethereum_address
    from fastapi.testclient import TestClient
    from market_service.main import app

    job_id, buyer_key, _ = await _seed_settle_job()
    proof = _settle_signature(job_id, buyer_key, derive_ethereum_address(buyer_key), f"/v1/market/jobs/{job_id}/release")
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/release", json=proof)
    assert r.status_code == 200
    assert r.json()["state"] == "RELEASED"


async def test_foreign_signed_release_is_403_and_escrow_untouched(stub_escrow_rpc) -> None:
    from aitbc.crypto.crypto import derive_ethereum_address
    from fastapi.testclient import TestClient
    from market_service.main import app

    job_id, _, _ = await _seed_settle_job()
    stranger_key = "0x" + "33" * 32
    proof = _settle_signature(job_id, stranger_key, derive_ethereum_address(stranger_key), f"/v1/market/jobs/{job_id}/release")
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/release", json=proof)
    assert r.status_code == 403

    state, pay_status = await _payment_status(job_id)
    assert state == "RUNNING"
    assert pay_status == "escrowed"


async def test_unsigned_release_api_key_path_still_works(stub_escrow_rpc) -> None:
    from fastapi.testclient import TestClient
    from market_service.main import app

    job_id, _, _ = await _seed_settle_job()
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/release", json={})
    assert r.status_code == 200
    assert r.json()["state"] == "RELEASED"


async def test_party_signed_refund_returns_200(stub_escrow_rpc) -> None:
    from aitbc.crypto.crypto import derive_ethereum_address
    from fastapi.testclient import TestClient
    from market_service.main import app

    job_id, _, provider_key = await _seed_settle_job(state="CANCELED")
    proof = _settle_signature(job_id, provider_key, derive_ethereum_address(provider_key), f"/v1/market/jobs/{job_id}/refund")
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/refund", json={"reason": "cancelled", **proof})
    assert r.status_code == 200
    assert r.json()["state"] == "REFUNDED"


async def test_foreign_signed_refund_is_403_and_escrow_untouched(stub_escrow_rpc) -> None:
    from aitbc.crypto.crypto import derive_ethereum_address
    from fastapi.testclient import TestClient
    from market_service.main import app

    job_id, _, _ = await _seed_settle_job(state="CANCELED")
    stranger_key = "0x" + "33" * 32
    proof = _settle_signature(job_id, stranger_key, derive_ethereum_address(stranger_key), f"/v1/market/jobs/{job_id}/refund")
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/refund", json={"reason": "sabotage", **proof})
    assert r.status_code == 403

    state, pay_status = await _payment_status(job_id)
    assert state == "CANCELED"
    assert pay_status == "escrowed"


async def test_unsigned_refund_api_key_path_still_works(stub_escrow_rpc) -> None:
    from fastapi.testclient import TestClient
    from market_service.main import app

    job_id, _, _ = await _seed_settle_job(state="CANCELED")
    with TestClient(app) as client:
        r = client.post(f"/v1/market/jobs/{job_id}/refund", json={"reason": "cancelled"})
    assert r.status_code == 200
    assert r.json()["state"] == "REFUNDED"
