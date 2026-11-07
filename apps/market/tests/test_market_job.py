"""Tests for MarketJob / MarketJobPayment lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context


@pytest.fixture
async def service() -> MarketService:
    async with get_session_context() as session:
        yield MarketService(session)


async def _mark_escrowed(service: MarketService, job_id: str, escrow_contract_id: str) -> None:
    """Drive the lifecycle fields the payment path owns.

    ``create_market_job`` deliberately ignores caller-supplied state,
    escrow_contract_id and payment.status (#815) — tests that need an
    escrowed job set those columns directly, the way settlement does.
    """
    job = await service.session.get(MarketJob, job_id)
    assert job is not None
    job.escrow_contract_id = escrow_contract_id
    job.payment_status = "escrowed"
    payment = await service.session.get(MarketJobPayment, job.payment_id)
    assert payment is not None
    payment.status = "escrowed"
    payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
    service.session.add_all([job, payment])
    await service.session.commit()


@pytest.mark.asyncio
async def test_create_market_job(service: MarketService) -> None:
    result = await service.create_market_job(
        {
            "service_type": "ipfs",
            "model": "ipfs-host",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "offer_id": "offer-1",
            "plugin_id": "ipfs-ipfs-host",
            "state": "QUEUED",
            "payload": {"cid": "QmTest123", "size": 1024, "access_key": "ak"},
            "payment": {
                "amount": "1.5",
                "status": "escrowed",
            },
        }
    )

    assert result["job_id"]
    assert result["service_type"] == "ipfs"
    assert Decimal(result["payment"]["amount"]) == Decimal("1.5")
    # #815: caller-supplied state/payment.status are ignored — lifecycle is
    # service-owned, so a fresh job is always pending regardless of input.
    assert result["payment_status"] == "pending"


@pytest.mark.asyncio
async def test_get_market_job(service: MarketService) -> None:
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "payload": {"cid": "QmTest", "size": 100},
            "payment": {"amount": "0.1", "status": "pending"},
        }
    )

    fetched = await service.get_market_job(created["job_id"])
    assert fetched
    assert fetched["job_id"] == created["job_id"]
    assert fetched["payment"]["status"] == "pending"


@pytest.mark.asyncio
async def test_confirm_and_release_payment(service: MarketService) -> None:
    """Confirm pin, then release payment; uses a stub RPC client."""

    class StubRPC:
        async def release_escrow(self, job_id: str, body: dict | None = None):
            return {"success": True, "tx_hash": f"0xrelease_{job_id}"}

    service._rpc_client = StubRPC()  # type: ignore[assignment]

    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "escrow_contract_id": "escrow-123",
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "pending"},
        }
    )
    await _mark_escrowed(service, created["job_id"], "escrow-123")

    await service.confirm_market_job_pin(created["job_id"], size=100)
    fetched = await service.get_market_job(created["job_id"])
    assert fetched["state"] == "RUNNING"
    # payload is a plain JSON column: pin-confirm must reassign it, or the
    # mutation is silently dropped at commit.
    assert fetched["payload"]["pinned"] is True
    assert fetched["payload"]["size"] == 100

    released = await service.release_market_job_payment(created["job_id"])
    assert released["state"] == "RELEASED"
    assert released["payment_status"] == "released"
    assert released["tx_hash"] == "0xrelease_escrow-123"


@pytest.mark.asyncio
async def test_cancel_and_refund(service: MarketService) -> None:
    class StubRPC:
        async def refund_escrow(self, job_id: str, body: dict | None = None):
            return {"success": True, "tx_hash": f"0xrefund_{job_id}"}

    service._rpc_client = StubRPC()  # type: ignore[assignment]

    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "escrow_contract_id": "escrow-456",
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )
    await _mark_escrowed(service, created["job_id"], "escrow-456")

    canceled = await service.cancel_market_job(created["job_id"], reason="test")
    assert canceled["state"] == "CANCELED"
    assert canceled["payment_status"] == "refund_pending"

    refunded = await service.refund_market_job_payment(created["job_id"])
    assert refunded["state"] == "REFUNDED"
    assert refunded["payment_status"] == "refunded"
    assert refunded["refund_tx_hash"] == "0xrefund_escrow-456"


@pytest.mark.asyncio
async def test_confirm_pin_persists_provider_confirmed(service: MarketService) -> None:
    """provider_confirmed must land in the persisted payload.

    Regression test: job.payload is a plain ``Column(JSON)`` -- mutating the
    dict in place never reaches the database, so the provider's pin-confirm was
    accepted (200) but the flag silently vanished.
    """

    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "payload": {"cid": "QmTest", "size": 10},
            "payment": {"amount": "0.1", "status": "escrowed"},
        }
    )

    await service.confirm_market_job_pin(created["job_id"], provider_confirmed=True)

    fetched = await service.get_market_job(created["job_id"])
    assert fetched["state"] == "RUNNING"
    assert fetched["payload"]["provider_confirmed"] is True
