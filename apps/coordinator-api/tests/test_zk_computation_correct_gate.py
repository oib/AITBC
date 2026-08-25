"""G3: computation_correct must gate escrow release, not just ZK proof validity."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.routers import miner as miner_module
from coordinator_api.contexts.infrastructure.routers.miner import _attach_zk_proof
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.contexts.payments.services.payments import PaymentService
from coordinator_api.schemas import JobCreate


class _NeverCallClient:
    """Placeholder AITBCHTTPClient that fails if the ZK gate did not block the call."""

    def __init__(self, *args, **kwargs):
        pass

    def post(self, *args, **kwargs):
        raise AssertionError("AITBCHTTPClient.post called; the release gate should have blocked earlier")


class _FakeJob:
    def __init__(
        self, *, job_id: str = "job_test_1234", payment_amount: float = 5.0, constraints: dict[str, Any] | None = None
    ):
        self.id = job_id
        self.payment_amount = payment_amount
        self.constraints = constraints or {}


class _FakeZkService:
    def __init__(self, *, verified: bool = True, computation_correct: bool = True):
        self._verified = verified
        self._computation_correct = computation_correct

    def is_enabled(self) -> bool:
        return True

    async def generate_receipt_proof(self, *args, **kwargs):
        return {
            "proof": {},
            "public_signals": ["1"],
            "receipt": [],
            "circuit": "receipt_public",
        }

    async def verify_proof(self, *args, **kwargs):
        return {
            "verified": self._verified,
            "computation_correct": self._computation_correct,
            "privacy_preserved": self._verified,
        }


def _completed_job_with_receipt(job_service, db_session, *, receipt: dict[str, Any] | None = None, zk_required: bool = True):
    req = JobCreate(
        payload={"type": "inference", "prompt": "test prompt"},
        ttl_seconds=900,
        payment_amount=Decimal("5"),
        payment_currency="AITBC",
    )
    job = job_service.create_job(client_id="client1", req=req)
    payment = JobPayment(
        job_id=job.id,
        amount=Decimal("5"),
        currency="AITBC",
        payment_method="aitbc_token",
        status="escrowed",
        meta_data={"provider_address": "0x" + "a" * 40},
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    job.state = "COMPLETED"
    job.completed_at = datetime.now(UTC)
    job.payment_id = payment.id
    job.payment_status = "escrowed"
    if zk_required:
        job.constraints = {"zk_proof_required": True}
    if receipt is not None:
        job.receipt = receipt
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job, payment


@pytest.mark.asyncio
async def test_attach_zk_proof_blocks_when_computation_is_incorrect(monkeypatch):
    monkeypatch.setattr(miner_module, "zk_proof_service", _FakeZkService(verified=True, computation_correct=False))
    receipt = {
        "receipt_id": "r_test_1234",
        "provider": "0x" + "a" * 40,
        "coordinator": "0x" + "b" * 40,
        "completed_at": 0,
        "status": "completed",
        "payload": {"units": 1.0},
    }
    result = {"output": "wrong"}

    out = await _attach_zk_proof(receipt, _FakeJob(constraints={"zk_proof_required": True}), result)

    assert out["zk_status"] == "computation_incorrect"
    assert out["computation_correct"] is False


@pytest.mark.asyncio
async def test_attach_zk_proof_passes_when_computation_is_correct(monkeypatch):
    monkeypatch.setattr(miner_module, "zk_proof_service", _FakeZkService(verified=True, computation_correct=True))
    receipt = {
        "receipt_id": "r_test_1234",
        "provider": "0x" + "a" * 40,
        "coordinator": "0x" + "b" * 40,
        "completed_at": 0,
        "status": "completed",
        "payload": {"units": 1.0},
    }
    result = {"output": "right"}

    out = await _attach_zk_proof(receipt, _FakeJob(constraints={"zk_proof_required": True}), result)

    assert out["zk_status"] == "verified"
    assert out["computation_correct"] is True


@pytest.mark.asyncio
async def test_release_payment_blocks_when_computation_correct_is_false(db_session, monkeypatch):
    monkeypatch.setattr(
        "coordinator_api.contexts.payments.services.payments.AITBCHTTPClient",
        _NeverCallClient,
    )
    job, payment = _completed_job_with_receipt(
        JobService(db_session), db_session, receipt={"zk_status": "verified", "computation_correct": False}
    )

    released = await PaymentService(db_session).release_payment("client1", job.id, payment.id)

    assert released is False


@pytest.mark.asyncio
async def test_release_payment_allows_when_computation_correct_is_true(db_session, monkeypatch):
    """A verified receipt with computation_correct=True is still blocked at the chain mock."""
    blocked = {"calls": 0}

    class _FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def post(self, *args, **kwargs):
            blocked["calls"] += 1
            return {"success": False, "message": "chain down"}

    monkeypatch.setattr(
        "coordinator_api.contexts.payments.services.payments.AITBCHTTPClient",
        _FailingClient,
    )
    job, payment = _completed_job_with_receipt(
        JobService(db_session), db_session, receipt={"zk_status": "verified", "computation_correct": True}
    )

    released = await PaymentService(db_session).release_payment("client1", job.id, payment.id)

    assert blocked["calls"] == 1
    assert released is False
