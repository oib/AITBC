from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest
import httpx
from nacl.signing import SigningKey

from aitbc_crypto.signing import ReceiptSigner

from aitbc_sdk.receipts import (
    CoordinatorReceiptClient,
    ReceiptFailure,
    ReceiptPage,
    ReceiptStatus,
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
    assert result.failure_reasons() == []
    assert result.miner_signature.reason is None


def test_verify_receipt_failure(sample_payload: Dict[str, object]) -> None:
    signing_key = SigningKey.generate()
    receipt = _sign_receipt(sample_payload, signing_key)
    receipt["metadata"] = {"job_payload": {"task": "tampered"}}

    result = verify_receipt(receipt)
    assert result.miner_signature.valid is False
    assert result.verified is False
    assert result.failure_reasons() == [f"miner_signature_invalid:{result.miner_signature.key_id}"]
    assert result.miner_signature.reason == "signature mismatch"


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
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=None, response=httpx.Response(self.status_code)
            )


def test_coordinator_receipt_client_latest(monkeypatch, sample_payload: Dict[str, object]) -> None:
    signing_key = SigningKey.generate()
    receipt = _sign_receipt(sample_payload, signing_key)

    def _mock_request(self, method, url, params=None, allow_404=False):
        assert method == "GET"
        return _DummyResponse(200, receipt)

    monkeypatch.setattr(CoordinatorReceiptClient, "_request", _mock_request)

    client = CoordinatorReceiptClient("https://coordinator", "api")
    fetched = client.fetch_latest("job-123")
    assert fetched == receipt


def test_coordinator_receipt_client_history(monkeypatch, sample_payload: Dict[str, object]) -> None:
    signing_key = SigningKey.generate()
    receipts = [_sign_receipt(sample_payload, signing_key)]

    def _mock_request(self, method, url, params=None, allow_404=False):
        assert method == "GET"
        return _DummyResponse(200, {"items": receipts})

    monkeypatch.setattr(CoordinatorReceiptClient, "_request", _mock_request)

    client = CoordinatorReceiptClient("https://coordinator", "api")
    history = client.fetch_history("job-123")
    assert history == receipts


def test_coordinator_receipt_client_latest_404(monkeypatch) -> None:
    def _mock_request(self, method, url, params=None, allow_404=False):
        assert allow_404 is True
        return None

    monkeypatch.setattr(CoordinatorReceiptClient, "_request", _mock_request)

    client = CoordinatorReceiptClient("https://coordinator", "api")
    assert client.fetch_latest("job-missing") is None


def test_fetch_receipts_page_list(monkeypatch, sample_payload: Dict[str, object]) -> None:
    items = [_sign_receipt(sample_payload, SigningKey.generate())]

    def _mock_request(self, method, url, params=None, allow_404=False):
        return _DummyResponse(200, items)

    monkeypatch.setattr(CoordinatorReceiptClient, "_request", _mock_request)

    client = CoordinatorReceiptClient("https://coordinator", "api")
    page = client.fetch_receipts_page(job_id="job-1")
    assert isinstance(page, ReceiptPage)
    assert page.items == items
    assert page.next_cursor is None


def test_fetch_receipts_page_dict_with_cursor(monkeypatch, sample_payload: Dict[str, object]) -> None:
    signing_key = SigningKey.generate()
    receipts = [_sign_receipt(sample_payload, signing_key)]
    responses = [
        _DummyResponse(200, {"items": receipts, "next_cursor": "cursor-1"}),
        _DummyResponse(200, {"items": receipts, "next": None}),
    ]

    def _mock_request(self, method, url, params=None, allow_404=False):
        assert method == "GET"
        return responses.pop(0)

    monkeypatch.setattr(CoordinatorReceiptClient, "_request", _mock_request)

    client = CoordinatorReceiptClient("https://coordinator", "api")
    first_page = client.fetch_receipts_page(job_id="job-1")
    assert first_page.next_cursor == "cursor-1"
    second_page = client.fetch_receipts_page(job_id="job-1", cursor=first_page.next_cursor)
    assert second_page.next_cursor is None


