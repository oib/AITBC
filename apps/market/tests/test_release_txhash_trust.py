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
    async def test_escrow_release_targets_contract_id(self, session):
        job_id = await _job(session, "job-release-3")
        svc = MarketService(session)
        svc._rpc_client.release_escrow = AsyncMock(return_value={"success": True, "tx_hash": "0xok"})
        await svc.release_market_job_payment(job_id)
        svc._rpc_client.release_escrow.assert_called_once_with("esc-1")
