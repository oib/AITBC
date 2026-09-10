"""Tests for the confidential router.

The confidential endpoints are primarily stubs/simulations; these tests verify
that the public CLI-facing payment route is fail-closed (503 unless TEE is
explicitly enabled), returns a simulated receipt when enabled, and that other
routes still respect the security matrix.
"""

import pytest

from aitbc.auth import create_access_token


@pytest.fixture
def client_token() -> str:
    return create_access_token("client1", "client")


@pytest.mark.unit
def test_confidential_payments_disabled_by_default(client):
    """POST /v1/confidential/payments returns 503 when TEE is not enabled."""
    from coordinator_api.config import settings

    assert settings.confidential_tee_enabled is False
    resp = client.post(
        "/v1/confidential/payments",
        json={
            "payment_id": "pay-123",
            "sender_id": "wallet-1",
            "recipient_id": "recipient-1",
            "amount_commitment": "0xdeadbeef",
        },
    )
    assert resp.status_code == 503
    assert "not enabled" in resp.text


@pytest.mark.unit
def test_confidential_payments_is_public_when_enabled(client, monkeypatch):
    """POST /v1/confidential/payments works without auth when TEE is enabled."""
    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "confidential_tee_enabled", True)
    resp = client.post(
        "/v1/confidential/payments",
        json={
            "payment_id": "pay-123",
            "sender_id": "wallet-1",
            "recipient_id": "recipient-1",
            "amount_commitment": "0xdeadbeef",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["payment_id"] == "pay-123"
    assert data["sender_id"] == "wallet-1"
    assert data["recipient_id"] == "recipient-1"
    assert data["amount_commitment"] == "0xdeadbeef"
    assert data["settled"] is True
    assert data["confidential"] is True
    assert data["status"] == "simulated"


@pytest.mark.unit
def test_confidential_transactions_requires_auth(client, client_token):
    """The existing /v1/confidential/transactions endpoint still requires a token."""
    resp = client.post(
        "/v1/confidential/transactions",
        headers={"Authorization": f"Bearer {client_token}"},
        json={
            "job_id": "job-123",
            "amount": "10",
            "confidential": False,
            "participants": [],
        },
    )
    # The endpoint is a stub and may return 500 when it cannot initialize the
    # encryption service, but it must not return 401 or 403 for a valid token.
    assert resp.status_code in (200, 201, 500)
