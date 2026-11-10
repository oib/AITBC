"""Tests for MarketJob / MarketJobPayment lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from market_service.domain.market import MarketJob, MarketJobPayment, SoftwareService
from market_service.services.market_service import MarketService
from market_service.storage import get_session_context


@pytest.fixture
async def service() -> MarketService:
    async with get_session_context() as session:
        yield MarketService(session)


async def _register_offer(service: MarketService, offer_id: str) -> None:
    """#1564: create_market_job rejects unknown offer_ids — tests register the
    offer they reference, the way a provider's listing would."""
    service.session.add(SoftwareService(service_type="ipfs", offer_id=offer_id))
    await service.session.commit()


async def _mark_escrowed(service: MarketService, job_id: str, escrow_contract_id: str) -> None:
    """Drive the lifecycle fields the payment path owns.

    ``create_market_job`` deliberately ignores caller-supplied state,
    escrow_contract_id and payment.status (#815) — tests that need an
    escrowed job set those columns directly, the way settlement does.
    """
    job = await service.session.get(MarketJob, job_id)
    assert job is not None
    job.escrow_contract_id = escrow_contract_id
    job.payment_status = "escrowed"
    payment = await service.session.get(MarketJobPayment, job.payment_id)
    assert payment is not None
    payment.status = "escrowed"
    payment.updated_at = datetime.now(UTC).replace(tzinfo=None)
    service.session.add_all([job, payment])
    await service.session.commit()


@pytest.mark.asyncio
async def test_create_market_job(service: MarketService) -> None:
    await _register_offer(service, "offer-1")
    result = await service.create_market_job(
        {
            "service_type": "ipfs",
            "model": "ipfs-host",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "offer_id": "offer-1",
            "plugin_id": "ipfs-ipfs-host",
            "state": "QUEUED",
            "payload": {"cid": "QmTest123", "size": 1024, "access_key": "ak"},
            "payment": {
                "amount": "1.5",
                "status": "escrowed",
            },
        }
    )

    assert result["job_id"]
    assert result["service_type"] == "ipfs"
    assert Decimal(result["payment"]["amount"]) == Decimal("1.5")
    # #815: caller-supplied state/payment.status are ignored — lifecycle is
    # service-owned, so a fresh job is always pending regardless of input.
    assert result["payment_status"] == "pending"


@pytest.mark.asyncio
async def test_get_market_job(service: MarketService) -> None:
    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "payload": {"cid": "QmTest", "size": 100},
            "payment": {"amount": "0.1", "status": "pending"},
        }
    )

    fetched = await service.get_market_job(created["job_id"])
    assert fetched
    assert fetched["job_id"] == created["job_id"]
    assert fetched["payment"]["status"] == "pending"


@pytest.mark.asyncio
async def test_confirm_and_release_payment(service: MarketService) -> None:
    """Confirm pin, then release payment; uses a stub RPC client."""

    class StubRPC:
        async def release_escrow(self, job_id: str, body: dict | None = None):
            return {"success": True, "tx_hash": f"0xrelease_{job_id}"}

    service._rpc_client = StubRPC()  # type: ignore[assignment]

    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "escrow_contract_id": "escrow-123",
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "pending"},
        }
    )
    await _mark_escrowed(service, created["job_id"], "escrow-123")

    await service.confirm_market_job_pin(created["job_id"], size=100)
    fetched = await service.get_market_job(created["job_id"])
    assert fetched["state"] == "RUNNING"
    # payload is a plain JSON column: pin-confirm must reassign it, or the
    # mutation is silently dropped at commit.
    assert fetched["payload"]["pinned"] is True
    assert fetched["payload"]["size"] == 100

    released = await service.release_market_job_payment(created["job_id"])
    assert released["state"] == "RELEASED"
    assert released["payment_status"] == "released"
    # #1564: the escrow path key is the market job id, not escrow_contract_id.
    assert released["tx_hash"] == f"0xrelease_{created['job_id']}"


@pytest.mark.asyncio
async def test_cancel_and_refund(service: MarketService) -> None:
    class StubRPC:
        async def refund_escrow(self, job_id: str, body: dict | None = None):
            return {"success": True, "tx_hash": f"0xrefund_{job_id}"}

    service._rpc_client = StubRPC()  # type: ignore[assignment]

    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "escrow_contract_id": "escrow-456",
            "payload": {"cid": "QmTest"},
            "payment": {"amount": "1.0", "status": "escrowed"},
        }
    )
    await _mark_escrowed(service, created["job_id"], "escrow-456")

    canceled = await service.cancel_market_job(created["job_id"], reason="test")
    assert canceled["state"] == "CANCELED"
    assert canceled["payment_status"] == "refund_pending"

    refunded = await service.refund_market_job_payment(created["job_id"])
    assert refunded["state"] == "REFUNDED"
    assert refunded["payment_status"] == "refunded"
    # #1564: the escrow path key is the market job id, not escrow_contract_id.
    assert refunded["refund_tx_hash"] == f"0xrefund_{created['job_id']}"


@pytest.mark.asyncio
async def test_confirm_pin_persists_provider_confirmed(service: MarketService) -> None:
    """provider_confirmed must land in the persisted payload.

    Regression test: job.payload is a plain ``Column(JSON)`` -- mutating the
    dict in place never reaches the database, so the provider's pin-confirm was
    accepted (200) but the flag silently vanished.
    """

    class StubRPC:
        async def verify_escrow(self, job_id: str):
            return {
                "job_id": job_id,
                "state": "funded",
                "amount": "0.1",
                "buyer": "0x" + "11" * 20,
                "provider": "0x" + "22" * 20,
            }

    service._rpc_client = StubRPC()  # type: ignore[assignment]

    created = await service.create_market_job(
        {
            "service_type": "ipfs",
            "buyer_address": "0x" + "11" * 20,
            "provider_address": "0x" + "22" * 20,
            "payload": {"cid": "QmTest", "size": 10},
            "payment": {"amount": "0.1", "status": "escrowed"},
        }
    )

    await service.confirm_market_job_pin(created["job_id"], provider_confirmed=True)

    fetched = await service.get_market_job(created["job_id"])
    assert fetched["state"] == "RUNNING"
    assert fetched["payload"]["provider_confirmed"] is True


