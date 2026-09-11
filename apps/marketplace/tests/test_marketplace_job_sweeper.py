"""Tests for MarketplaceJobSweeper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from marketplace_service.domain.marketplace import MarketplaceJob, MarketplaceJobPayment
from marketplace_service.services.marketplace_job_sweeper import MarketplaceJobSweeper
from marketplace_service.services.marketplace_service import MarketplaceService
from marketplace_service.storage import get_session_context


class StubRPC:
    def __init__(self) -> None:
        self.released: list[str] = []
        self.refunded: list[str] = []

    async def release_escrow(self, job_id: str, body: dict | None = None):
        self.released.append(job_id)
        return {"success": True, "tx_hash": f"0xrelease_{job_id}"}

    async def refund_escrow(self, job_id: str, body: dict | None = None):
        self.refunded.append(job_id)
        return {"success": True, "tx_hash": f"0xrefund_{job_id}"}


@pytest.fixture
async def sweeper():
    async with get_session_context() as session:
        service = MarketplaceService(session)
        rpc = StubRPC()
        sweeper = MarketplaceJobSweeper(rpc_client=rpc, session_factory=lambda: get_session_context())
        yield service, sweeper, rpc


@pytest.mark.asyncio
async def test_sweeper_releases_expired_job(sweeper) -> None:
    service, sw, rpc = sweeper

    created = await service.create_marketplace_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "escrow_contract_id": "escrow-expired",
            "state": "COMPLETED",
            "expires_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )

    counts = await sw.sweep_once()
    assert counts["released"] == 1
    assert "escrow-expired" in rpc.released

    job = await service.get_marketplace_job(created["job_id"])
    assert job["state"] == "RELEASED"
    assert job["payment_status"] == "released"


@pytest.mark.asyncio
async def test_sweeper_refunds_canceled_job(sweeper) -> None:
    service, sw, rpc = sweeper

    created = await service.create_marketplace_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "escrow_contract_id": "escrow-canceled",
            "state": "CANCELED",
            "updated_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )

    counts = await sw.sweep_once()
    assert counts["refunded"] == 1
    assert "escrow-canceled" in rpc.refunded

    job = await service.get_marketplace_job(created["job_id"])
    assert job["state"] == "REFUNDED"
    assert job["payment_status"] == "refunded"
