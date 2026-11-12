"""#1863 respin pins: exception types that escaped the narrowed _OPS_ERRORS tuples.

Each test fails on the unfixed narrowing (exception propagates / 500) and
passes once the raise surface is covered.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from coordinator_api.contexts.compliance.hipaa import ConsentRecord as SQLConsentRecord
from coordinator_api.contexts.compliance.services.consent_store import SQLConsentStore
from coordinator_api.contexts.infrastructure.routers.users import _verify_wallet_signature
from coordinator_api.contexts.multimodal.routers import multi_modal_rl
from coordinator_api.contexts.payments.services import payments as payments_module
from coordinator_api.contexts.infrastructure.services import jobs as jobs_module


def test_wallet_signature_bad_signature_returns_false() -> None:
    """eth_keys BadSignature / eth_utils ValidationError must not escape as 500."""
    # Well-formed hex but wrong length -> recover_message raises ValidationError.
    assert _verify_wallet_signature("0x" + "ab" * 20, "0x" + "00" * 64, "nonce-1") is False


def test_multi_modal_rate_limit_error_is_soft_fail(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """AITBCHTTPClient RateLimitError/CircuitBreakerOpenError -> error JSON, not 500."""
    from aitbc.exceptions import RateLimitError

    def _raise(*args: object, **kwargs: object) -> None:
        raise RateLimitError("rate limited")

    monkeypatch.setattr(multi_modal_rl.AITBCHTTPClient, "post", _raise)
    resp = client.post(
        "/v1/multi-modal-rl/jobs",
        json={"task_type": "inference", "task_data": {"prompt": "hi"}},
        headers={"Authorization": "Bearer " + _token()},
    )
    assert resp.status_code == 200
    assert "error" in resp.json()


def _token() -> str:
    from aitbc.auth import create_access_token

    return create_access_token("u", "client")


def test_consent_store_skips_unknown_classification() -> None:
    """normalize_classification's InvalidClassificationError must be skipped, not crash."""
    row = SQLConsentRecord(
        subject_id="s1",
        purpose="treatment",
        meta={"classifications": ["not-a-real-class", "phi"]},
    )
    record = SQLConsentStore.__new__(SQLConsentStore)._to_aitbc(row)
    assert record is not None
    assert len(record.classifications) == 1


def test_payments_tuple_covers_energy_pricing_error() -> None:
    from aitbc.market.energy_pricing import EnergyPricingError

    assert EnergyPricingError in payments_module._OPS_ERRORS


def test_multi_modal_tuple_covers_aitbc_error_family() -> None:
    from aitbc.exceptions import AITBCError, CircuitBreakerOpenError, RateLimitError, RetryError

    for exc in (AITBCError, RateLimitError, CircuitBreakerOpenError, RetryError):
        assert exc in multi_modal_rl._OPS_ERRORS or any(issubclass(exc, t) for t in multi_modal_rl._OPS_ERRORS)


def test_jobs_tuple_covers_invalid_operation() -> None:
    from decimal import InvalidOperation

    assert InvalidOperation in jobs_module._OPS_ERRORS
