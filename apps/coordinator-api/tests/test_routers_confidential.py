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
            "sender_id": "client1",
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
            "sender_id": "client1",
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
            "sender_id": "client1",
            "recipient_id": "recipient-1",
            "amount_commitment": "0xdeadbeef",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["payment_id"] == "pay-123"
    assert data["sender_id"] == "client1"
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
    # #2174: no confidential-transaction store exists — the endpoint fails
    # loud with 501 instead of fabricating an orphaned transaction.
    assert resp.status_code == 501


@pytest.mark.unit
def test_confidential_transaction_get_is_honest_501(client, client_token):
    """#2174: GET /transactions/{id} reports the missing store, not a fake 404."""
    resp = client.get(
        "/v1/confidential/transactions/ctx-1",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp.status_code == 501


@pytest.mark.unit
def test_confidential_audit_is_honest_501(client, client_token):
    """#2174: POST /transactions/{id}/audit fails loud — no store to audit."""
    resp = client.post(
        "/v1/confidential/transactions/ctx-1/audit",
        headers={"Authorization": f"Bearer {client_token}"},
        params={"authorization": "audit-key", "purpose": "audit"},
    )
    assert resp.status_code == 501


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
    body = {"participant_id": "client1", "public_key": "AAAA", "algorithm": "X25519"}
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
        json={"participant_id": "client1", "public_key": "AAAA", "algorithm": "X25519"},
    )
    resp = client.post("/v1/confidential/keys/rotate", headers=headers, params={"participant_id": "client1"})
    assert resp.status_code == 501


# --- #1877: requester identity bound to the JWT principal ---


@pytest.fixture
def admin_token() -> str:
    return create_access_token("admin1", "admin")


def _access_body(requester: str) -> dict:
    return {
        "transaction_id": "ctx-1",
        "requester": requester,
        "purpose": "audit",
    }


@pytest.mark.unit
def test_access_requires_auth(client):
    """POST /transactions/{id}/access rejects unauthenticated callers."""
    resp = client.post("/v1/confidential/transactions/ctx-1/access", json=_access_body("client1"))
    assert resp.status_code in (401, 403)


@pytest.mark.unit
def test_access_rejects_foreign_requester(client, client_token):
    """#1877: a valid token cannot assert another participant as requester."""
    resp = client.post(
        "/v1/confidential/transactions/ctx-1/access",
        headers={"Authorization": f"Bearer {client_token}"},
        json=_access_body("victim-999"),
    )
    assert resp.status_code == 403
    assert "requester must match" in resp.text


@pytest.mark.unit
def test_access_allows_self_requester(client, client_token):
    """requester == token sub passes the binding, then hits the honest 501
    (#2174: no store exists to serve decrypted data)."""
    resp = client.post(
        "/v1/confidential/transactions/ctx-1/access",
        headers={"Authorization": f"Bearer {client_token}"},
        json=_access_body("client1"),
    )
    assert resp.status_code == 501
    assert "requester must match" not in resp.text


@pytest.mark.unit
def test_access_admin_may_assert_requester(client, admin_token):
    """Admin role keeps operator override for support/audit flows."""
    resp = client.post(
        "/v1/confidential/transactions/ctx-1/access",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_access_body("any-participant"),
    )
    assert resp.status_code == 501
    assert "requester must match" not in resp.text


@pytest.mark.unit
def test_confidential_transactions_get_requires_auth(client):
    """GET /transactions/{id} rejects unauthenticated callers."""
    resp = client.get("/v1/confidential/transactions/ctx-1")
    assert resp.status_code in (401, 403)


@pytest.mark.unit
def test_confidential_audit_requires_auth(client):
    """POST /transactions/{id}/audit rejects unauthenticated callers."""
    resp = client.post(
        "/v1/confidential/transactions/ctx-1/audit",
        params={"authorization": "audit-key", "purpose": "audit"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.unit
def test_access_logs_requires_admin(client):
    """#1897: GET /access/logs is audit data — admin scope only."""
    resp = client.get("/v1/confidential/access/logs")
    assert resp.status_code in (401, 403)


@pytest.mark.unit
def test_access_logs_rejects_client(client, client_token):
    resp = client.get(
        "/v1/confidential/access/logs",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.unit
def test_access_logs_allows_admin(client, admin_token):
    """#2174: admin passes auth, then the endpoint reports the missing
    access-log store as 501 instead of an empty page."""
    resp = client.get(
        "/v1/confidential/access/logs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 501


@pytest.mark.unit
def test_confidential_status_requires_auth(client):
    """#1897: GET /status sits under the auth matrix floor."""
    resp = client.get("/v1/confidential/status")
    assert resp.status_code in (401, 403)


@pytest.mark.unit
def test_confidential_status_allows_client(client, client_token):
    """#2174: status stays 200 but reports only real capabilities — no
    fabricated enabled=True / transactions_count."""
    resp = client.get(
        "/v1/confidential/status",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert "transactions_count" not in data
    assert data["audit_enabled"] is False


# --- #1932 F1: participant_id path traversal ---


@pytest.mark.unit
def test_keys_register_rejects_traversal_admin(client, admin_token, monkeypatch, tmp_path):
    """Admin JWTs bypass the participant==sub check, so the charset gate in
    _require_participant must reject traversal payloads for admins too."""
    from coordinator_api.config import settings
    from coordinator_api.contexts.confidential.routers import confidential as conf_module

    monkeypatch.setattr(settings, "key_storage_dir", str(tmp_path))
    conf_module.key_manager = None

    resp = client.post(
        "/v1/confidential/keys/register",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"participant_id": "../escape", "public_key": "AAAA", "algorithm": "X25519"},
    )
    assert resp.status_code == 400
    assert "Invalid participant_id" in resp.text
    # Nothing written outside (or inside) the key storage dir.
    assert not (tmp_path.parent / "escape.json").exists()
    assert not (tmp_path.parent / "escape.priv").exists()
    # No participant key material was written into the storage dir.
    assert not list(tmp_path.glob("*.json"))
    assert not list(tmp_path.glob("*.priv"))


@pytest.mark.unit
def test_keys_register_rejects_traversal_client(client, client_token, monkeypatch, tmp_path):
    """Client callers get the same charset rejection before the sub-match."""
    from coordinator_api.config import settings
    from coordinator_api.contexts.confidential.routers import confidential as conf_module

    monkeypatch.setattr(settings, "key_storage_dir", str(tmp_path))
    conf_module.key_manager = None

    resp = client.post(
        "/v1/confidential/keys/register",
        headers={"Authorization": f"Bearer {client_token}"},
        json={"participant_id": "a/b", "public_key": "AAAA", "algorithm": "X25519"},
    )
    assert resp.status_code == 400
    assert not list(tmp_path.glob("*.json"))
    assert not list(tmp_path.glob("*.priv"))


@pytest.mark.unit
def test_keys_rotate_rejects_traversal_admin(client, admin_token, monkeypatch, tmp_path):
    from coordinator_api.config import settings
    from coordinator_api.contexts.confidential.routers import confidential as conf_module

    monkeypatch.setattr(settings, "key_storage_dir", str(tmp_path))
    conf_module.key_manager = None

    resp = client.post(
        "/v1/confidential/keys/rotate",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"participant_id": "../../etc/cron.d/x"},
    )
    assert resp.status_code == 400
    assert not list(tmp_path.glob("*.json"))
    assert not list(tmp_path.glob("*.priv"))
