"""#3080 (AUDIT-ATASK-ESCROW-1): buyer-attested escrow release.

CRIT-1: ``POST /tasks/{id}/complete`` released an on-chain escrow on the
provider's signature alone — the payee signed off its own payment, so
lock→immediately-release was a theft primitive. An escrow with
``tx_hash_lock`` now also requires ``job_tx_hash``: the hash of the
buyer-signed ``software_job`` completion record. ``_verify_buyer_attestation``
checks the same binding the chain's ``_verify_job_tx_proof`` enforces at
release, plus two coordinator-side binds the chain route does not:

* HIGH-2: the billed ``amount_units`` may not exceed the buyer-attested
  ``actual_cost`` (overbilling cap — the accepted quote binds the release);
* the asserted ``result_hash`` must equal the attested one.

HIGH-4: ``payment.timeout_seconds`` below
``settings.task_payment_min_timeout_seconds`` is refused at submit — a
near-zero timeout let the expire sweep refund the lock before work finished.
"""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aitbc.crypto import EscrowStatus, PaymentEscrow  # noqa: E402
from aitbc.crypto.crypto import (  # noqa: E402
    derive_ethereum_address,
    generate_ethereum_private_key,
    sign_transaction_data,
)

from agent_app import state  # noqa: E402
from agent_app.config import settings  # noqa: E402
from agent_app.models import TaskPayment, TaskSubmission  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402

BUYER = "0xBuyer"
JOB_TX = "0x" + "ab" * 32


def _sealed_job_record(task_id: str, provider: str, **over) -> dict:
    """The transaction_status answer for a sealed buyer software_job record."""
    payload = {
        "action": "software_job",
        "status": "completed",
        "job_id": task_id,
        "result_hash": "0x" + "cd" * 32,
        "buyer_address": BUYER,
        "provider_address": provider,
        "actual_cost": "1",
    }
    payload.update(over)
    return {
        "status": "confirmed",
        "block_height": 11,
        "type": "GPU_MARKET",
        "sender": BUYER,
        "payload": payload,
    }


class _AttestingRPC:
    """ChainEscrowClient stand-in: sealed attestation record + release capture."""

    def __init__(self, record: dict | None = None):
        self.record = record
        self.release_kwargs: dict = {}
        self.release_calls = 0

    def transaction_status(self, tx_hash, chain_id=None):
        if tx_hash != JOB_TX:
            return None
        return self.record

    def release(self, job_id, **kwargs):
        self.release_calls += 1
        self.release_kwargs = kwargs
        return {"tx_hash": "0xrel"}


@pytest.fixture
def env(monkeypatch):
    escrow = PaymentEscrow()
    distributor = MagicMock()
    distributor.submit_task = AsyncMock(return_value=True)
    monkeypatch.setattr(state, "payment_escrow", escrow)
    monkeypatch.setattr(state, "task_distributor", distributor)
    monkeypatch.setattr(state, "escrow_rpc", None)
    monkeypatch.setattr(settings, "task_payment_escrow_enabled", True)
    monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
    app = FastAPI()
    app.include_router(tasks_router.router, prefix="/v1")
    client = TestClient(app)
    return client, escrow


def _locked(escrow: PaymentEscrow, task_id: str, agent: str, amount: int = 100, onchain: bool = True):
    entry = escrow.create_escrow(task_id=task_id, chain_id="c", requester=BUYER, agent=agent, amount=amount)
    escrow.lock(entry.escrow_id)
    if onchain:
        entry.tx_hash_lock = "0x" + "ef" * 32
    return entry


def _complete_sig(task_id: str, pk: str, **body_extra):
    """Provider-signed complete body (legacy signature form).

    The verifier rebuilds the signed fields from the *body*, so the signature
    must cover the amount_units actually sent (0 when omitted).
    """
    signed_at = int(time.time())
    body: dict = {"signed_at": signed_at, **body_extra}
    fields = {
        "action": "complete",
        "task_id": task_id,
        "signed_at": signed_at,
        "amount_units": body.get("amount_units") or 0,
    }
    body["signature"] = sign_transaction_data(fields, pk)
    return body


