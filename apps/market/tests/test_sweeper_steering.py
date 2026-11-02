"""Phase-0 pin for MARKET-SWEEPER-STEERING-1 (#815).

The rental-token upsert and create_market_job model splats let an anonymous
caller write rows that point the settlement sweepers at a victim's
escrow_contract_id: a token with rental_id=<victim>, pinned=False,
status='expired', past expires_at makes IpfsRentalSweeper call
refund_escrow(victim); a MarketJob with state=FAILED,
payment.status='escrowed', escrow_contract_id=<victim> makes
MarketJobSweeper do the same.

Desired: sweepers act only on escrows owned by the row they settle —
steering rows never reach refund/release. FAILS on current main: the
crafted rows get the sweeper to call refund_escrow("victim").
"""

import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import IpfsRentalToken, MarketJob, MarketJobPayment
from market_service.services.ipfs_rental_sweeper import IpfsRentalSweeper
from market_service.services.market_job_sweeper import MarketJobSweeper
from market_service.storage import get_session_context


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_session_context() as s:
        yield s


def _rpc():
    rpc = MagicMock()
    rpc.refund_escrow = AsyncMock(return_value={"success": True, "tx_hash": "0xr"})
    rpc.release_escrow = AsyncMock(return_value={"success": True, "tx_hash": "0xr"})
    return rpc


class TestRentalTokenSteering:
    @pytest.mark.asyncio
    async def test_crafted_token_refunds_victim_escrow(self, session):
        victim = "victim-escrow-1"
        token = IpfsRentalToken(
            access_key="k-steer-1",
            access_secret="s",
            rental_id=victim,
            offer_id="o1",
            cid="QmX",
            buyer_address="0xbuyer",
            provider_address="0xprovider",
            escrow_contract_id=victim,
            pinned=False,
            status="expired",
            expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2),
        )
        session.add(token)
        await session.commit()
        rpc = _rpc()
        sweeper = IpfsRentalSweeper(rpc_client=rpc, session_factory=get_session_context)
        await sweeper.sweep_once()
        called = [c.args[0] for c in rpc.refund_escrow.call_args_list]
        assert victim not in called, "crafted token steered the sweeper into refunding a victim escrow"


class TestMarketJobSteering:
    @pytest.mark.asyncio
    async def test_crafted_failed_job_refunds_victim_escrow(self, session):
        victim = "victim-escrow-2"
        pay = MarketJobPayment(
            job_id="job-steer-1",
            amount=10,
            status="escrowed",
            escrowed_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2),
        )
        job = MarketJob(
            id="job-steer-1",
            state="FAILED",
            escrow_contract_id=victim,
            payment_id=pay.id,
            payment_status="escrowed",
            expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2),
            updated_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2),
            created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2),
        )
        session.add_all([pay, job])
        await session.commit()
        rpc = _rpc()
        sweeper = MarketJobSweeper(rpc_client=rpc, session_factory=get_session_context)
        await sweeper.sweep_once()
        called = [c.args[0] for c in rpc.refund_escrow.call_args_list]
        assert victim not in called, "crafted job steered the sweeper into refunding a victim escrow"
