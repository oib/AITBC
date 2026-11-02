"""Phase-0 pin for MARKET-RELEASE-TXHASH-TRUST-1 (#814).

release_market_job_payment trusts a caller-supplied ``tx_hash`` verbatim:
when ``release_data["tx_hash"]`` is set the escrow-release RPC is skipped
entirely and the job is marked RELEASED with no on-chain check (contrast
complete_bid, which verifies sender/recipient/value). It also settles
``job.id`` while guarding ``escrow_contract_id`` — if they diverge the
settle targets the wrong object.

Desired: a caller-supplied tx_hash is never authoritative — the release
verifies on-chain like complete_bid, or refuses. FAILS on current main:
the job lands RELEASED with the forged hash and zero RPC calls.
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


async def _job(session: AsyncSession, jid: str) -> MarketJob:
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
    return job


class TestCallerSuppliedTxHashIsNotAuthoritative:
    @pytest.mark.asyncio
    async def test_forged_tx_hash_marks_released_without_rpc(self, session):
        job = await _job(session, "job-release-1")
        job_id = job.id
        svc = MarketService(session)
        svc._rpc_client.release_escrow = AsyncMock()
        result = await svc.release_market_job_payment(job_id, release_data={"tx_hash": "0xdeadbeef"})
        # desired: the release must not stand on a caller-supplied hash —
        # either it verifies on-chain or it refuses. On main it returns
        # RELEASED with the forged hash and no RPC call at all.
        svc._rpc_client.release_escrow.assert_not_called()
        assert result.get("state") != "RELEASED" or result.get("tx_hash") != "0xdeadbeef", (
            "caller-supplied tx_hash marked the job RELEASED with no verification"
        )
