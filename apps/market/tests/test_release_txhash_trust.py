"""Pin for MARKET-RELEASE-TXHASH-TRUST-1 (#814), post-fix contract.

release_market_job_payment must not trust a caller-supplied ``tx_hash``
verbatim: the hash is evidence to be verified on-chain (like complete_bid),
not authority. The settle call targets ``job.escrow_contract_id`` — the
field the guard checks — not ``job.id``.

Green on the fix; FAILS on pre-fix main (the job lands RELEASED with a
forged hash and no RPC call at all).
"""

import sys
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import MarketJob, MarketJobPayment
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_session_context() as s:
        yield s


async def _job(session: AsyncSession, jid: str) -> str:
    pay = MarketJobPayment(job_id=jid, amount=10, status="escrowed")
    job = MarketJob(
        id=jid,
        state="COMPLETED",
        escrow_contract_id="esc-1",
        payment_id=pay.id,
        payment_status="escrowed",
    )
    session.add_all([pay, job])
    await session.flush()
    return jid


class TestCallerTxHashIsVerified:
    @pytest.mark.asyncio
    async def test_unconfirmed_tx_hash_is_refused(self, session):
        job_id = await _job(session, "job-release-1")
        svc = MarketService(session)
        svc._rpc_client.release_escrow = AsyncMock()
        svc._rpc_client.get_transaction = AsyncMock(return_value={"status": "pending"})
        with pytest.raises(ValueError, match="(?i)confirmed"):
            await svc.release_market_job_payment(job_id, release_data={"tx_hash": "0xdeadbeef"})
        svc._rpc_client.release_escrow.assert_not_called()
        svc._rpc_client.get_transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_tx_hash_is_refused(self, session):
        job_id = await _job(session, "job-release-2")
        svc = MarketService(session)
        svc._rpc_client.get_transaction = AsyncMock(return_value=None)
        with pytest.raises(ValueError):
            await svc.release_market_job_payment(job_id, release_data={"tx_hash": "0xdeadbeef"})

    @pytest.mark.asyncio
    async def test_escrow_release_targets_job_id(self, session):
        """#1564: the /rpc/escrow/{id} path key is the market job id — the
        escrow's job_id on chain — not the opaque contract id."""
        job_id = await _job(session, "job-release-3")
        svc = MarketService(session)
        svc._rpc_client.release_escrow = AsyncMock(return_value={"success": True, "tx_hash": "0xok"})
        await svc.release_market_job_payment(job_id)
        svc._rpc_client.release_escrow.assert_called_once_with("job-release-3")

    @pytest.mark.asyncio
    async def test_tx_hash_bound_to_this_jobs_escrow(self, session):
        """#1564: a confirmed tx of the right type but bound to a DIFFERENT
        job's escrow must be refused — 'confirmed' alone is not proof."""
        job_id = await _job(session, "job-release-4")
        svc = MarketService(session)
        svc._rpc_client.release_escrow = AsyncMock()
        svc._rpc_client.get_transaction = AsyncMock(
            return_value={
                "status": "confirmed",
                "type": "ESCROW_RELEASE",
                "payload": {"job_id": "someone-elses-job"},
            }
        )
        with pytest.raises(ValueError, match="(?i)not bound"):
            await svc.release_market_job_payment(job_id, release_data={"tx_hash": "0xdeadbeef"})
        svc._rpc_client.release_escrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_tx_hash_wrong_type_is_refused(self, session):
        job_id = await _job(session, "job-release-5")
        svc = MarketService(session)
        svc._rpc_client.get_transaction = AsyncMock(
            return_value={
                "status": "confirmed",
                "type": "ESCROW_LOCK",
                "payload": {"job_id": "job-release-5"},
            }
        )
        with pytest.raises(ValueError, match="(?i)ESCROW_RELEASE"):
            await svc.release_market_job_payment(job_id, release_data={"tx_hash": "0xdeadbeef"})

    @pytest.mark.asyncio
    async def test_release_refuses_non_escrowed_payment(self, session):
        """#1564 state guard: a pending payment on a live job cannot be
        'released' — only escrowed payments settle."""
        pay = MarketJobPayment(job_id="job-release-6", amount=10, status="pending")
        job = MarketJob(id="job-release-6", state="RUNNING", payment_id=pay.id, payment_status="pending")
        session.add_all([pay, job])
        await session.flush()
        svc = MarketService(session)
        svc._rpc_client.release_escrow = AsyncMock()
        with pytest.raises(ValueError, match="(?i)escrowed"):
            await svc.release_market_job_payment("job-release-6")
        svc._rpc_client.release_escrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_refuses_canceled_job(self, session):
        """#1564 state guard: a CANCELED job's escrow goes back to the buyer,
        never to the provider."""
        pay = MarketJobPayment(job_id="job-release-7", amount=10, status="escrowed")
        job = MarketJob(id="job-release-7", state="CANCELED", payment_id=pay.id, payment_status="escrowed")
        session.add_all([pay, job])
        await session.flush()
        svc = MarketService(session)
        svc._rpc_client.release_escrow = AsyncMock()
        with pytest.raises(ValueError, match="(?i)canceled"):
            await svc.release_market_job_payment("job-release-7")
        svc._rpc_client.release_escrow.assert_not_called()
