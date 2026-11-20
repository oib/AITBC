"""#2331 tier (a): bind the miner-reported circuit output to the expected one.

The ``receipt_model`` Groth16 proof commits to ``model.compute_output(prompt)``
in its public ``output_hash`` — but the witness is built coordinator-side from
``compute_public_inputs``, so the proof verifies no matter what the miner put
in ``result.output``. Before this check a miner could return arbitrary output
and still collect ``zk_status: verified`` plus released escrow.

These tests pin the pure-code equality check: a matching output keeps today's
behavior; a tampered or unparseable output fails closed with
``zk_status`` in ``{output_mismatch, output_unparseable, output_check_error}``
and ``computation_correct=False``, and escrow never releases on it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.routers import miner
from coordinator_api.contexts.infrastructure.routers.miner import (
    _CIRCUIT_OUTPUT_FAILURE_STATUSES,
    _attach_zk_proof,
    _parse_circuit_output,
    _settle_escrowed_payment,
)
from coordinator_api.contexts.payments.services.payments import _computation_is_correct
from coordinator_api.contexts.zk_applications.services import model_registry

PROMPT = "hello circuit"


def _job(*, model="linear-1", constraints=None, prompt=PROMPT):
    return SimpleNamespace(
        id="job-2331",
        payload={"prompt": prompt, "model": model},
        constraints=constraints or {},
    )


def _expected_output(job) -> list[int]:
    model = model_registry.get_model("linear-1")
    assert model is not None
    return model_registry.expected_output_values(job, model)


def _result(output) -> dict:
    return {"output": output, "model": "linear-1"}


class _FakeZKProofService:
    """Stands in for zk_proof_service — no snarkjs/node toolchain needed."""

    def __init__(self, *, enabled=True, verify_ok=True):
        self._enabled = enabled
        self._verify_ok = verify_ok
        self.generate_calls = 0
        self.verify_calls = 0

    def is_enabled(self) -> bool:
        return self._enabled

    async def generate_model_proof(self, job, result):
        self.generate_calls += 1
        return {"proof": {"a": "b"}, "public_signals": ["1", "2", "3", "4"], "circuit": "receipt_model"}

    async def verify_model_proof(self, proof, public_signals, expected_public):
        self.verify_calls += 1
        if self._verify_ok:
            return {"verified": True, "computation_correct": True, "privacy_preserved": True}
        return {"verified": True, "computation_correct": False, "error": "public_signal_mismatch"}

    async def generate_receipt_proof(self, receipt, job_result):
        return None


@pytest.fixture
def fake_zk(monkeypatch):
    svc = _FakeZKProofService()
    monkeypatch.setattr(miner, "zk_proof_service", svc)
    # compute_public_inputs shells out to node/poseidon-lite for the proof
    # witness; the #2331 check under test uses expected_output_values (pure
    # Python) and the fake verifier ignores the signals, so stub the witness
    # builder to keep these tests hermetic.
    monkeypatch.setattr(
        model_registry,
        "compute_public_inputs",
        lambda job, result, model: {
            "public_inputs": {"input_hash": "0", "model_hash": "0", "output_hash": "0", "model_id": "0"},
            "private_inputs": {},
        },
    )
    return svc


# ---------------------------------------------------------------------------
# _parse_circuit_output
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_accepts_json_array_string():
    assert _parse_circuit_output(json.dumps([1, 2, 3])) == [1, 2, 3]


@pytest.mark.unit
def test_parse_accepts_bare_list_and_digit_strings():
    assert _parse_circuit_output([1, "2", 3]) == [1, 2, 3]


@pytest.mark.unit
def test_parse_rejects_non_list_and_garbage():
    assert _parse_circuit_output("not json") is None
    assert _parse_circuit_output('{"a": 1}') is None
    assert _parse_circuit_output(42) is None
    assert _parse_circuit_output([1, True, 3]) is None  # bool is an int subclass
    assert _parse_circuit_output([1, 2.5, 3]) is None
    assert _parse_circuit_output(["-1", "2"]) is None  # field elements are non-negative


# ---------------------------------------------------------------------------
# _attach_zk_proof — ZK-required circuit job
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_matching_output_verifies(fake_zk):
    job = _job(constraints={"zk_proof_required": True})
    receipt = {"receipt_id": "r1"}
    result = _result(json.dumps(_expected_output(job)))

    out = await _attach_zk_proof(dict(receipt), job, result)

    assert out["zk_status"] == "verified"
    assert out["computation_correct"] is True
    assert out["zk_proof"]["circuit"] == "receipt_model"
    assert fake_zk.generate_calls == 1
    assert fake_zk.verify_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tampered_output_fails_gate_and_skips_proof(fake_zk):
    job = _job(constraints={"zk_proof_required": True})
    expected = _expected_output(job)
    forged = [(v + 1) % 21888242871839275222246405745257275088696311157297823662689037894645226208583 for v in expected]
    assert forged != expected

    out = await _attach_zk_proof({"receipt_id": "r1"}, job, _result(json.dumps(forged)))

    assert out["zk_status"] == "output_mismatch"
    assert out["zk_status"] in _CIRCUIT_OUTPUT_FAILURE_STATUSES
    assert out["computation_correct"] is False
    assert "zk_proof" not in out
    # A mismatched output can never verify — do not spend a snarkjs proof on it.
    assert fake_zk.generate_calls == 0
    assert fake_zk.verify_calls == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unparseable_output_fails_closed(fake_zk):
    """A plain string (pre-#2330 miner shape) cannot be the field array — fail closed."""
    job = _job(constraints={"zk_proof_required": True})

    out = await _attach_zk_proof({"receipt_id": "r1"}, job, _result("model output"))

    assert out["zk_status"] == "output_unparseable"
    assert out["computation_correct"] is False
    assert fake_zk.generate_calls == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_circuit_job_unchanged(fake_zk):
    """Unregistered models keep the existing unsupported_model / TEE path."""
    job = _job(model="llama3.2:3b", constraints={"zk_proof_required": True})
    out = await _attach_zk_proof({"receipt_id": "r1"}, job, {"output": "anything", "model": "llama3.2:3b"})
    assert out["zk_status"] == "unsupported_model"
    assert out["computation_correct"] is False
    assert fake_zk.generate_calls == 0


# ---------------------------------------------------------------------------
# _attach_zk_proof — job below the ZK threshold (no proof required)
# ---------------------------------------------------------------------------


_BN128_FQ = 21888242871839275222246405745257275088696311157297823662689037894645226208583


def _tampered(expected: list[int]) -> list[int]:
    """A deterministically different field array of the same length."""
    forged = list(expected)
    forged[-1] = (forged[-1] + 1) % _BN128_FQ
    return forged


@pytest.mark.unit
@pytest.mark.asyncio
async def test_low_value_circuit_job_still_checks_output(fake_zk):
    """The check is pure code and cheap: a forged output must not collect on a
    cheap job either — zk_status carries the failure instead of 'not_required'."""
    job = _job()  # no zk_proof_required, no payment amount -> not required
    out = await _attach_zk_proof({"receipt_id": "r1"}, job, _result(json.dumps(_tampered(_expected_output(job)))))
    assert out["zk_status"] == "output_mismatch"
    assert out["computation_correct"] is False
    assert fake_zk.generate_calls == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_low_value_circuit_job_matching_output_unchanged(fake_zk):
    job = _job()
    result = _result(json.dumps(_expected_output(job)))
    out = await _attach_zk_proof({"receipt_id": "r1"}, job, result)
    assert out["zk_status"] == "not_required"
    assert out["computation_correct"] is True
    assert fake_zk.generate_calls == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_low_value_non_circuit_job_unchanged(fake_zk):
    job = _job(model="llama3.2:3b")
    out = await _attach_zk_proof({"receipt_id": "r1"}, job, {"output": "free text", "model": "llama3.2:3b"})
    assert out["zk_status"] == "not_required"
    assert out["computation_correct"] is True


# ---------------------------------------------------------------------------
# Escrow settlement must refuse the failure statuses even when ungated
# ---------------------------------------------------------------------------


def _db_job(session, *, constraints=None) -> Job:
    job = Job(
        id="job-2331-settle",
        client_id="client-1",
        state="COMPLETED",
        payload={"prompt": PROMPT, "model": "linear-1"},
        constraints=constraints or {},
        assigned_miner_id="miner-b",
        payment_id="pay-2331",
        receipt={"receipt_id": "r1"},
        receipt_id="r1",
        completed_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(job)
    session.commit()
    return job


@pytest.mark.unit
@pytest.mark.asyncio
async def test_settle_blocked_on_output_mismatch_even_when_ungated(db_session):
    """A non-ZK-gated job with a forged circuit output must not release escrow."""
    job = _db_job(db_session)  # no zk_proof_required, amount below threshold
    receipt = {"zk_status": "output_mismatch", "computation_correct": False}
    assert _computation_is_correct(receipt, job) is False

    release = AsyncMock(return_value=True)
    with patch("coordinator_api.contexts.payments.services.payments.PaymentService") as payment_cls:
        payment_cls.return_value.release_payment = release
        ok = await _settle_escrowed_payment(db_session, job, Decimal("0.5"), receipt, job.id)

    assert ok is False
    release.assert_not_awaited()
    db_session.expire_all()
    stored = db_session.get(Job, job.id)
    assert "output_mismatch" in (stored.error or "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_settle_unaffected_for_verified_receipt(db_session):
    """Sanity: a normal ungated receipt still reaches the settle path."""
    job = _db_job(db_session, constraints={"acceptance_window_seconds": 0})
    receipt = {"zk_status": "not_required", "computation_correct": True}

    with patch("coordinator_api.contexts.payments.services.payments.PaymentService") as payment_cls:
        payment_cls.return_value.release_payment = AsyncMock(return_value=True)
        ok = await _settle_escrowed_payment(db_session, job, Decimal("0.5"), receipt, job.id)

    # window=0 -> same-request release through the stubbed PaymentService.
    assert ok is True
