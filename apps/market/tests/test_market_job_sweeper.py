"""Tests for MarketJobSweeper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from aitbc.market import BlockchainRPCClient
from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.services.market_job_sweeper import META_SETTLE_DEFERRAL_FIRST_AT, MarketJobSweeper
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context
from sqlmodel import col, select


class StubRPC:
    def __init__(self) -> None:
        self.released: list[str] = []
        self.refunded: list[str] = []
        self.escrow_rows: dict[str, dict] = {}
        self.lock_txs: dict[str, str] = {}
        self.omit_tx_hash = False

    async def verify_escrow(self, job_id: str):
        return self.escrow_rows.get(job_id)

    async def find_escrow_lock(self, job_id: str):
        return self.lock_txs.get(job_id)

    async def release_escrow(self, job_id: str, body: dict | None = None):
        self.released.append(job_id)
        return {"success": True, "tx_hash": None if self.omit_tx_hash else f"0xrelease_{job_id}"}

    async def refund_escrow(self, job_id: str, body: dict | None = None):
        self.refunded.append(job_id)
        return {"success": True, "tx_hash": None if self.omit_tx_hash else f"0xrefund_{job_id}"}


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
            "expires_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )
    await _apply_lifecycle(created["job_id"], state="COMPLETED", escrow_contract_id="escrow-expired")

    counts = await sw.sweep_once()
    assert counts["released"] == 1
    # #1564: the escrow path key is the market job id, not escrow_contract_id.
    assert created["job_id"] in rpc.released

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
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )
    await _apply_lifecycle(
        created["job_id"],
        state="CANCELED",
        escrow_contract_id="escrow-canceled",
        updated_at=(datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None),
    )

    counts = await sw.sweep_once()
    assert counts["refunded"] == 1
    # #1564: the escrow path key is the market job id, not escrow_contract_id.
    assert created["job_id"] in rpc.refunded

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


async def _apply_lifecycle(
    job_id: str,
    *,
    state: str,
    escrow_contract_id: str,
    updated_at: datetime | None = None,
    provider_confirmed: bool = False,
) -> None:
    """Set the lifecycle columns the payment path owns.

    ``create_market_job`` ignores caller-supplied state, escrow_contract_id,
    updated_at and payment.status (#815) — sweeper fixtures drive those
    columns directly, the way settlement would have left them.
    ``provider_confirmed`` models the #1922 provider-signed pin-confirm
    payload flag (#2491).
    """
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        job.state = state
        job.escrow_contract_id = escrow_contract_id
        job.payment_status = "escrowed"
        if provider_confirmed:
            payload = dict(job.payload or {})
            payload["provider_confirmed"] = True
            job.payload = payload
        if updated_at is not None:
            job.updated_at = updated_at
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        payment.status = "escrowed"
        payment.escrowed_at = datetime.now(UTC).replace(tzinfo=None)
        payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add_all([job, payment])
        await session.commit()


async def _age_job(job_id: str) -> None:
    """Backdate job.updated_at past the sweeper min_age gate."""
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        job.updated_at = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
        session.add(job)
        await session.commit()


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
            "expires_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )
    await _apply_lifecycle(created["job_id"], state="COMPLETED", escrow_contract_id="escrow-lagging")

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
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )
    await _apply_lifecycle(
        created["job_id"],
        state="CANCELED",
        escrow_contract_id="escrow-unsettled",
        updated_at=(datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None),
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

    @staticmethod
    def _sealed_lock_tx(request: httpx.Request) -> httpx.Response:
        # Echo the queried job_id — find_escrow_lock re-checks payload.job_id.
        return httpx.Response(
            200,
            json=[
                {
                    "tx_hash": "0xlock_sealed",
                    "block_height": 33900,
                    "payload": {"job_id": request.url.params.get("job_id", ""), "action": "escrow_lock"},
                }
            ],
            request=request,
        )

    def _settle_verify_transport(self, monkeypatch, settle_items, verify, tx=None, locks=None):
        """MockTransport: POSTs serve settle_items (callables or Exceptions,
        clamped at the last item); GETs dispatch on path -- /rpc/escrow/
        serves the verify answer, /rpc/transaction/ serves the tx answer
        (default: a sealed transaction, so adoption tests stay adoptions),
        /rpc/transactions serves the ESCROW_LOCK lookup (default: one
        sealed lock, so locked-escrow tests keep deferring)."""
        state = {"posts": 0, "gets": 0}
        if tx is None:
            tx = self._sealed_tx
        if locks is None:
            locks = self._sealed_lock_tx

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                state["gets"] += 1
                if request.url.path.startswith("/rpc/transactions"):
                    answer = locks
                elif request.url.path.startswith("/rpc/transaction/"):
                    answer = tx
                else:
                    answer = verify
                if isinstance(answer, Exception):
                    raise answer
                return answer(request)
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

    @staticmethod
    def _sealed_tx(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "tx_hash": request.url.path.rsplit("/", 1)[-1],
                "block_height": 34100,
                "status": "sealed",
            },
            request=request,
        )

    async def _deferred_job(self, service, job_suffix, meta, *, refund: bool = False):
        data: dict = {
            "service_type": "ipfs",
            "buyer_address": "0x" + "77" * 20,
            "provider_address": "0x" + "88" * 20,
            "escrow_contract_id": f"escrow-{job_suffix}",
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed", "meta_data": meta},
        }
        if not refund:
            data["expires_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        created = await service.create_market_job(data)
        await _apply_lifecycle(
            created["job_id"],
            state="CANCELED" if refund else "COMPLETED",
            escrow_contract_id=f"escrow-{job_suffix}",
            updated_at=(datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None) if refund else None,
        )
        return created["job_id"]

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @staticmethod
    def _no_lock_tx(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], request=request)

    @staticmethod
    def _other_job_lock_tx(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "tx_hash": "0xlock_other",
                    "block_height": 33900,
                    "payload": {"job_id": "sw_job_other", "action": "escrow_lock"},
                }
            ],
            request=request,
        )

    @pytest.mark.asyncio
    async def test_past_bound_phantom_escrow_goes_terminal(self, sweeper, monkeypatch) -> None:
        """#2386: escrow row reads locked but no sealed ESCROW_LOCK exists —
        the lock tx never landed, no money moved: terminal, not forever-defer."""
        service, sw, _rpc = sweeper

        def verify_locked(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"state": "locked", "release_tx_hash": None, "refund_tx_hash": None},
                request=request,
            )

        self._settle_verify_transport(monkeypatch, [self._post_unsettled], verify_locked, locks=self._no_lock_tx)
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "phantom", {"settle_deferral_first_at": first_at})

        counts = await sw.sweep_once()
        assert counts["failed"] >= 1

        job = await service.get_market_job(job_id)
        assert job["payment_status"] == "settlement_failed"
        assert "no sealed ESCROW_LOCK" in (job.get("error") or "")
        payment = await _payment_of(job_id)
        assert payment.status == "settlement_failed"
        assert "settle_deferral_first_at" not in (payment.meta_data or {})

    @pytest.mark.asyncio
    async def test_past_bound_lock_for_other_job_is_phantom(self, sweeper, monkeypatch) -> None:
        """A sealed lock belonging to a different job_id does not save this one."""
        service, sw, _rpc = sweeper

        def verify_locked(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"state": "funded", "release_tx_hash": None, "refund_tx_hash": None},
                request=request,
            )

        self._settle_verify_transport(monkeypatch, [self._post_unsettled], verify_locked, locks=self._other_job_lock_tx)
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "otherjob", {"settle_deferral_first_at": first_at})

        counts = await sw.sweep_once()
        assert counts["failed"] >= 1

        job = await service.get_market_job(job_id)
        assert job["payment_status"] == "settlement_failed"

    @pytest.mark.asyncio
    async def test_past_bound_lock_probe_error_keeps_deferring(self, sweeper, monkeypatch) -> None:
        """A failed lock lookup is 'unknown', never 'absent' — keep deferring."""
        service, sw, _rpc = sweeper

        def verify_locked(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"state": "locked", "release_tx_hash": None, "refund_tx_hash": None},
                request=request,
            )

        self._settle_verify_transport(
            monkeypatch,
            [self._post_unsettled],
            verify_locked,
            locks=httpx.ConnectError("lock probe down"),
        )
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "probefail", {"settle_deferral_first_at": first_at})

        counts = await sw.sweep_once()
        assert counts["failed"] >= 1

        job = await service.get_market_job(job_id)
        assert job["payment_status"] == "escrowed"
        payment = await _payment_of(job_id)
        assert payment.meta_data["settle_deferral_first_at"] == first_at

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_past_bound_verdict_without_hash_keeps_deferring(self, sweeper, monkeypatch) -> None:
        """A row that says 'released' but carries no release hash is the S-8
        dead-hash shape -- never adopt 'settled' from it."""
        service, sw, _rpc = sweeper

        def verify_hashless(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"state": "released", "release_tx_hash": None},
                request=request,
            )

        self._settle_verify_transport(monkeypatch, [self._post_unsettled], verify_hashless)
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "hashless", {"settle_deferral_first_at": first_at})

        counts = await sw.sweep_once()
        assert counts["failed"] >= 1

        job = await service.get_market_job(job_id)
        assert job["payment_status"] == "escrowed"
        payment = await _payment_of(job_id)
        assert payment.meta_data["settle_deferral_first_at"] == first_at

    @pytest.mark.asyncio
    async def test_refund_intended_released_verdict_still_adopts(self, sweeper, monkeypatch) -> None:
        """Kind mismatch, refund sweep sees 'released': reality wins -- the
        row is authoritative for where the money went, so the verdict is
        adopted (with an error log naming both kinds)."""
        service, sw, _rpc = sweeper

        def verify_released(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"state": "released", "release_tx_hash": "0xpaid-anyway"},
                request=request,
            )

        self._settle_verify_transport(monkeypatch, [self._post_unsettled], verify_released)
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "mix-rl", {"settle_deferral_first_at": first_at}, refund=True)

        await sw.sweep_once()

        job = await service.get_market_job(job_id)
        assert job["state"] == "RELEASED"
        assert job["payment_status"] == "released"
        assert job["tx_hash"] == "0xpaid-anyway"

    @pytest.mark.asyncio
    async def test_release_intended_refunded_verdict_still_adopts(self, sweeper, monkeypatch) -> None:
        """Kind mismatch, release sweep sees 'refunded': same rule -- adopt
        the row's verdict rather than strand a settled escrow."""
        service, sw, _rpc = sweeper

        def verify_refunded(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"state": "refunded", "refund_tx_hash": "0xreturned"},
                request=request,
            )

        self._settle_verify_transport(monkeypatch, [self._post_unsettled], verify_refunded)
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "mix-rf", {"settle_deferral_first_at": first_at})

        await sw.sweep_once()

        job = await service.get_market_job(job_id)
        assert job["state"] == "REFUNDED"
        assert job["payment_status"] == "refunded"
        assert job["refund_tx_hash"] == "0xreturned"

    @pytest.mark.asyncio
    async def test_past_bound_verdict_with_unsealed_hash_keeps_deferring(self, sweeper, monkeypatch) -> None:
        """The S-8 dead-hash shape made stronger: the row names a hash but
        the chain has it with no block height -- never adopted."""
        service, sw, _rpc = sweeper

        def verify_released(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"state": "released", "release_tx_hash": "0xnever-sealed"},
                request=request,
            )

        def tx_unsealed(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"tx_hash": "0xnever-sealed", "block_height": None, "status": "pending"},
                request=request,
            )

        self._settle_verify_transport(monkeypatch, [self._post_unsettled], verify_released, tx=tx_unsealed)
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "unsealed", {"settle_deferral_first_at": first_at})

        counts = await sw.sweep_once()
        assert counts["failed"] >= 1

        job = await service.get_market_job(job_id)
        assert job["payment_status"] == "escrowed"
        payment = await _payment_of(job_id)
        assert payment.meta_data["settle_deferral_first_at"] == first_at

    @pytest.mark.asyncio
    async def test_past_bound_verdict_with_unfound_hash_keeps_deferring(self, sweeper, monkeypatch) -> None:
        """A hash the chain does not have at all is the other dead-hash
        shape -- 404 on the lookup, keep deferring."""
        service, sw, _rpc = sweeper

        def verify_refunded(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"state": "refunded", "refund_tx_hash": "0xghost"},
                request=request,
            )

        def tx_404(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"detail": "Transaction 0xghost not found"}, request=request)

        self._settle_verify_transport(monkeypatch, [self._post_unsettled], verify_refunded, tx=tx_404)
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "ghosttx", {"settle_deferral_first_at": first_at})

        counts = await sw.sweep_once()
        assert counts["failed"] >= 1

        job = await service.get_market_job(job_id)
        assert job["payment_status"] == "escrowed"
        payment = await _payment_of(job_id)
        assert payment.meta_data["settle_deferral_first_at"] == first_at

    @pytest.mark.asyncio
    async def test_past_bound_verdict_hash_lookup_error_keeps_deferring(self, sweeper, monkeypatch) -> None:
        """A failed tx lookup must not be read as 'unsealed' -- an unreadable
        chain is evidence of nothing, so defer rather than adopt or fail."""
        service, sw, _rpc = sweeper

        def verify_released(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"state": "released", "release_tx_hash": "0xmaybe"},
                request=request,
            )

        self._settle_verify_transport(
            monkeypatch,
            [self._post_unsettled],
            verify_released,
            tx=httpx.ReadTimeout("node unreachable"),
        )
        sw._rpc_client = BlockchainRPCClient(rpc_url="http://testnode")

        first_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        job_id = await self._deferred_job(service, "txlookup-err", {"settle_deferral_first_at": first_at})

        counts = await sw.sweep_once()
        assert counts["failed"] >= 1

        job = await service.get_market_job(job_id)
        assert job["payment_status"] == "escrowed"
        payment = await _payment_of(job_id)
        assert payment.meta_data["settle_deferral_first_at"] == first_at


