"""Tests for the receipt_model model-execution ZK circuit."""

from __future__ import annotations


import pytest

from coordinator_api.contexts.zk_applications.services import model_registry
from coordinator_api.contexts.zk_applications.services import zk_proofs
from coordinator_api.contexts.zk_applications.services.zk_proofs import ZKProofService


@pytest.fixture(autouse=True)
def enable_zk_verification(monkeypatch):
    monkeypatch.setattr(zk_proofs, "ENABLE_ZK_VERIFICATION", True)


@pytest.mark.asyncio
async def test_receipt_model_generates_and_verifies():
    svc = ZKProofService()
    assert "receipt_model" in svc.available_circuits

    class FakeJob:
        payload = {"prompt": "hello test", "model": "linear-1"}
        constraints = {}

    result = {"output": "model output"}
    proof = await svc.generate_model_proof(FakeJob(), result)
    assert proof is not None
    assert proof["circuit"] == "receipt_model"
    assert proof["model_name"] == "linear-1"
    assert len(proof["public_signals"]) == 4

    model = model_registry.get_model("linear-1")
    inputs = model_registry.compute_public_inputs(FakeJob(), result, model)
    expected_public = model_registry.expected_public_signals(inputs["public_inputs"])

    verify_result = await svc.verify_model_proof(proof["proof"], proof["public_signals"], expected_public)
    assert verify_result["verified"] is True
    assert verify_result["computation_correct"] is True
    assert verify_result["privacy_preserved"] is True


@pytest.mark.asyncio
async def test_receipt_model_rejects_tampered_public_signals():
    svc = ZKProofService()

    class FakeJob:
        payload = {"prompt": "hello test", "model": "linear-1"}
        constraints = {}

    result = {"output": "model output"}
    proof = await svc.generate_model_proof(FakeJob(), result)

    bad_expected = ["1", "2", "3", "0"]
    verify_result = await svc.verify_model_proof(proof["proof"], proof["public_signals"], bad_expected)
    assert verify_result["verified"] is True
    assert verify_result["computation_correct"] is False
    assert verify_result["error"] == "public_signal_mismatch"


@pytest.mark.asyncio
async def test_receipt_model_unsupported_model_returns_none():
    svc = ZKProofService()

    class FakeJob:
        payload = {"prompt": "hello", "model": "llama3.2:3b"}
        constraints = {}

    proof = await svc.generate_model_proof(FakeJob(), {"output": "x"})
    assert proof is None


def test_model_registry_gets_model_by_name_or_id():
    model = model_registry.get_model("linear-1")
    assert model is not None
    assert model.model_id == 0

    model_by_id = model_registry.get_model("0")
    assert model_by_id is not None
    assert model_by_id.name == "linear-1"

    assert model_registry.get_model("unsupported") is None
