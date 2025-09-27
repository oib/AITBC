from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest
from nacl.signing import SigningKey

from aitbc_crypto.signing import ReceiptSigner

from aitbc_sdk.receipts import (
    CoordinatorReceiptClient,
    ReceiptVerification,
    verify_receipt,
    verify_receipts,
)


@pytest.fixture()
def sample_payload() -> Dict[str, object]:
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
        "metadata": {
            "job_payload": {"task": "render"},
            "job_constraints": {},
            "result": {"duration": 5},
            "metrics": {"duration_ms": 5000},
        },
    }


def _sign_receipt(payload: Dict[str, object], key: SigningKey) -> Dict[str, object]:
    signer = ReceiptSigner(key.encode())
    receipt = dict(payload)
    receipt["signature"] = signer.sign(payload)
    return receipt


def test_verify_receipt_success(sample_payload: Dict[str, object]) -> None:
    signing_key = SigningKey.generate()
    receipt = _sign_receipt(sample_payload, signing_key)

    result = verify_receipt(receipt)
    assert isinstance(result, ReceiptVerification)
    assert result.miner_signature.valid is True
    assert result.verified is True


def test_verify_receipt_failure(sample_payload: Dict[str, object]) -> None:
    signing_key = SigningKey.generate()
    receipt = _sign_receipt(sample_payload, signing_key)
    receipt["metadata"] = {"job_payload": {"task": "tampered"}}

    result = verify_receipt(receipt)
    assert result.miner_signature.valid is False
    assert result.verified is False


def test_verify_receipts_batch(sample_payload: Dict[str, object]) -> None:
    signing_key = SigningKey.generate()
    receipt = _sign_receipt(sample_payload, signing_key)

    results = verify_receipts([receipt, receipt])
    assert len(results) == 2
    assert all(item.verified for item in results)


@dataclass
class _DummyResponse:
    status_code: int
    data: object

    def json(self) -> object:
        return self.data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class _DummyClient:
    def __init__(self, responses: List[_DummyResponse]):
        self._responses = responses

    def get(self, url: str, *args, **kwargs) -> _DummyResponse:
        if not self._responses:
            raise AssertionError("no more responses configured")
        return self._responses.pop(0)

    def __enter__(self) -> "_DummyClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass


def test_coordinator_receipt_client_latest(monkeypatch, sample_payload: Dict[str, object]) -> None:
    signing_key = SigningKey.generate()
    receipt = _sign_receipt(sample_payload, signing_key)

    def _mock_client(self) -> _DummyClient:
        return _DummyClient([_DummyResponse(200, receipt)])

    monkeypatch.setattr(CoordinatorReceiptClient, "_client", _mock_client)

    client = CoordinatorReceiptClient("https://coordinator", "api")
    fetched = client.fetch_latest("job-123")
    assert fetched == receipt


def test_coordinator_receipt_client_history(monkeypatch, sample_payload: Dict[str, object]) -> None:
    signing_key = SigningKey.generate()
    receipts = [_sign_receipt(sample_payload, signing_key)]

    def _mock_client(self) -> _DummyClient:
        return _DummyClient([_DummyResponse(200, {"items": receipts})])

    monkeypatch.setattr(CoordinatorReceiptClient, "_client", _mock_client)

    client = CoordinatorReceiptClient("https://coordinator", "api")
    history = client.fetch_history("job-123")
    assert history == receipts


def test_coordinator_receipt_client_latest_404(monkeypatch) -> None:
    def _mock_client(self) -> _DummyClient:
        return _DummyClient([_DummyResponse(404, {})])

    monkeypatch.setattr(CoordinatorReceiptClient, "_client", _mock_client)

    client = CoordinatorReceiptClient("https://coordinator", "api")
    assert client.fetch_latest("job-missing") is None