async def _set_dispute(job_id: str, *, disputed: bool = True, cleared: bool = False) -> None:
    """Drive the dispute columns the way the dispute/resolve routes would."""
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        now = datetime.now(UTC).replace(tzinfo=None)
        if disputed:
            job.disputed_at = now
            job.dispute_reason = "test dispute"
            job.dispute_cleared_at = now if cleared else None
        session.add(job)
        await session.commit()


@pytest.mark.asyncio
async def test_disputed_job_skips_release_and_refund(sweeper) -> None:
    """#1783: an open dispute freezes both settlement passes."""
    service, sw, rpc = sweeper

    released_job = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "escrow_contract_id": "escrow-disp-rel",
            "expires_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )
    await _apply_lifecycle(released_job["job_id"], state="COMPLETED", escrow_contract_id="escrow-disp-rel")
    await _set_dispute(released_job["job_id"])

    refunded_job = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "escrow_contract_id": "escrow-disp-ref",
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )
    await _apply_lifecycle(
        refunded_job["job_id"],
        state="CANCELED",
        escrow_contract_id="escrow-disp-ref",
        updated_at=(datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None),
    )
    await _set_dispute(refunded_job["job_id"])

    counts = await sw.sweep_once()
    assert released_job["job_id"] not in rpc.released
    assert refunded_job["job_id"] not in rpc.refunded
    assert counts["disputed_frozen"] >= 2  # other suites may leave open disputes in the shared test DB

    # Resolve both — the next sweep settles them normally. Resolve bumps
    # job.updated_at, so age it past the sweeper's min_age gate first (the
    # freeze semantics are what matter, not the 60s debounce).
    await service.resolve_market_job_dispute(released_job["job_id"])
    await service.resolve_market_job_dispute(refunded_job["job_id"])
    await _age_job(released_job["job_id"])
    await _age_job(refunded_job["job_id"])
    counts = await sw.sweep_once()
    assert released_job["job_id"] in rpc.released
    assert refunded_job["job_id"] in rpc.refunded


