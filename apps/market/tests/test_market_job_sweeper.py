"""Tests for MarketJobSweeper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from aitbc.market import BlockchainRPCClient
from market_service.domain.market import MarketJobPayment
from market_service.services.market_job_sweeper import MarketJobSweeper
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context
from sqlmodel import col, select


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


async def _payment_of(job_id: str) -> MarketJobPayment:
    async with get_session_context() as session:
        result = await session.execute(select(MarketJobPayment).where(col(MarketJobPayment.job_id) == job_id))
        return result.scalar_one()


@pytest.mark.asyncio
async def test_release_404_is_not_terminal_yet(sweeper, monkeypatch) -> None:
    """A 404 from the release route defers: 'the node being asked has no
    row' is not the same as 'no escrow exists'."""
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
    assert counts["failed"] >= 1

    job = await service.get_market_job(created["job_id"])
    assert job["payment_status"] == "escrowed"
    payment = await _payment_of(created["job_id"])
    assert payment.status == "escrowed"
    assert payment.meta_data["settle_deferral_first_at"]


@pytest.mark.asyncio
async def test_refund_unsettled_is_not_terminal_yet(sweeper, monkeypatch) -> None:
    """A 200 {success:false} is the node's rolled-back retryable answer —
    it defers instead of going terminal in one pass."""
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
    assert counts["failed"] >= 1

    job = await service.get_market_job(created["job_id"])
    assert job["payment_status"] == "escrowed"
    payment = await _payment_of(created["job_id"])
    assert payment.meta_data["settle_deferral_first_at"]


@pytest.mark.unit
class TestSettleDeferralBound:
    """The deferral bound and the confirming read at its end.

    Falsy answers (404, {success:false}) and raised errors all defer through
    the same marker; past MARKET_JOB_SWEEP_SETTLE_MAX_SECONDS one GET read
    decides: absent -> terminal, released/refunded -> verdict adopted,
    anything else -> keep deferring.
    """

    def _settle_verify_transport(self, monkeypatch, settle_items, verify):
        """MockTransport: POSTs serve settle_items (callables or Exceptions,
        clamped at the last item); GETs serve the verify answer."""
        state = {"posts": 0, "gets": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                state["gets"] += 1
                if isinstance(verify, Exception):
                    raise verify
                return verify(request)
            item = settle_items[min(state["posts"], len(settle_items) - 1)]
            state["posts"] += 1
            if isinstance(item, Exception):
                raise item
            return item(request)

        transport = httpx.MockTransport(handler)
        real_async_client = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs["transport"] = transport
            return real_async_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", client_factory)
        return state

    @staticmethod
    def _post404(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"detail": "No escrow contract found"},
            request=request,
        )

    @staticmethod
    def _post_unsettled(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "message": "could not be settled on-chain", "tx_hash": None},
            request=request,
        )

    async def _deferred_job(self, service, job_suffix, meta):
        created = await service.create_market_job(
            {
                "service_type": "ipfs",
                "buyer_address": "0x" + "77" * 20,
                "provider_address": "0x" + "88" * 20,
                "escrow_contract_id": f"escrow-{job_suffix}",
                "state": "COMPLETED",
                "expires_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                "payload": {"cid": "QmTest"},
                "payment": {"amount": "1.0", "status": "escrowed", "meta_data": meta},
            }
        )
        return created["job_id"]

    async def test_past_bound_absent_escrow_goes_terminal(self, sweeper, monkeypatch) -> None:
        service, sw, _rpc = sweeper

        def verify_404(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"detail": "No escrow found"}, request=request)

        self._settle_verify_transport(monkeypatch, [self._post404], verify_404)
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "pastabs", {"settle_deferral_first_at": first_at})

        counts = await sw.sweep_once()
        assert counts["failed"] >= 1

        job = await service.get_market_job(job_id)
        assert job["payment_status"] == "settlement_failed"
        payment = await _payment_of(job_id)
        assert payment.status == "settlement_failed"
        assert "settle_deferral_first_at" not in (payment.meta_data or {})

    async def test_past_bound_locked_escrow_keeps_deferring(self, sweeper, monkeypatch) -> None:
        service, sw, _rpc = sweeper

        def verify_locked(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"state": "locked", "release_tx_hash": None, "refund_tx_hash": None},
                request=request,
            )

        self._settle_verify_transport(monkeypatch, [self._post_unsettled], verify_locked)
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "pastlock", {"settle_deferral_first_at": first_at})

        counts = await sw.sweep_once()
        assert counts["failed"] >= 1

        job = await service.get_market_job(job_id)
        assert job["payment_status"] == "escrowed"
        payment = await _payment_of(job_id)
        assert payment.meta_data["settle_deferral_first_at"] == first_at

    async def test_past_bound_settled_escrow_adopts_the_verdict(self, sweeper, monkeypatch) -> None:
        service, sw, _rpc = sweeper

        def verify_released(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"state": "released", "release_tx_hash": "0xsealed-by-other-path"},
                request=request,
            )

        self._settle_verify_transport(monkeypatch, [self._post_unsettled], verify_released)
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "pastverdict", {"settle_deferral_first_at": first_at})

        counts = await sw.sweep_once()
        assert counts["released"] >= 1

        job = await service.get_market_job(job_id)
        assert job["state"] == "RELEASED"
        assert job["payment_status"] == "released"
        assert job["tx_hash"] == "0xsealed-by-other-path"
        payment = await _payment_of(job_id)
        assert "settle_deferral_first_at" not in (payment.meta_data or {})

    async def test_raised_error_defers_through_the_same_marker(self, sweeper, monkeypatch) -> None:
        """The inverse defect: raised errors (a 500 here) used to retry
        forever and silently -- now they share the bounded deferral."""
        service, sw, _rpc = sweeper

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "node exploded"}, request=request)

        sw._rpc_client = _rpc_over_mock_transport(monkeypatch, handler)
        job_id = await self._deferred_job(service, "raised", None)

        counts = await sw.sweep_once()
        assert counts["failed"] >= 1

        job = await service.get_market_job(job_id)
        assert job["payment_status"] == "escrowed"
        payment = await _payment_of(job_id)
        assert payment.meta_data["settle_deferral_first_at"]

    async def test_raised_error_past_bound_uses_the_same_read(self, sweeper, monkeypatch) -> None:
        service, sw, _rpc = sweeper

        def settle500(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "node exploded"}, request=request)

        def verify_404(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"detail": "No escrow found"}, request=request)

        self._settle_verify_transport(monkeypatch, [settle500], verify_404)
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "raisedpast", {"settle_deferral_first_at": first_at})

        counts = await sw.sweep_once()
        assert counts["failed"] >= 1
        job = await service.get_market_job(job_id)
        assert job["payment_status"] == "settlement_failed"

    async def test_success_clears_the_deferral_marker(self, sweeper, monkeypatch) -> None:
        service, sw, _rpc = sweeper

        def settle200(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"success": True, "tx_hash": "0xlanded"},
                request=request,
            )

        self._settle_verify_transport(monkeypatch, [settle200], settle200)
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "succlear", {"settle_deferral_first_at": first_at})

        counts = await sw.sweep_once()
        assert counts["released"] >= 1

        payment = await _payment_of(job_id)
        assert payment.status == "released"
        assert "settle_deferral_first_at" not in (payment.meta_data or {})