def test_iter_receipts_handles_pagination(monkeypatch, sample_payload: Dict[str, object]) -> None:
    signing_key = SigningKey.generate()
    receipt_a = _sign_receipt(sample_payload, signing_key)
    receipt_b = _sign_receipt(sample_payload, signing_key)
    responses = [
        _DummyResponse(200, {"items": [receipt_a], "next_cursor": "cursor-2"}),
        _DummyResponse(200, {"items": [receipt_b]}),
    ]

    def _mock_request(self, method, url, params=None, allow_404=False):
        return responses.pop(0)

    monkeypatch.setattr(CoordinatorReceiptClient, "_request", _mock_request)

    client = CoordinatorReceiptClient("https://coordinator", "api")
    collected = list(client.iter_receipts("job-123", page_size=1))
    assert collected == [receipt_a, receipt_b]


def test_request_retries_on_transient(monkeypatch, sample_payload: Dict[str, object]) -> None:
    responses: List[object] = [
        httpx.ReadTimeout("timeout"),
        _DummyResponse(429, {}),
        _DummyResponse(200, {}),
    ]

    class _RetryClient:
        def __init__(self, shared: List[object]):
            self._shared = shared

        def request(self, method: str, url: str, params=None):
            obj = self._shared.pop(0)
            if isinstance(obj, Exception):
                raise obj
            return obj

        def __enter__(self) -> "_RetryClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            pass

    def _mock_client(self):
        return _RetryClient(responses)

    monkeypatch.setattr(CoordinatorReceiptClient, "_client", _mock_client)
    monkeypatch.setattr("aitbc_sdk.receipts.time.sleep", lambda *_args: None)

    client = CoordinatorReceiptClient("https://coordinator", "api", max_retries=3)
    response = client._request("GET", "/v1/jobs/job-1/receipts")
    assert isinstance(response, _DummyResponse)
    assert response.status_code == 200


def test_summarize_receipts_all_verified(monkeypatch, sample_payload: Dict[str, object]) -> None:
    signing_key = SigningKey.generate()
    receipts = [_sign_receipt(sample_payload, signing_key) for _ in range(2)]

    def _fake_iter(self, job_id: str, page_size: int = 100):
        yield from receipts

    monkeypatch.setattr(CoordinatorReceiptClient, "iter_receipts", _fake_iter)

    client = CoordinatorReceiptClient("https://coordinator", "api")
    status = client.summarize_receipts("job-verified")

    assert isinstance(status, ReceiptStatus)
    assert status.total == 2
    assert status.verified_count == 2
    assert status.all_verified is True
    assert status.has_failures is False
    assert status.failure_reasons == {}
    assert status.failures == []
    assert isinstance(status.latest_verified, ReceiptVerification)


def test_summarize_receipts_with_failures(monkeypatch, sample_payload: Dict[str, object]) -> None:
    signing_key = SigningKey.generate()
    good = _sign_receipt(sample_payload, signing_key)

    bad = dict(good)
    bad["metadata"] = {"job_payload": {"task": "tampered"}}

    receipts = [good, bad]

    def _fake_iter(self, job_id: str, page_size: int = 100):
        yield from receipts

    monkeypatch.setattr(CoordinatorReceiptClient, "iter_receipts", _fake_iter)

    client = CoordinatorReceiptClient("https://coordinator", "api")
    status = client.summarize_receipts("job-mixed")

    assert status.total == 2
    assert status.verified_count == 1
    assert status.all_verified is False
    assert status.has_failures is True
    assert status.failure_reasons  # not empty
    assert status.failure_reasons[next(iter(status.failure_reasons))] == 1
    assert len(status.failures) == 1
    failure = status.failures[0]
    assert isinstance(failure, ReceiptFailure)
    assert failure.reasons
    assert failure.verification.miner_signature.valid is False