@pytest.mark.asyncio
async def test_cleared_dispute_does_not_freeze(sweeper) -> None:
    """#1783: a resolved dispute must not freeze settlement forever."""
    service, sw, rpc = sweeper
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "escrow_contract_id": "escrow-disp-clr",
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )
    await _apply_lifecycle(
        created["job_id"],
        state="CANCELED",
        escrow_contract_id="escrow-disp-clr",
        updated_at=(datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None),
    )
    await _set_dispute(created["job_id"], cleared=True)

    await sw.sweep_once()
    # The pin is the refund itself — disputed_frozen counts every open
    # dispute in the shared test DB, so an exact zero is not assertable here.
    assert created["job_id"] in rpc.refunded


@pytest.mark.asyncio
async def test_sweeper_adopts_locked_pending_payment(sweeper) -> None:
    """#2348: a pending payment whose on-chain escrow is locked flips to
    escrowed — the legacy direct-lock path where pin-confirm raced the
    seal must not orphan the lock."""
    service, sw, rpc = sweeper
    buyer = "0x" + "11" * 20
    provider = "0x" + "22" * 20
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": buyer,
            "provider_address": provider,
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0"},
        }
    )
    job_id = created["job_id"]
    rpc.escrow_rows[job_id] = {"state": "locked", "amount": "1.0", "buyer": buyer, "provider": provider}

    counts = await sw.sweep_once()
    assert counts["adopted"] == 1

    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment.status == "escrowed"
        assert payment.escrowed_at is not None
        assert job.payment_status == "escrowed"