class TestSelfReleaseRequiresAttestation:
    """CRIT-1: provider signature alone must not release an on-chain escrow."""

    def test_complete_without_job_tx_hash_409(self, env, monkeypatch):
        client, escrow = env
        pk = generate_ethereum_private_key()
        rpc = _AttestingRPC(_sealed_job_record("t-self", derive_ethereum_address(pk)))
        monkeypatch.setattr(state, "escrow_rpc", rpc)
        _locked(escrow, "t-self", derive_ethereum_address(pk))

        resp = client.post("/v1/tasks/t-self/complete", json=_complete_sig("t-self", pk))

        assert resp.status_code == 409, resp.text
        assert "attestation" in resp.json()["detail"].lower()
        assert rpc.release_calls == 0
        assert escrow.get_escrow_for_task("t-self").status == EscrowStatus.LOCKED

    def test_complete_malformed_job_tx_hash_400(self, env, monkeypatch):
        client, escrow = env
        pk = generate_ethereum_private_key()
        monkeypatch.setattr(state, "escrow_rpc", _AttestingRPC(None))
        _locked(escrow, "t-mal", derive_ethereum_address(pk))

        resp = client.post(
            "/v1/tasks/t-mal/complete",
            json=_complete_sig("t-mal", pk, job_tx_hash="not-a-hash"),
        )
        assert resp.status_code == 400, resp.text

    def test_bookkeeping_escrow_keeps_provider_signature_release(self, env, monkeypatch):
        """No tx_hash_lock → no on-chain funds → the old contract still holds."""
        client, escrow = env
        pk = generate_ethereum_private_key()
        monkeypatch.setattr(state, "escrow_rpc", None)
        _locked(escrow, "t-book", derive_ethereum_address(pk), onchain=False)

        resp = client.post("/v1/tasks/t-book/complete", json=_complete_sig("t-book", pk))

        assert resp.status_code == 200, resp.text
        assert escrow.get_escrow_for_task("t-book").status == EscrowStatus.RELEASED


