"""Unit tests for v0.16.2 Agent A SDK deliverables."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
import requests

from aitbc.exceptions import CircuitBreakerOpenError, RetryError
from aitbc.types import (
    DeveloperProfile,
    GrantMilestone,
    GrantProposal,
    GrantSummary,
    RegistryEntry,
    SDKRequest,
    SDKResponse,
    WalletBalance,
)
from aitbc_sdk import (
    CoordinatorAPIClient,
    RegistryClient,
    SDKCircuitBreaker,
    SDKRetryPolicy,
    WalletClient,
)


def test_sdk_exports_types() -> None:
    """``aitbc.types`` exposes the shared SDK models."""
    assert SDKRequest is not None
    assert SDKResponse is not None
    assert WalletBalance is not None
    assert RegistryEntry is not None
    assert GrantSummary is not None
    assert GrantProposal is not None
    assert GrantMilestone is not None
    assert DeveloperProfile is not None


def _mock_http_client(mock_class: Mock, response: dict[str, object]) -> Mock:
    instance = Mock()
    instance.get.return_value = response
    instance.post.return_value = response
    mock_class.return_value = instance
    return instance


def test_coordinator_client_wallet_balance() -> None:
    with patch("aitbc_sdk.client.AITBCHTTPClient") as mock_class:
        _mock_http_client(mock_class, {"wallet_id": "w-1", "balance": "100.5", "asset": "AITBC"})
        client = CoordinatorAPIClient("http://api.test", api_key="key")
        balance = client.wallet.get_balance("w-1")
        assert balance.wallet_id == "w-1"
        assert balance.balance == Decimal("100.5")
        assert balance.asset == "AITBC"


def test_coordinator_client_registry() -> None:
    with patch("aitbc_sdk.client.AITBCHTTPClient") as mock_class:
        _mock_http_client(
            mock_class,
            {
                "items": [
                    {"id": "e1", "name": "Alice", "wallet_address": "0xabc"},
                    {"entry_id": "e2", "name": "Bob", "address": "0xdef"},
                ]
            },
        )
        client = CoordinatorAPIClient("http://api.test")
        entries = client.registry.list_registry(role="developer")
        assert len(entries) == 2
        assert entries[0].id == "e1"
        assert entries[1].id == "e2"


def test_coordinator_client_get_grant_summary() -> None:
    with patch("aitbc_sdk.client.AITBCHTTPClient") as mock_class:
        _mock_http_client(
            mock_class,
            {
                "grant_id": "g1",
                "title": "OpenClaw",
                "status": "active",
                "requested_amount": "1000",
                "approved_amount": "500",
            },
        )
        client = CoordinatorAPIClient("http://api.test")
        summary = client.get_grant_summary("g1")
        assert summary.grant_id == "g1"
        assert summary.title == "OpenClaw"
        assert summary.requested_amount == Decimal("1000")
        assert summary.approved_amount == Decimal("500")


def test_wallet_client_send_payment() -> None:
    with patch("aitbc_sdk.client.AITBCHTTPClient") as mock_class:
        instance = _mock_http_client(mock_class, {"payment_id": "p1", "status": "submitted"})
        client = WalletClient(Mock())
        client._http = instance  # type: ignore[method-assign]
        result = client.send_payment("w-1", "recipient", 10, "wallet-password")
        assert result["payment_id"] == "p1"
        instance.post.assert_called_once()
        # Pin the route. This asserted only the call count, so it stayed green while the
        # client posted to /v1/wallets/{id}/payments, which no service has ever served.
        assert instance.post.call_args.args[0] == "/v1/wallets/w-1/send"


def test_registry_client_get_developer() -> None:
    with patch("aitbc_sdk.client.AITBCHTTPClient") as mock_class:
        _mock_http_client(mock_class, {"id": "e1", "name": "Alice", "wallet_address": "0xabc"})
        client = RegistryClient(Mock())
        client._http = mock_class.return_value  # type: ignore[method-assign]
        entry = client.get_developer("0xabc")
        assert entry.id == "e1"
        assert entry.name == "Alice"
        assert entry.wallet_address == "0xabc"


@patch("aitbc.network.retry_policy.time.sleep")
def test_retry_policy_retries_then_succeeds(mock_sleep: Mock) -> None:
    func = Mock(side_effect=[requests.RequestException("boom"), {"ok": True}])
    policy = SDKRetryPolicy(max_retries=3)
    result = policy.execute(func)
    assert result == {"ok": True}
    assert func.call_count == 2


@patch("aitbc.network.retry_policy.time.sleep")
def test_retry_policy_exhausts_retries(mock_sleep: Mock) -> None:
    func = Mock(side_effect=requests.RequestException("boom"))
    policy = SDKRetryPolicy(max_retries=2)
    with pytest.raises(RetryError):
        policy.execute(func)
    assert func.call_count == 3  # initial + 2 retries


def test_circuit_breaker_opens_after_threshold() -> None:
    breaker = SDKCircuitBreaker(threshold=2)
    failing = Mock(side_effect=RuntimeError("down"))

    with pytest.raises(RuntimeError):
        breaker.call(failing)
    with pytest.raises(RuntimeError):
        breaker.call(failing)
    with pytest.raises(CircuitBreakerOpenError):
        breaker.call(failing)


def test_circuit_breaker_closes_after_success() -> None:
    breaker = SDKCircuitBreaker(threshold=2)
    assert breaker.call(lambda: "ok") == "ok"
    assert breaker.is_open() is False


def test_lazy_sdk_imports_client() -> None:
    from aitbc_sdk import CoordinatorClient as _CoordinatorClient  # noqa: F401
    from aitbc_sdk import SDKRetryPolicy as _SDKRetryPolicy  # noqa: F401
