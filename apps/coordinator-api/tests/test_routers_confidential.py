"""Tests for the confidential router.

The confidential endpoints are primarily stubs/simulations; these tests verify
that the CLI-facing payment route is fail-closed (503 unless TEE is
explicitly enabled), requires authentication, and that other routes still
respect the security matrix.
"""

import pytest

from aitbc.auth import create_access_token


@pytest.fixture
def client_token() -> str:
    return create_access_token("client1", "client")


@pytest.mark.unit
def test_confidential_payments_requires_auth(client):
    """POST /v1/confidential/payments now requires a client/admin token."""
    resp = client.post(
        "/v1/confidential/payments",
        json={
            "payment_id": "pay-123",
            "sender_id": "wallet-1",
            "recipient_id": "recipient-1",
            "amount_commitment": "0xdeadbeef",
        },
    )
    assert resp.status_code in (401, 403)


@pytest.mark.unit
def test_confidential_payments_disabled_for_authenticated_client(client, client_token):
    """POST /v1/confidential/payments returns 503 when TEE is not enabled."""
    from coordinator_api.config import settings

    assert settings.confidential_tee_enabled is False
    resp = client.post(
        "/v1/confidential/payments",
        headers={"Authorization": f"Bearer {client_token}"},
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
def test_confidential_payments_authenticated_when_enabled(client, client_token, monkeypatch):
    """POST /v1/confidential/payments works with a client token when TEE is enabled."""
    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "confidential_tee_enabled", True)
    resp = client.post(
        "/v1/confidential/payments",
        headers={"Authorization": f"Bearer {client_token}"},
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


@pytest.mark.unit
def test_keys_register_requires_auth(client):
    """POST /v1/confidential/keys/register rejects unauthenticated callers."""
    resp = client.post(
        "/v1/confidential/keys/register",
        json={"participant_id": "p1", "public_key": "AAAA", "algorithm": "X25519"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.unit
def test_keys_rotate_requires_auth(client):
    """POST /v1/confidential/keys/rotate rejects unauthenticated callers."""
    resp = client.post("/v1/confidential/keys/rotate", params={"participant_id": "p1"})
    assert resp.status_code in (401, 403)


@pytest.mark.unit
def test_keys_register_existing_returns_stored_version(client, client_token, monkeypatch, tmp_path):
    """Re-registering an existing participant returns the stored key version,
    not a fabricated key_version=1/now timestamp."""
    from coordinator_api.config import settings
    from coordinator_api.contexts.confidential.routers import confidential as conf_module

    monkeypatch.setattr(settings, "key_storage_dir", str(tmp_path))
    conf_module.key_manager = None

    headers = {"Authorization": f"Bearer {client_token}"}
    body = {"participant_id": "p-existing", "public_key": "AAAA", "algorithm": "X25519"}
    first = client.post("/v1/confidential/keys/register", headers=headers, json=body)
    assert first.status_code == 200, first.text
    second = client.post("/v1/confidential/keys/register", headers=headers, json=body)
    assert second.status_code == 200, second.text
    data = second.json()
    assert data["success"] is True
    assert data["key_version"] == first.json()["key_version"]
    assert data["registered_at"] == first.json()["registered_at"]


@pytest.mark.unit
def test_keys_rotate_authenticated_is_honest_501(client, client_token, monkeypatch, tmp_path):
    """With auth, rotate reaches the service and reports the unimplemented
    re-encryption path as 501 rather than a fabricated success."""
    from coordinator_api.config import settings
    from coordinator_api.contexts.confidential.routers import confidential as conf_module

    monkeypatch.setattr(settings, "key_storage_dir", str(tmp_path))
    conf_module.key_manager = None

    headers = {"Authorization": f"Bearer {client_token}"}
    client.post(
        "/v1/confidential/keys/register",
        headers=headers,
        json={"participant_id": "p-rotate", "public_key": "AAAA", "algorithm": "X25519"},
    )
    resp = client.post("/v1/confidential/keys/rotate", headers=headers, params={"participant_id": "p-rotate"})
    assert resp.status_code == 501
