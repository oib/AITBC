"""#1805: market job sweeper terminal escrow writes are compare-and-swap."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment, SoftwareService
from market_service.services.market_service import MarketService
from market_service.services.market_job_sweeper import MarketJobSweeper
from market_service.storage import get_session_context

pytestmark = pytest.mark.asyncio


class StubRPC:
    async def release_escrow(self, job_id: str, body: dict | None = None):
        return {"success": True, "tx_hash": f"0xrelease_{job_id}"}

    async def refund_escrow(self, job_id: str, body: dict | None = None):
        return {"success": True, "tx_hash": f"0xrefund_{job_id}"}


async def _seed_completed_escrowed() -> str:
    uid = uuid4().hex[:8]
    offer_id = f"offer_sw_{uid}"
    async with get_session_context() as session:
        svc = MarketService(session)
        svc.session.add(SoftwareService(service_type="ipfs", offer_id=offer_id))
        created = await svc.create_market_job(
            {
                "service_type": "ipfs",
                "buyer_address": "0x" + "11" * 20,
                "provider_address": "0x" + "22" * 20,
                "offer_id": offer_id,
                "payload": {"cid": "QmTest"},
                "payment": {"amount": "1.0", "status": "escrowed"},
            }
        )
        job_id = created["job_id"]
        job = await session.get(MarketJob, job_id)
        assert job is not None
        job.state = "COMPLETED"
        job.updated_at = (datetime.now(UTC) - timedelta(days=2)).replace(tzinfo=None)
        session.add(job)
        await session.commit()
    return job_id


async def _state_and_payment(job_id: str) -> tuple[str, str | None]:
    async with get_session_context() as session:
        job = await session.get(MarketJob, job_id)
        payment = await session.get(MarketJobPayment, job.payment_id) if job and job.payment_id else None
        return job.state if job else "", (payment.status if payment else None)


async def test_concurrent_cancel_and_release_no_mixed_state() -> None:
    """Cancel vs sweeper release: never RELEASED with escrowed, nor CANCELED with released."""
    rpc = StubRPC()
    for _ in range(10):
        job_id = await _seed_completed_escrowed()

        async def cancel(_job_id: str = job_id):
            async with get_session_context() as session:
                await MarketService(session).cancel_market_job(_job_id, reason="race")

        async def release(_job_id: str = job_id):
            async with get_session_context() as session:
                job = await session.get(MarketJob, _job_id)
                assert job is not None and job.payment_id
                payment = await session.get(MarketJobPayment, job.payment_id)
                assert payment is not None
                sw = MarketJobSweeper(rpc_client=rpc, session_factory=lambda: get_session_context())
                await sw._release_payment(session, job, payment)
                await session.commit()

        await asyncio.gather(cancel(), release(), return_exceptions=True)
        state, pay = await _state_and_payment(job_id)
        if state == "RELEASED":
            assert pay == "released", (state, pay)
        elif state == "CANCELED":
            assert pay in {"escrowed", "refund_pending", "refunded"}, (state, pay)
        else:
            assert state in {"COMPLETED", "RELEASED", "CANCELED"}, (state, pay)
