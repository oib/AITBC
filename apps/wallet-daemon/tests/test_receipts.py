from __future__ import annotations

import pytest
from nacl.signing import SigningKey

from app.receipts import ReceiptValidationResult, ReceiptVerifierService


@pytest.fixture()
def sample_receipt() -> dict:
    return {
        "version": "1.0",
        "receipt_id": "rcpt-1",
        "job_id": "job-123",
        "provider": "miner-abc",
        "client": "client-xyz",
        "units": 1.0,
        "unit_type": "gpu_seconds",
        "price": 3.5,
        "started_at": 1700000000,
        "completed_at": 1700000005,
        "metadata": {},
    }


class _DummyClient:
    def __init__(self, latest=None, history=None):
        self.latest = latest
        self.history = history or []

    def fetch_latest(self, job_id: str):
        return self.latest

    def fetch_history(self, job_id: str):
        return list(self.history)


@pytest.fixture()
def signer():
    return SigningKey.generate()


@pytest.fixture()
def signed_receipt(sample_receipt: dict, signer: SigningKey) -> dict:
    from aitbc_crypto.signing import ReceiptSigner

    receipt = dict(sample_receipt)
    receipt["signature"] = ReceiptSigner(signer.encode()).sign(sample_receipt)
    return receipt


def test_verify_latest_success(monkeypatch, signed_receipt: dict):
    service = ReceiptVerifierService("http://coordinator", "api-key")
    client = _DummyClient(latest=signed_receipt)
    monkeypatch.setattr(service, "client", client)

    result = service.verify_latest("job-123")
    assert isinstance(result, ReceiptValidationResult)
    assert result.job_id == "job-123"
    assert result.receipt_id == "rcpt-1"
    assert result.miner_valid is True
    assert result.all_valid is True


def test_verify_latest_none(monkeypatch):
    service = ReceiptVerifierService("http://coordinator", "api-key")
    client = _DummyClient(latest=None)
    monkeypatch.setattr(service, "client", client)

    assert service.verify_latest("job-123") is None


def test_verify_history(monkeypatch, signed_receipt: dict):
    service = ReceiptVerifierService("http://coordinator", "api-key")
    client = _DummyClient(history=[signed_receipt])
    monkeypatch.setattr(service, "client", client)

    results = service.verify_history("job-123")
    assert len(results) == 1
    assert results[0].miner_valid is True
    assert results[0].job_id == "job-123"
