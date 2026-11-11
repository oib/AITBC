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
from decimal import Decimal
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


_PROVIDER = "0x" + "aa" * 20
_BUYER = "0x" + "bb" * 20
_ATTACKER = "0x" + "cc" * 20


async def _job_with_parties(session: AsyncSession, jid: str) -> str:
    pay = MarketJobPayment(job_id=jid, amount=10, status="escrowed")
    job = MarketJob(
        id=jid,
        state="COMPLETED",
        escrow_contract_id="esc-1",
        payment_id=pay.id,
        payment_status="escrowed",
        buyer_address=_BUYER,
        provider_address=_PROVIDER,
    )
    session.add_all([pay, job])
    # Commit, not flush: a refused settle call rolls the session back, which
    # would otherwise wipe the uncommitted fixture rows (#1584 tests).
    await session.commit()
    return jid


def _settle_tx(job_id: str, tx_type: str = "ESCROW_RELEASE", **overrides):
    tx = {
        "status": "confirmed",
        "type": tx_type,
        "sender": "0x" + "dd" * 20,
        "recipient": _PROVIDER,
        "value": 5 * 36_000_000,  # 5 AIT in compute-units
        "payload": {
            "job_id": job_id,
            "action": "escrow_release" if tx_type == "ESCROW_RELEASE" else "escrow_refund",
            "buyer_escrow_addr": _BUYER,
            "provider_escrow_addr": _PROVIDER,
        },
    }
    tx.update(overrides)
    return tx


class TestSettleTxPartyAndAmountBinding:
    """#1584: the verified hash must pay THIS job's escrow payee, and the
    stored settlement amount comes from the tx, not the caller."""

    @pytest.mark.asyncio
    async def test_release_stores_onchain_amount_not_caller_claim(self, session):
        job_id = await _job_with_parties(session, "job-release-8")
        svc = MarketService(session)
        svc._rpc_client.get_transaction = AsyncMock(return_value=_settle_tx(job_id))
        await svc.release_market_job_payment(job_id, release_data={"tx_hash": "0xok", "released_amount": "999"})
        from sqlalchemy import select

        pay = (await session.execute(select(MarketJobPayment).where(MarketJobPayment.job_id == job_id))).scalar_one()
        assert pay.released_amount == Decimal("5")

    @pytest.mark.asyncio
    async def test_release_refuses_tx_paying_wrong_recipient(self, session):
        job_id = await _job_with_parties(session, "job-release-9")
        svc = MarketService(session)
        svc._rpc_client.get_transaction = AsyncMock(return_value=_settle_tx(job_id, recipient=_ATTACKER))
        with pytest.raises(ValueError, match="(?i)payee"):
            await svc.release_market_job_payment(job_id, release_data={"tx_hash": "0xok"})

    @pytest.mark.asyncio
    async def test_release_refuses_payload_payee_mismatch(self, session):
        job_id = await _job_with_parties(session, "job-release-10")
        tx = _settle_tx(job_id)
        tx["payload"]["provider_escrow_addr"] = _ATTACKER
        svc = MarketService(session)
        svc._rpc_client.get_transaction = AsyncMock(return_value=tx)
        with pytest.raises(ValueError, match="(?i)provider_escrow_addr"):
            await svc.release_market_job_payment(job_id, release_data={"tx_hash": "0xok"})

    @pytest.mark.asyncio
    async def test_refund_binds_buyer_recipient_and_amount(self, session):
        pay = MarketJobPayment(job_id="job-refund-1", amount=10, status="escrowed")
        job = MarketJob(
            id="job-refund-1",
            state="CANCELED",
            payment_id=pay.id,
            payment_status="escrowed",
            buyer_address=_BUYER,
            provider_address=_PROVIDER,
        )
        session.add_all([pay, job])
        await session.commit()
        svc = MarketService(session)
        # A refund pays the BUYER — a tx paying the provider must be refused.
        svc._rpc_client.get_transaction = AsyncMock(return_value=_settle_tx("job-refund-1", "ESCROW_REFUND"))
        with pytest.raises(ValueError, match="(?i)payee"):
            await svc.refund_market_job_payment("job-refund-1", refund_data={"tx_hash": "0xok"})
        # Paying the buyer stores the on-chain amount.
        tx = _settle_tx("job-refund-1", "ESCROW_REFUND", recipient=_BUYER)
        svc._rpc_client.get_transaction = AsyncMock(return_value=tx)
        await svc.refund_market_job_payment("job-refund-1", refund_data={"tx_hash": "0xok", "refunded_amount": "1"})
        from sqlalchemy import select

        pay = (await session.execute(select(MarketJobPayment).where(MarketJobPayment.job_id == "job-refund-1"))).scalar_one()
        # #1835: the settle write is now a Core CAS (synchronize_session=False)
        # — the identity-mapped instance keeps its pre-write attributes, so
        # refresh to read what actually committed.
        await session.refresh(pay)
        assert pay.refunded_amount == Decimal("5")
