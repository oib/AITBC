"""AUDIT-EDGE-MEMORY-OWNER-AUTHZ (#2801): the blob owner was a self-asserted
string — any caller who learned a cid could read/delete it by naming the
storing owner. With key auth configured the owner is bound to the key's
identity and the caller-supplied owner is ignored.
"""

import base64

import pytest
from fastapi.testclient import TestClient

from memory_app.config import settings
from memory_app.main import app


def _store(client: TestClient, owner: str, payload: bytes, headers: dict | None = None) -> dict:
    resp = client.post(
        "/v1/store",
        json={"owner": owner, "data": base64.b64encode(payload).decode("ascii"), "tags": {}},
        headers=headers or {},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def keyed(monkeypatch):
    """Two tenant keys plus the shared key, all bound to fixed owners."""
    monkeypatch.setattr(settings, "memory_api_key", "shared-secret")
    monkeypatch.setattr(
        settings,
        "memory_api_key_owners",
        '{"tenant-a-key": "tenant-a", "tenant-b-key": "tenant-b"}',
    )
    return {
        "shared": {"X-API-Key": "shared-secret"},
        "a": {"X-API-Key": "tenant-a-key"},
        "b": {"X-API-Key": "tenant-b-key"},
    }


def test_tenant_key_binds_owner_and_blocks_assertion(keyed) -> None:
    client = TestClient(app)
    body = _store(client, "ignored-name", b"tenant blob", keyed["a"])
    cid = body["content_address"]
    # Stored under the key's owner, not the asserted name.
    assert body["owner"] == "tenant-a"
    # Tenant B cannot read it even by asserting tenant-a's name.
    resp = client.get(f"/v1/retrieve/{cid}", params={"owner": "tenant-a"}, headers=keyed["b"])
    assert resp.status_code == 403
    # Tenant A reads it regardless of the owner param value.
    resp = client.get(f"/v1/retrieve/{cid}", params={"owner": "whatever"}, headers=keyed["a"])
    assert resp.status_code == 200
    # Tenant B cannot delete it.
    assert client.delete(f"/v1/blobs/{cid}", params={"owner": "tenant-a"}, headers=keyed["b"]).status_code == 403


def test_shared_key_is_single_tenant(keyed) -> None:
    client = TestClient(app)
    body = _store(client, "any-name", b"shared blob", keyed["shared"])
    assert body["owner"] == "shared"
    # Even asserting the stored owner string does not match — identity wins.
    resp = client.get(f"/v1/retrieve/{body['content_address']}", params={"owner": "shared"}, headers=keyed["shared"])
    assert resp.status_code == 200


def test_wrong_key_rejected(keyed) -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/store",
        json={"owner": "x", "data": base64.b64encode(b"y").decode(), "tags": {}},
        headers={"X-API-Key": "wrong"},
    )
    assert resp.status_code == 401


def test_open_mode_keeps_self_asserted_owner(monkeypatch) -> None:
    """No keys configured: previous open behavior is preserved."""
    monkeypatch.setattr(settings, "memory_api_key", None)
    monkeypatch.setattr(settings, "memory_api_key_owners", None)
    client = TestClient(app)
    body = _store(client, "open-owner", b"open blob")
    assert body["owner"] == "open-owner"