class _EscrowStub:
    """verify_escrow stub for pin-confirm tests."""

    def __init__(self, escrow: dict | None):
        self._escrow = escrow
        self.calls = 0

    async def verify_escrow(self, job_id: str):
        self.calls += 1
        return self._escrow


def _job_fields(**overrides):
    fields = {
        "service_type": "ipfs",
        "buyer_address": "0x" + "11" * 20,
        "provider_address": "0x" + "22" * 20,
        "payload": {"cid": "QmTest"},
        "payment": {"amount": "1.0", "status": "pending"},
    }
    fields.update(overrides)
    return fields


@pytest.mark.asyncio
async def test_pin_confirm_requires_onchain_escrow(service: MarketService) -> None:
    """#1564: pending->escrowed without chain proof must fail and persist nothing."""
    stub = _EscrowStub(None)
    service._rpc_client = stub  # type: ignore[assignment]

    created = await service.create_market_job(_job_fields())

    with pytest.raises(ValueError, match="No on-chain escrow"):
        await service.confirm_market_job_pin(created["job_id"], size=100)

    assert stub.calls == 1
    fetched = await service.get_market_job(created["job_id"])
    assert fetched["state"] == "QUEUED"
    assert fetched["payment"]["status"] == "pending"
    assert fetched["payload"].get("pinned") is not True


@pytest.mark.asyncio
async def test_pin_confirm_rejects_mismatched_escrow(service: MarketService) -> None:
    """#1564: an escrow for a different amount or party is not proof."""
    stub = _EscrowStub(
        {
            "job_id": "other",
            "state": "funded",
            "amount": "2.0",
            "buyer": "0x" + "11" * 20,
            "provider": "0x" + "22" * 20,
        }
    )
    service._rpc_client = stub  # type: ignore[assignment]

    created = await service.create_market_job(_job_fields())

    with pytest.raises(ValueError, match="does not match"):
        await service.confirm_market_job_pin(created["job_id"])

    fetched = await service.get_market_job(created["job_id"])
    assert fetched["payment"]["status"] == "pending"


@pytest.mark.asyncio
async def test_pin_confirm_rejects_unlocked_escrow_state(service: MarketService) -> None:
    """#1564: a 'created' (unfunded) or settled escrow state is not a lock."""
    stub = _EscrowStub(
        {
            "job_id": "x",
            "state": "released",
            "amount": "1.0",
            "buyer": "0x" + "11" * 20,
            "provider": "0x" + "22" * 20,
        }
    )
    service._rpc_client = stub  # type: ignore[assignment]

    created = await service.create_market_job(_job_fields())

    with pytest.raises(ValueError, match="not locked"):
        await service.confirm_market_job_pin(created["job_id"])


@pytest.mark.asyncio
async def test_pin_confirm_marks_escrowed_with_valid_proof(service: MarketService) -> None:
    """#1564: a locked on-chain escrow with matching amount+parties flips pending->escrowed."""
    stub = _EscrowStub(
        {
            "job_id": "x",
            "state": "funded",
            "amount": "1.0",
            "buyer": "0x" + "11" * 20,
            "provider": "0x" + "22" * 20,
        }
    )
    service._rpc_client = stub  # type: ignore[assignment]

    created = await service.create_market_job(_job_fields())
    result = await service.confirm_market_job_pin(created["job_id"], size=42)

    assert result["state"] == "RUNNING"
    assert result["payment_status"] == "escrowed"
    fetched = await service.get_market_job(created["job_id"])
    assert fetched["payment"]["status"] == "escrowed"
    assert fetched["payment"]["escrowed_at"] is not None


@pytest.mark.asyncio
async def test_pin_confirm_skips_proof_when_already_escrowed(service: MarketService) -> None:
    """#1564: the proof gate only guards the pending->escrowed transition."""
    stub = _EscrowStub(None)
    service._rpc_client = stub  # type: ignore[assignment]

    created = await service.create_market_job(_job_fields())
    await _mark_escrowed(service, created["job_id"], "escrow-1")

    result = await service.confirm_market_job_pin(created["job_id"])
    assert result["state"] == "RUNNING"
    assert stub.calls == 0


@pytest.mark.asyncio
async def test_create_market_job_rejects_unknown_offer(service: MarketService) -> None:
    """#1564: an offer_id that resolves nowhere is a 400-class error."""

    class _EmptyRPC:
        async def get_offer(self, gpu_id, chain_id=None):
            return None

        async def query_transactions(self, **kwargs):
            return []

    service._rpc_client = _EmptyRPC()  # type: ignore[assignment]

    with pytest.raises(ValueError, match="Unknown offer_id"):
        await service.create_market_job(_job_fields(offer_id="no-such-offer"))


@pytest.mark.asyncio
async def test_create_market_job_rejects_bad_payment_amount(service: MarketService) -> None:
    """#1564/#1608: NaN and negative payment amounts never reach the column."""
    await _register_offer(service, "offer-amt")

    with pytest.raises(ValueError, match="payment amount"):
        await service.create_market_job(_job_fields(offer_id="offer-amt", payment={"amount": "NaN"}))
    with pytest.raises(ValueError, match="payment amount"):
        await service.create_market_job(_job_fields(offer_id="offer-amt", payment={"amount": "-1"}))