@pytest.mark.asyncio
async def test_sweeper_does_not_adopt_unlocked_or_mismatched_escrow(sweeper) -> None:
    """#2348: adoption requires the same locked-state/amount/party proof as
    pin-confirm — an absent, unlocked or foreign escrow stays pending."""
    service, sw, rpc = sweeper
    buyer = "0x" + "11" * 20
    provider = "0x" + "22" * 20
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": buyer,
            "provider_address": provider,
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0"},
        }
    )
    job_id = created["job_id"]
    # Unlocked state -> no adoption.
    rpc.escrow_rows[job_id] = {"state": "created", "amount": "1.0", "buyer": buyer, "provider": provider}
    counts = await sw.sweep_once()
    assert counts["adopted"] == 0
    # Wrong amount -> no adoption.
    rpc.escrow_rows[job_id] = {"state": "locked", "amount": "2.0", "buyer": buyer, "provider": provider}
    counts = await sw.sweep_once()
    assert counts["adopted"] == 0
    # Foreign buyer -> no adoption.
    rpc.escrow_rows[job_id] = {"state": "locked", "amount": "1.0", "buyer": "0x" + "33" * 20, "provider": provider}
    counts = await sw.sweep_once()
    assert counts["adopted"] == 0

    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment.status == "pending"


