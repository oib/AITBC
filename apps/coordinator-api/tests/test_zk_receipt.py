"""Tests for the receipt_public ZK proof integration (P2.1)."""

import os
from datetime import UTC, datetime

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
    assert result["computation_correct"] is True


def test_zk_threshold_enabled_for_high_value():
    from coordinator_api.contexts.infrastructure.routers.miner import _zk_required_for

    class FakeJob:
        payment_amount = 10.0
        constraints = {}

    assert _zk_required_for(FakeJob()) is True
