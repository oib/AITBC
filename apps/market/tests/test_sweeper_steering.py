"""Pin for MARKET-SWEEPER-STEERING-1 (#815), post-fix contract.

The rental-token upsert and create_market_job must not let a caller write
settlement state: column allowlists drop status/pinned/expires_at/tx_hash
(token) and state/escrow_contract_id/payment lifecycle fields (job), so a
crafted row can no longer point the sweepers at a victim escrow. The
rental sweeper additionally settles escrow_contract_id — the field the
payment path owns — and refuses rows where rental_id disagrees with it.

Green on the fix; FAILS on pre-fix main (the splats accepted the steering
fields and the sweeper refunded the victim).
"""

import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import IpfsRentalToken, MarketJob, MarketJobPayment
from market_service.services.ipfs_rental_sweeper import IpfsRentalSweeper
from market_service.services.market_service import MarketService
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


class TestRentalTokenSplatAllowlist:
    @pytest.mark.asyncio
    async def test_settlement_fields_are_dropped_on_create(self, session):
        svc = MarketService(session)
        await svc.register_ipfs_rental_token(
            {
                "access_key": "k-allow-1",
                "access_secret": "s",
                "rental_id": "victim-escrow-1",
                "escrow_contract_id": "victim-escrow-1",
                "pinned": False,
                "status": "expired",
                "expires_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                "tx_hash": None,
            }
        )
        row = (await session.execute(select(IpfsRentalToken).where(IpfsRentalToken.access_key == "k-allow-1"))).scalar_one()
        assert row.status == "active"
        assert row.pinned is True
        assert row.expires_at is None

    @pytest.mark.asyncio
    async def test_update_cannot_rewrite_settlement_fields(self, session):
        svc = MarketService(session)
        await svc.register_ipfs_rental_token({"access_key": "k-allow-2", "access_secret": "s", "rental_id": "r1"})
        await svc.register_ipfs_rental_token(
            {"access_key": "k-allow-2", "pinned": False, "status": "expired", "escrow_contract_id": "victim"}
        )
        row = (await session.execute(select(IpfsRentalToken).where(IpfsRentalToken.access_key == "k-allow-2"))).scalar_one()
        assert row.status == "active"
        assert row.pinned is True
        assert row.escrow_contract_id != "victim"


class TestSweeperSettlesOwnedEscrow:
    @pytest.mark.asyncio
    async def test_mismatched_rental_escrow_is_skipped(self, session):
        token = IpfsRentalToken(
            access_key="k-mismatch-1",
            access_secret="s",
            rental_id="victim-escrow-2",
            escrow_contract_id="own-escrow-2",
            pinned=False,
            status="expired",
            expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2),
        )
        session.add(token)
        await session.commit()
        rpc = _rpc()
        sweeper = IpfsRentalSweeper(rpc_client=rpc, session_factory=get_session_context)
        await sweeper.sweep_once()
        called = [c.args[0] for c in rpc.refund_escrow.call_args_list] + [c.args[0] for c in rpc.release_escrow.call_args_list]
        assert "victim-escrow-2" not in called

    @pytest.mark.asyncio
    async def test_market_job_splat_drops_settlement_fields(self, session):
        svc = MarketService(session)
        await svc.create_market_job(
            {
                "offer_id": "o1",
                "state": "FAILED",
                "escrow_contract_id": "victim-escrow-3",
                "payment_status": "escrowed",
                "payment": {"status": "escrowed", "amount": "5"},
            }
        )
        job = (await session.execute(select(MarketJob))).scalars().all()[-1]
        payment = (await session.execute(select(MarketJobPayment).where(MarketJobPayment.job_id == job.id))).scalar_one()
        assert job.state != "FAILED"
        assert job.escrow_contract_id is None
        assert payment.status != "escrowed"
        assert payment.escrowed_at is None