@pytest.mark.asyncio
async def test_expired_job_with_rental_token_keeps_escrow(sweeper) -> None:
    """#2348/#2491: an expired ipfs job covered by an active IpfsRentalToken
    does not refund — but only once the provider's signed pin-confirm has
    proven delivery (``provider_confirmed``). The job still expires so
    access ends."""
    from market_service.domain.market import IpfsRentalToken

    service, sw, rpc = sweeper
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
            "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        }
    )
    job_id = created["job_id"]
    await _apply_lifecycle(job_id, state="RUNNING", escrow_contract_id=job_id, provider_confirmed=True)
    async with get_session_context() as session:
        session.add(
            IpfsRentalToken(
                access_key="ak-test-2348",
                access_secret="hashed-secret",
                rental_id=job_id,
                cid="QmTest",
                status="active",
                expires_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        await session.commit()

    counts = await sw.sweep_once()
    assert counts["refunded"] == 0
    assert job_id not in rpc.refunded

    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert job.state == "EXPIRED"
        assert payment.status == "escrowed"

    # Once the token leaves 'active' the normal refund path resumes.
    async with get_session_context() as session:
        token = await session.get(IpfsRentalToken, "ak-test-2348")
        token.status = "released"
        session.add(token)
        await session.commit()
    await _age_job(job_id)
    counts = await sw.sweep_once()
    assert job_id in rpc.refunded


def _rental_token_signature(
    job_id: str,
    cid: str,
    buyer_address: str,
    provider_address: str,
    private_key: str,
    signer_address: str,
) -> dict:
    """#2491: provider-signed rental-token registration proof."""
    import time

    from aitbc.crypto.crypto import sign_transaction_data
    from aitbc.market.job_request_signature import jobs_request_message
    from aitbc.utils.chain_id import resolve_chain_id
    from market_service.config import settings

    chain_id = settings.default_chain_id or resolve_chain_id()
    issued_at = int(time.time())
    binding = {
        "rental_id": job_id,
        "cid": cid,
        "buyer_address": buyer_address,
        "provider_address": provider_address,
    }
    return {
        "signer_address": signer_address,
        "chain_id": chain_id,
        "issued_at": issued_at,
        "signature": sign_transaction_data(
            jobs_request_message(signer_address, chain_id, issued_at, "/v1/market/ipfs/rental-token", binding=binding),
            private_key,
        ),
    }


@pytest.mark.asyncio
async def test_register_ipfs_rental_token_derives_expires_at(sweeper) -> None:
    """#2348: token registration inherits the market job's expires_at — the
    writable allowlist strips caller-supplied settlement fields, so without
    the derivation the token would never expire. #2491: a job-bound
    registration carries the provider's wallet signature."""
    from aitbc.crypto.crypto import derive_ethereum_address

    service, _sw, _rpc = sweeper
    provider_key = "0x" + "22" * 32
    provider_address = derive_ethereum_address(provider_key)
    buyer_address = derive_ethereum_address("0x" + "11" * 32)
    expires = (datetime.now(UTC) + timedelta(days=7)).replace(tzinfo=None)
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": buyer_address,
            "provider_address": provider_address,
            "payload": {"cid": "QmTest", "access_key": "ak-der", "access_secret": "sec-der"},
            "expires_at": expires.isoformat(),
        }
    )
    job_id = created["job_id"]
    result = await service.register_ipfs_rental_token(
        {
            "access_key": "ak-der",
            "access_secret": "sec-der",
            "rental_id": job_id,
            "cid": "QmTest",
            "size": 100,
            **_rental_token_signature(job_id, "QmTest", buyer_address, provider_address, provider_key, provider_address),
        }
    )
    assert result["expires_at"] is not None
    # #2491: job-bound party fields come from the job, not the caller.
    assert result["buyer_address"] == buyer_address
    assert result["provider_address"] == provider_address


async def _terminal_pending_job(job_id: str, state: str) -> None:
    """Drive the job terminal while its payment stays pending (#2442)."""
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        job.state = state
        job.updated_at = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
        session.add(job)
        await session.commit()


async def _backdate_pending_deferral(job_id: str) -> None:
    """Age the pending-payment deferral stamp past settle_max_seconds."""
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        assert job is not None
        payment = await session.get(MarketJobPayment, job.payment_id)
        assert payment is not None
        meta = dict(payment.meta_data or {})
        meta[META_SETTLE_DEFERRAL_FIRST_AT] = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
        payment.meta_data = meta
        session.add(payment)
        await session.commit()


