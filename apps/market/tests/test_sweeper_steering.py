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

from market_service.domain.market import IpfsRentalToken, MarketJob, MarketJobPayment, SoftwareService
from market_service.services.ipfs_rental_sweeper import IpfsRentalSweeper
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context


# #2623: new rental tokens must bind to a resolvable market job and carry
# the job provider's wallet signature — the allowlist tests register
# through that path so they exercise the same contract the route enforces.
_PROVIDER_KEY = "0x" + "22" * 32
_BUYER_KEY = "0x" + "11" * 32


def _addr(private_key: str) -> str:
    from aitbc.crypto.crypto import derive_ethereum_address

    return derive_ethereum_address(private_key)


def _proof(private_key: str, route: str, binding: dict) -> dict:
    import time

    from aitbc.crypto.crypto import sign_transaction_data
    from aitbc.market.job_request_signature import jobs_request_message
    from aitbc.utils.chain_id import resolve_chain_id
    from market_service.config import settings

    address = _addr(private_key)
    chain_id = settings.default_chain_id or resolve_chain_id()
    issued_at = int(time.time())
    return {
        "signer_address": address,
        "chain_id": chain_id,
        "issued_at": issued_at,
        "signature": sign_transaction_data(
            jobs_request_message(address, chain_id, issued_at, route, binding=binding), private_key
        ),
    }


async def _job_and_binding(svc: MarketService, session: AsyncSession) -> tuple[str, dict]:
    created = await svc.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": _addr(_BUYER_KEY),
            "provider_address": _addr(_PROVIDER_KEY),
            "payload": {"cid": "QmTest", "size": 10},
            "payment": {"amount": "1.0"},
        }
    )
    job_id = created["job_id"]
    job = await session.get(MarketJob, job_id)
    assert job is not None
    binding = {
        "rental_id": job_id,
        "cid": str((job.payload or {}).get("cid") or ""),
        "buyer_address": str(job.buyer_address or ""),
        "provider_address": str(job.provider_address or ""),
    }
    return job_id, binding


async def _register(
    svc: MarketService, session: AsyncSession, access_key: str, rental_id: str, binding: dict, **extra
) -> None:
    await svc.register_ipfs_rental_token(
        {
            "access_key": access_key,
            "access_secret": "s",
            "rental_id": rental_id,
            **_proof(_PROVIDER_KEY, "/v1/market/ipfs/rental-token", binding),
            **extra,
        }
    )


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
        job_id, binding = await _job_and_binding(svc, session)
        await _register(
            svc,
            session,
            "k-allow-1",
            job_id,
            binding,
            escrow_contract_id="victim-escrow-1",
            pinned=False,
            status="expired",
            expires_at=(datetime.now(UTC) - timedelta(days=2)).isoformat(),
            tx_hash=None,
        )
        row = (await session.execute(select(IpfsRentalToken).where(IpfsRentalToken.access_key == "k-allow-1"))).scalar_one()
        assert row.status == "active"
        assert row.pinned is True
        # #2623: the caller's past expires_at is dropped AND the token now
        # inherits the job's settlement clock — it cannot live forever.
        assert row.expires_at is not None
        assert row.expires_at > datetime.now(UTC).replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_update_cannot_rewrite_settlement_fields(self, session):
        svc = MarketService(session)
        job_id, binding = await _job_and_binding(svc, session)
        await _register(svc, session, "k-allow-2", job_id, binding)
        # #2623/#2514: updates on a job-bound token need the provider
        # signature again — authorization comes from the stored rental_id.
        await svc.register_ipfs_rental_token(
            {
                "access_key": "k-allow-2",
                "pinned": False,
                "status": "expired",
                "escrow_contract_id": "victim",
                **_proof(_PROVIDER_KEY, "/v1/market/ipfs/rental-token", binding),
            }
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
        session.add(SoftwareService(service_type="ipfs", offer_id="o1"))
        await session.commit()
        await svc.create_market_job(
            {
                "offer_id": "o1",
                "state": "FAILED",
                "escrow_contract_id": "victim-escrow-3",
                "payment_status": "escrowed",
                "payment": {"status": "escrowed", "amount": "5"},
            }
        )
        job = (await session.execute(select(MarketJob).where(MarketJob.offer_id == "o1"))).scalars().all()[-1]
        payment = (await session.execute(select(MarketJobPayment).where(MarketJobPayment.job_id == job.id))).scalar_one()
        assert job.state != "FAILED"
        # #1634: escrow_contract_id is now bound to the job id at creation —
        # the splat must still not let the caller's "victim-escrow-3" through.
        assert job.escrow_contract_id == job.id
        assert job.escrow_contract_id != "victim-escrow-3"
        assert payment.status != "escrowed"
        assert payment.escrowed_at is None
