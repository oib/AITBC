"""Tests for MarketplaceJob / MarketplaceJobPayment lifecycle."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import SQLModel

from marketplace_service.domain.marketplace import MarketplaceJob, MarketplaceJobPayment
from marketplace_service.services.marketplace_service import MarketplaceService
from marketplace_service.storage import get_session_context


@pytest.fixture
async def service() -> MarketplaceService:
    async with get_session_context() as session:
        yield MarketplaceService(session)


@pytest.mark.asyncio
async def test_create_marketplace_job(service: MarketplaceService) -> None:
    result = await service.create_marketplace_job(
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
    assert result["payment_status"] == "escrowed"


@pytest.mark.asyncio
async def test_get_marketplace_job(service: MarketplaceService) -> None:
    created = await service.create_marketplace_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "payload": {"cid": "QmTest", "size": 100},
            "payment": {"amount": "0.1", "status": "pending"},
        }
    )

    fetched = await service.get_marketplace_job(created["job_id"])
    assert fetched
    assert fetched["job_id"] == created["job_id"]
    assert fetched["payment"]["status"] == "pending"


@pytest.mark.asyncio
async def test_confirm_and_release_payment(service: MarketplaceService) -> None:
    """Confirm pin, then release payment; uses a stub RPC client."""

    class StubRPC:
        async def release_escrow(self, job_id: str, body: dict | None = None):
            return {"success": True, "tx_hash": f"0xrelease_{job_id}"}

    service._rpc_client = StubRPC()  # type: ignore[assignment]

    created = await service.create_marketplace_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "escrow_contract_id": "escrow-123",
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "pending"},
        }
    )

    await service.confirm_marketplace_job_pin(created["job_id"], size=100)
    fetched = await service.get_marketplace_job(created["job_id"])
    assert fetched["state"] == "RUNNING"

    released = await service.release_marketplace_job_payment(created["job_id"])
    assert released["state"] == "RELEASED"
    assert released["payment_status"] == "released"
    assert released["tx_hash"] == "0xrelease_escrow-123"


@pytest.mark.asyncio
async def test_cancel_and_refund(service: MarketplaceService) -> None:
    class StubRPC:
        async def refund_escrow(self, job_id: str, body: dict | None = None):
            return {"success": True, "tx_hash": f"0xrefund_{job_id}"}

    service._rpc_client = StubRPC()  # type: ignore[assignment]

    created = await service.create_marketplace_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "escrow_contract_id": "escrow-456",
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )

    canceled = await service.cancel_marketplace_job(created["job_id"], reason="test")
    assert canceled["state"] == "CANCELED"
    assert canceled["payment_status"] == "refund_pending"

    refunded = await service.refund_marketplace_job_payment(created["job_id"])
    assert refunded["state"] == "REFUNDED"
    assert refunded["payment_status"] == "refunded"
    assert refunded["refund_tx_hash"] == "0xrefund_escrow-456"