@pytest.mark.asyncio
async def test_pending_payment_on_terminal_job_expires_after_bound(sweeper) -> None:
    """#2442: terminal job + pending payment + confirmed-absent escrow ->
    bounded probe under the settle deferral, then terminal 'expired'."""
    service, sw, _rpc = sweeper
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0"},
        }
    )
    job_id = created["job_id"]
    await _terminal_pending_job(job_id, "EXPIRED")

    # First confirmed-absent answer only stamps the deferral — still pending.
    await sw.sweep_once()
    payment = await _payment_of(job_id)
    assert payment.status == "pending"
    assert META_SETTLE_DEFERRAL_FIRST_AT in (payment.meta_data or {})

    # Inside the bound it keeps probing — still pending.
    await sw.sweep_once()
    assert (await _payment_of(job_id)).status == "pending"

    # Past the bound with no sealed ESCROW_LOCK on chain -> expired.
    await _backdate_pending_deferral(job_id)
    await sw.sweep_once()
    payment = await _payment_of(job_id)
    assert payment.status == "expired"
    assert META_SETTLE_DEFERRAL_FIRST_AT not in (payment.meta_data or {})

    job = await service.get_market_job(job_id)
    assert job["payment_status"] == "expired"
    assert job["payment"]["status"] == "expired"


@pytest.mark.asyncio
async def test_pending_payment_on_live_job_never_expires(sweeper) -> None:
    """#2442: QUEUED/RUNNING jobs keep probing forever — the lock may still
    legitimately seal, so the dead-end bound must not apply."""
    service, sw, _rpc = sweeper
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0"},
        }
    )
    job_id = created["job_id"]

    await sw.sweep_once()
    payment = await _payment_of(job_id)
    assert payment.status == "pending"
    # Live jobs do not even consume the deferral stamp.
    assert META_SETTLE_DEFERRAL_FIRST_AT not in (payment.meta_data or {})


@pytest.mark.asyncio
async def test_pending_payment_mismatched_escrow_stays_pending(sweeper) -> None:
    """#2442: a present-but-mismatched escrow is real locked money — it
    must keep probing for an operator and never feed the expire bound."""
    service, sw, rpc = sweeper
    buyer = "0x" + "11" * 20
    provider = "0x" + "22" * 20
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": buyer,
            "provider_address": provider,
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0"},
        }
    )
    job_id = created["job_id"]
    rpc.escrow_rows[job_id] = {"state": "locked", "amount": "2.0", "buyer": buyer, "provider": provider}
    await _terminal_pending_job(job_id, "FAILED")

    await sw.sweep_once()
    payment = await _payment_of(job_id)
    assert payment.status == "pending"
    assert META_SETTLE_DEFERRAL_FIRST_AT not in (payment.meta_data or {})


@pytest.mark.asyncio
async def test_pending_payment_sealed_lock_stays_pending_past_bound(sweeper) -> None:
    """#2442: past the bound a sealed ESCROW_LOCK on chain vetoes the
    expire — 'no escrow row' was a wrong-node/lag read, not absence."""
    service, sw, rpc = sweeper
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0"},
        }
    )
    job_id = created["job_id"]
    await _terminal_pending_job(job_id, "CANCELED")

    await sw.sweep_once()
    assert META_SETTLE_DEFERRAL_FIRST_AT in ((await _payment_of(job_id)).meta_data or {})

    rpc.lock_txs[job_id] = "0xsealed-lock"
    await _backdate_pending_deferral(job_id)
    await sw.sweep_once()
    assert (await _payment_of(job_id)).status == "pending"


@pytest.mark.asyncio
async def test_hashless_refund_stores_null_not_empty_string(sweeper) -> None:
    """#2442: a successful refund with no tx_hash stores NULL on both the
    payment and the job — never ""."""
    service, sw, rpc = sweeper
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "escrow_contract_id": "escrow-hashless",
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )
    await _apply_lifecycle(
        created["job_id"],
        state="CANCELED",
        escrow_contract_id="escrow-hashless",
        updated_at=(datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None),
    )
    rpc.omit_tx_hash = True

    counts = await sw.sweep_once()
    assert counts["refunded"] == 1

    payment = await _payment_of(created["job_id"])
    assert payment.status == "refunded"
    assert payment.refund_transaction_hash is None
    job = await service.get_market_job(created["job_id"])
    assert job["state"] == "REFUNDED"
    assert job["refund_tx_hash"] is None
    assert job["payment"]["refund_transaction_hash"] is None


async def _ipfs_job_with_escrow(service, *, expires_at: datetime | None = None) -> tuple[str, str, str]:
    """Create an ipfs market job with derived party keys; return
    (job_id, buyer_address, provider_address)."""
    from aitbc.crypto.crypto import derive_ethereum_address

    buyer_key = "0x" + "11" * 32
    provider_key = "0x" + "22" * 32
    data = {
        "service_type": "ipfs",
        "buyer_address": derive_ethereum_address(buyer_key),
        "provider_address": derive_ethereum_address(provider_key),
        "payload": {"cid": "QmTest", "access_key": "ak-x", "access_secret": "sec-x"},
        "payment": {"amount": "1.0", "status": "escrowed"},
    }
    if expires_at is not None:
        data["expires_at"] = expires_at.isoformat()
    created = await service.create_market_job(data)
    return created["job_id"], derive_ethereum_address(buyer_key), derive_ethereum_address(provider_key)


