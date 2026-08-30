"""Tests for the receipt_public ZK proof integration (P2.1)."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from coordinator_api.contexts.zk_applications.services import zk_proofs
from coordinator_api.contexts.zk_applications.services.zk_proofs import ZKProofService
from coordinator_api.schemas import JobResult, Receipt


@pytest.mark.asyncio
@pytest.mark.skipif(
    not ("/opt/aitbc/apps/zk-circuits/receipt_public_0001.zkey" and True),
    reason="receipt_public circuit artifacts not built",
)
async def test_generate_and_verify_receipt_public_proof(monkeypatch):
    monkeypatch.setattr(zk_proofs, "ENABLE_ZK_VERIFICATION", True)
    svc = ZKProofService()
    assert "receipt_public" in svc.available_circuits, f"available: {list(svc.available_circuits)}"

    receipt = Receipt(
        receiptId="r_test_1234",
        miner="0x28241C034aDF9ca346BE0C3596FF30e4905bD940",
        coordinator="0xcoordinator",
        issuedAt=datetime.now(UTC),
        status="completed",
        payload={"units": 12.5, "job_id": "job_test_1234"},
    )
    job_result = JobResult(result={"output": "hello world", "output_hash": "0xabc"})

    proof = await svc.generate_receipt_proof(receipt, job_result)
    assert proof is not None
    assert proof["circuit"] == "receipt_public"
    assert len(proof["public_signals"]) == 1
    assert proof.get("receipt")

    result = await svc.verify_proof(proof["proof"], proof["public_signals"], "receipt_public")
    assert result["verified"] is True
    assert result["computation_correct"] is False


def test_zk_threshold_enabled_for_high_value():
    from coordinator_api.contexts.infrastructure.routers.miner import _zk_required_for

    class FakeJob:
        constraints = {}
        payload = {"model": "linear-1"}

    assert _zk_required_for(FakeJob(), payment_amount=Decimal("10.0")) is True


def test_zk_require_proof_env_forces_zk_for_every_job(monkeypatch):
    """COORDINATOR_ZK_REQUIRE=true must override the payment threshold."""
    from coordinator_api.contexts.infrastructure.routers import miner

    class LowValueJob:
        constraints = {}
        payload = {"model": "linear-1"}

    assert miner._zk_required_for(LowValueJob(), payment_amount=Decimal("1.0")) is False
    monkeypatch.setattr(miner, "_ZK_REQUIRE_PROOF", True)
    assert miner._zk_required_for(LowValueJob()) is True


def test_zk_require_proof_env_forces_payment_gate(monkeypatch):
    """COORDINATOR_ZK_REQUIRE=true must force the release/refund/sweeper gate too."""
    from coordinator_api.contexts.payments.services import payments

    class FakeJob:
        constraints = {}
        payload = {"model": "linear-1"}

    assert payments._zk_required_for_payment(Decimal("1.0"), FakeJob()) is False
    monkeypatch.setattr(payments, "_ZK_REQUIRE_PROOF", True)
    assert payments._zk_required_for_payment(Decimal("1.0"), FakeJob()) is True
