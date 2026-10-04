"""Tests for MarketJobSweeper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from aitbc.market import BlockchainRPCClient
from market_service.services.market_job_sweeper import MarketJobSweeper
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context


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
        service = MarketService(session)
        rpc = StubRPC()
        sweeper = MarketJobSweeper(rpc_client=rpc, session_factory=lambda: get_session_context())
        yield service, sweeper, rpc


@pytest.mark.asyncio
async def test_sweeper_releases_expired_job(sweeper) -> None:
    service, sw, rpc = sweeper

    created = await service.create_market_job(
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

    job = await service.get_market_job(created["job_id"])
    assert job["state"] == "RELEASED"
    assert job["payment_status"] == "released"


@pytest.mark.asyncio
async def test_sweeper_refunds_canceled_job(sweeper) -> None:
    service, sw, rpc = sweeper

    created = await service.create_market_job(
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

    job = await service.get_market_job(created["job_id"])
    assert job["state"] == "REFUNDED"
    assert job["payment_status"] == "refunded"


def _rpc_over_mock_transport(monkeypatch: pytest.MonkeyPatch, handler) -> BlockchainRPCClient:
    """A real BlockchainRPCClient whose httpx layer is a MockTransport.

    Same pattern as the coordinator probes in test_release_attempts.py: the
    exercise covers the client's real 404/raise_for_status handling, not a
    stubbed answer.
    """
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    return BlockchainRPCClient(rpc_url="http://testnode")


@pytest.mark.xfail(
    strict=True,
    reason="Task 78 probe: a 404 'escrow not found' is ambiguous (absent vs wrong node vs lag) but goes terminal in one pass",
)
@pytest.mark.asyncio
async def test_release_404_is_not_terminal_yet(sweeper, monkeypatch) -> None:
    """A 404 from the release route must not flip the payment to
    settlement_failed in a single pass — 'the node being asked has no row'
    is not the same as 'no escrow exists'."""
    service, sw, _rpc = sweeper

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"detail": "No escrow contract found for job_id=escrow-lagging"},
            request=request,
        )

    sw._rpc_client = _rpc_over_mock_transport(monkeypatch, handler)

    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "33" * 20,
            "provider_address": "0x" + "44" * 20,
            "escrow_contract_id": "escrow-lagging",
            "state": "COMPLETED",
            "expires_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )

    counts = await sw.sweep_once()
    assert counts["failed"] == 1

    job = await service.get_market_job(created["job_id"])
    # Desired: the row stays escrowed/retryable. Today: settlement_failed.
    assert job["payment_status"] != "settlement_failed"


@pytest.mark.xfail(
    strict=True,
    reason="Task 78 probe: {success:false} means 'rolled back, retry' on the node but goes terminal in one pass",
)
@pytest.mark.asyncio
async def test_refund_unsettled_is_not_terminal_yet(sweeper, monkeypatch) -> None:
    """A 200 {success:false} is the node's rolled-back retryable answer —
    it must not flip the payment to settlement_failed in a single pass."""
    service, sw, _rpc = sweeper

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": False,
                "contract_id": "escrow-unsettled",
                "job_id": "escrow-unsettled",
                "message": "Escrow refund could not be settled on-chain; the buyer was not refunded",
                "refund_tx_hash": None,
            },
            request=request,
        )

    sw._rpc_client = _rpc_over_mock_transport(monkeypatch, handler)

    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "55" * 20,
            "provider_address": "0x" + "66" * 20,
            "escrow_contract_id": "escrow-unsettled",
            "state": "CANCELED",
            "updated_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )

    counts = await sw.sweep_once()
    assert counts["failed"] == 1

    job = await service.get_market_job(created["job_id"])
    # Desired: the row stays escrowed/retryable. Today: settlement_failed.
    assert job["payment_status"] != "settlement_failed"