@pytest.mark.asyncio
async def test_job_bound_token_registration_requires_provider_signature(sweeper) -> None:
    """#2491: the market API key alone must not attach a rental token to a
    job's escrow — unsigned and foreign-signed registrations are refused."""
    service, _sw, _rpc = sweeper
    job_id, buyer_address, provider_address = await _ipfs_job_with_escrow(service)

    base = {
        "access_key": "ak-forged",
        "access_secret": "sec",
        "rental_id": job_id,
        "cid": "QmTest",
    }
    # Unsigned -> refused.
    with pytest.raises(ValueError, match="signer_address"):
        await service.register_ipfs_rental_token(dict(base))
    # Signed by a foreign key -> refused. The signer_address matches the
    # recovered signer so verification itself passes and the provider
    # check is what fails.
    from aitbc.crypto.crypto import derive_ethereum_address

    foreign_addr = derive_ethereum_address("0x" + "33" * 32)
    foreign = _rental_token_signature(job_id, "QmTest", buyer_address, provider_address, "0x" + "33" * 32, foreign_addr)
    with pytest.raises(ValueError, match="provider"):
        await service.register_ipfs_rental_token({**base, **foreign})
    # Signed by the buyer, not the provider -> refused.
    buyer_key = "0x" + "11" * 32
    buyer_sig = _rental_token_signature(job_id, "QmTest", buyer_address, provider_address, buyer_key, buyer_address)
    with pytest.raises(ValueError, match="provider"):
        await service.register_ipfs_rental_token({**base, **buyer_sig})
    # No token row may exist for any of the refused attempts.
    from market_service.domain.market import IpfsRentalToken

    async with get_session_context() as session:
        rows = (
            (await session.execute(select(IpfsRentalToken).where(IpfsRentalToken.access_key == "ak-forged"))).scalars().all()
        )
        assert rows == []


@pytest.mark.asyncio
async def test_job_bound_token_binds_job_parties(sweeper) -> None:
    """#2491: caller-supplied party/CID claims on a job-bound token are
    overwritten with the stored job values."""
    from aitbc.crypto.crypto import derive_ethereum_address

    service, _sw, _rpc = sweeper
    job_id, buyer_address, provider_address = await _ipfs_job_with_escrow(service)
    provider_key = "0x" + "22" * 32
    attacker = derive_ethereum_address("0x" + "99" * 32)
    result = await service.register_ipfs_rental_token(
        {
            "access_key": "ak-bind",
            "access_secret": "sec",
            "rental_id": job_id,
            "cid": "QmFake",
            "buyer_address": attacker,
            "provider_address": attacker,
            **_rental_token_signature(job_id, "QmTest", buyer_address, provider_address, provider_key, provider_address),
        }
    )
    assert result["provider_address"] == provider_address
    assert result["buyer_address"] == buyer_address
    assert result["cid"] == "QmTest"