class TestAttestationBinding:
    """The job_tx_hash must resolve to a sealed record bound to this escrow."""

    def _post(self, client, task_id, pk, **extra):
        return client.post(f"/v1/tasks/{task_id}/complete", json=_complete_sig(task_id, pk, **extra))

    def test_unresolvable_attestation_503(self, env, monkeypatch):
        client, escrow = env
        pk = generate_ethereum_private_key()
        monkeypatch.setattr(state, "escrow_rpc", _AttestingRPC(None))
        _locked(escrow, "t-404", derive_ethereum_address(pk))

        resp = self._post(client, "t-404", pk, job_tx_hash=JOB_TX)
        assert resp.status_code == 503, resp.text
        assert escrow.get_escrow_for_task("t-404").status == EscrowStatus.LOCKED

    def test_unsealed_attestation_409_retryable(self, env, monkeypatch):
        client, escrow = env
        pk = generate_ethereum_private_key()
        record = _sealed_job_record("t-pend", derive_ethereum_address(pk))
        record["status"] = "pending"
        record["block_height"] = None
        record["state"] = "pending"
        monkeypatch.setattr(state, "escrow_rpc", _AttestingRPC(record))
        _locked(escrow, "t-pend", derive_ethereum_address(pk))

        resp = self._post(client, "t-pend", pk, job_tx_hash=JOB_TX)
        assert resp.status_code == 409, resp.text
        assert "not sealed" in resp.json()["detail"]

    def test_wrong_job_id_409(self, env, monkeypatch):
        client, escrow = env
        pk = generate_ethereum_private_key()
        provider = derive_ethereum_address(pk)
        monkeypatch.setattr(state, "escrow_rpc", _AttestingRPC(_sealed_job_record("t-other", provider)))
        _locked(escrow, "t-wrong", provider)

        resp = self._post(client, "t-wrong", pk, job_tx_hash=JOB_TX)
        assert resp.status_code == 409, resp.text

    def test_wrong_buyer_409(self, env, monkeypatch):
        client, escrow = env
        pk = generate_ethereum_private_key()
        provider = derive_ethereum_address(pk)
        record = _sealed_job_record("t-buyer", provider, buyer_address="0xMallory")
        record["sender"] = "0xMallory"
        monkeypatch.setattr(state, "escrow_rpc", _AttestingRPC(record))
        _locked(escrow, "t-buyer", provider)

        resp = self._post(client, "t-buyer", pk, job_tx_hash=JOB_TX)
        assert resp.status_code == 409, resp.text

    def test_overbilled_amount_409(self, env, monkeypatch):
        """HIGH-2: billed units may not exceed the buyer-attested actual_cost."""
        client, escrow = env
        pk = generate_ethereum_private_key()
        provider = derive_ethereum_address(pk)
        # actual_cost "0.000001" AIT = 36 units; billing 100 must refuse.
        record = _sealed_job_record("t-over", provider, actual_cost="0.000001")
        monkeypatch.setattr(state, "escrow_rpc", _AttestingRPC(record))
        _locked(escrow, "t-over", provider)

        resp = self._post(client, "t-over", pk, job_tx_hash=JOB_TX, amount_units=100)

        assert resp.status_code == 409, resp.text
        assert "attested cost" in resp.json()["detail"]
        assert escrow.get_escrow_for_task("t-over").status == EscrowStatus.LOCKED

    def test_result_hash_mismatch_409(self, env, monkeypatch):
        client, escrow = env
        pk = generate_ethereum_private_key()
        provider = derive_ethereum_address(pk)
        monkeypatch.setattr(state, "escrow_rpc", _AttestingRPC(_sealed_job_record("t-rh", provider)))
        _locked(escrow, "t-rh", provider)

        resp = self._post(client, "t-rh", pk, job_tx_hash=JOB_TX, result_hash="0x" + "00" * 32)

        assert resp.status_code == 409, resp.text
        assert "result_hash" in resp.json()["detail"]

    def test_attested_release_succeeds(self, env, monkeypatch):
        """End-to-end: sealed bound attestation + in-cap billing → release."""
        client, escrow = env
        pk = generate_ethereum_private_key()
        provider = derive_ethereum_address(pk)
        rpc = _AttestingRPC(_sealed_job_record("t-ok", provider, actual_cost="0.01"))
        monkeypatch.setattr(state, "escrow_rpc", rpc)
        _locked(escrow, "t-ok", provider)

        attested = "0x" + "cd" * 32
        resp = self._post(
            client,
            "t-ok",
            pk,
            job_tx_hash=JOB_TX,
            amount_units=30,
            result_hash=attested,
        )

        assert resp.status_code == 200, resp.text
        assert rpc.release_calls == 1
        assert rpc.release_kwargs["job_tx_hash"] == JOB_TX
        assert rpc.release_kwargs["amount_units"] == 30
        assert escrow.get_escrow_for_task("t-ok").status == EscrowStatus.RELEASED


class TestMinTimeoutFloor:
    """HIGH-4: a near-zero escrow timeout is a work-theft primitive."""

    def _submission(self, task_id: str, timeout: float) -> TaskSubmission:
        return TaskSubmission(
            task_data={"task_id": task_id, "task_type": "test"},
            payment=TaskPayment(amount=100, requester=BUYER, agent="0xAgent", timeout_seconds=timeout),
        )

    def test_below_floor_rejected(self, env):
        client, escrow = env
        floor = settings.task_payment_min_timeout_seconds
        resp = client.post("/v1/tasks/submit", json=self._submission("t-fast", floor - 1).model_dump())
        assert resp.status_code == 400, resp.text
        assert "timeout_seconds" in resp.json()["detail"]
        assert escrow.get_escrow_for_task("t-fast") is None

    def test_at_floor_accepted(self, env, monkeypatch):
        client, _ = env
        monkeypatch.setattr(state, "escrow_rpc", None)
        # No lock_tx → bookkeeping path; still exercises the floor check.
        resp = client.post(
            "/v1/tasks/submit",
            json=self._submission("t-floor", settings.task_payment_min_timeout_seconds).model_dump(),
        )
        assert resp.status_code == 200, resp.text