@pytest.mark.asyncio
async def test_expired_job_with_unproven_token_refunds(sweeper) -> None:
    """#2491 exploit regression: an active rental token that has no
    provider-signed pin proof must NOT suppress the expired-job refund —
    previously any market-API-key holder could register one and flip the
    refund into a release."""
    from market_service.domain.market import IpfsRentalToken

    service, sw, rpc = sweeper
    job_id, _buyer, _provider = await _ipfs_job_with_escrow(service, expires_at=datetime.now(UTC) - timedelta(days=1))
    await _apply_lifecycle(job_id, state="RUNNING", escrow_contract_id=job_id)
    async with get_session_context() as session:
        session.add(
            IpfsRentalToken(
                access_key="ak-unproven",
                access_secret="hashed-secret",
                rental_id=job_id,
                cid="QmTest",
                status="active",
                expires_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        await session.commit()

    # First pass expires the job; the refund itself waits out min_age.
    await sw.sweep_once()
    await _age_job(job_id)
    counts = await sw.sweep_once()
    assert job_id in rpc.refunded
    assert counts["refunded"] == 1


@pytest.mark.asyncio
async def test_job_bound_token_update_requires_provider_signature(sweeper) -> None:
    """#2514: the #2491 signature gate must also cover the UPDATE path —
    an unsigned upsert that omits ``rental_id`` used to rewrite a
    provider-signed token's secret, CID and parties while the stored
    ``rental_id`` kept the escrow binding."""
    from aitbc.crypto.crypto import derive_ethereum_address

    service, _sw, _rpc = sweeper
    job_id, buyer_address, provider_address = await _ipfs_job_with_escrow(service)
    provider_key = "0x" + "22" * 32
    attacker = derive_ethereum_address("0x" + "99" * 32)

    await service.register_ipfs_rental_token(
        {
            "access_key": "ak-upd",
            "access_secret": "sec-orig",
            "rental_id": job_id,
            "cid": "QmTest",
            **_rental_token_signature(job_id, "QmTest", buyer_address, provider_address, provider_key, provider_address),
        }
    )

    # Unsigned update, no rental_id — the old bypass.
    with pytest.raises(ValueError, match="signer_address"):
        await service.register_ipfs_rental_token(
            {
                "access_key": "ak-upd",
                "access_secret": "sec-pwned",
                "cid": "QmEvil",
                "buyer_address": attacker,
                "provider_address": attacker,
            }
        )
    # Foreign-signed update — verification passes but the signer is not
    # the job's provider.
    foreign_addr = derive_ethereum_address("0x" + "33" * 32)
    with pytest.raises(ValueError, match="provider"):
        await service.register_ipfs_rental_token(
            {
                "access_key": "ak-upd",
                "access_secret": "sec-pwned",
                **_rental_token_signature(job_id, "QmTest", buyer_address, provider_address, "0x" + "33" * 32, foreign_addr),
            }
        )

    from market_service.domain.market import IpfsRentalToken

    async with get_session_context() as session:
        row = (await session.execute(select(IpfsRentalToken).where(IpfsRentalToken.access_key == "ak-upd"))).scalar_one()
        assert row.provider_address == provider_address
        assert row.buyer_address == buyer_address
        assert row.cid == "QmTest"
        assert row.access_secret != "sec-pwned"


@pytest.mark.asyncio
async def test_job_bound_token_update_with_provider_signature(sweeper) -> None:
    """#2514: a provider-signed update succeeds — credential rotation is
    legitimate — but party/CID claims are rebound to the stored job."""
    from aitbc.crypto.crypto import derive_ethereum_address

    service, _sw, _rpc = sweeper
    job_id, buyer_address, provider_address = await _ipfs_job_with_escrow(service)
    provider_key = "0x" + "22" * 32
    attacker = derive_ethereum_address("0x" + "99" * 32)

    await service.register_ipfs_rental_token(
        {
            "access_key": "ak-upd-ok",
            "access_secret": "sec-orig",
            "rental_id": job_id,
            "cid": "QmTest",
            **_rental_token_signature(job_id, "QmTest", buyer_address, provider_address, provider_key, provider_address),
        }
    )
    result = await service.register_ipfs_rental_token(
        {
            "access_key": "ak-upd-ok",
            "access_secret": "sec-rotated",
            "cid": "QmFake",
            "buyer_address": attacker,
            "provider_address": attacker,
            # rental_id omitted — authorization comes from the stored token.
            **_rental_token_signature(job_id, "QmTest", buyer_address, provider_address, provider_key, provider_address),
        }
    )
    assert result["provider_address"] == provider_address
    assert result["buyer_address"] == buyer_address
    assert result["cid"] == "QmTest"
    assert result["rental_id"] == job_id


@pytest.mark.asyncio
async def test_token_update_rejects_differing_rental_id(sweeper) -> None:
    """#2514: a request ``rental_id`` that differs from the stored token's
    is refused — otherwise a signature valid for the caller's own job
    could rewrite a victim token that stays bound to the victim escrow."""

    service, _sw, _rpc = sweeper
    job_id, buyer_address, provider_address = await _ipfs_job_with_escrow(service)
    other_job_id, _ob, _op = await _ipfs_job_with_escrow(service)
    provider_key = "0x" + "22" * 32

    await service.register_ipfs_rental_token(
        {
            "access_key": "ak-rid",
            "access_secret": "sec",
            "rental_id": job_id,
            "cid": "QmTest",
            **_rental_token_signature(job_id, "QmTest", buyer_address, provider_address, provider_key, provider_address),
        }
    )
    # Signed for the STORED job but claiming a different rental_id.
    with pytest.raises(ValueError, match="rental_id"):
        await service.register_ipfs_rental_token(
            {
                "access_key": "ak-rid",
                "access_secret": "sec2",
                "rental_id": other_job_id,
                **_rental_token_signature(job_id, "QmTest", buyer_address, provider_address, provider_key, provider_address),
            }
        )
    # A standalone token cannot acquire a rental_id via update either.
    await service.register_ipfs_rental_token({"access_key": "ak-plain", "access_secret": "sec"})
    with pytest.raises(ValueError, match="rental_id"):
        await service.register_ipfs_rental_token({"access_key": "ak-plain", "access_secret": "sec2", "rental_id": job_id})


@pytest.mark.asyncio
async def test_standalone_token_update_stays_unsigned(sweeper) -> None:
    """#2514: tokens with no job binding keep the legacy unsigned update —
    there is no provider job to verify against."""
    service, _sw, _rpc = sweeper
    await service.register_ipfs_rental_token({"access_key": "ak-legacy", "access_secret": "sec-1", "cid": "QmA"})
    result = await service.register_ipfs_rental_token({"access_key": "ak-legacy", "access_secret": "sec-2", "cid": "QmB"})
    assert result["cid"] == "QmB"
