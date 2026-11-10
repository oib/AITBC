"""MEMORY-RESIDUAL-1 (#1682) tests: TTL eviction, LRU, ownership, delete, API key."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from memory_app import api as api_module
from memory_app.config import settings
from memory_app.main import app


def _store(client: TestClient, owner: str, payload: bytes, tags: dict | None = None) -> dict:
    resp = client.post(
        "/v1/store",
        json={"owner": owner, "data": base64.b64encode(payload).decode("ascii"), "tags": tags or {}},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.unit
def test_retrieve_requires_owner() -> None:
    """GET /retrieve without ?owner= is rejected (was unauthenticated)."""
    client = TestClient(app)
    body = _store(client, "res-owner-a", b"residual auth blob")
    resp = client.get(f"/v1/retrieve/{body['content_address']}")
    assert resp.status_code == 422


@pytest.mark.unit
def test_retrieve_rejects_non_owner() -> None:
    """A caller presenting a different owner gets 403, not the blob."""
    client = TestClient(app)
    body = _store(client, "res-owner-b", b"residual auth blob 2")
    resp = client.get(f"/v1/retrieve/{body['content_address']}", params={"owner": "res-intruder"})
    assert resp.status_code == 403
    ok = client.get(f"/v1/retrieve/{body['content_address']}", params={"owner": "res-owner-b"})
    assert ok.status_code == 200
    assert base64.b64decode(ok.json()["data"]) == b"residual auth blob 2"


@pytest.mark.unit
def test_idempotent_restore_keeps_both_owners() -> None:
    """A second tenant storing identical bytes can still retrieve it (#1682)."""
    client = TestClient(app)
    data = base64.b64encode(b"shared residual blob").decode("ascii")
    first = client.post("/v1/store", json={"owner": "res-owner-c", "data": data, "tags": {}})
    second = client.post("/v1/store", json={"owner": "res-owner-d", "data": data, "tags": {}})
    assert first.status_code == 201 and second.status_code == 201
    cid = first.json()["content_address"]
    assert second.json()["content_address"] == cid
    # Descriptor still names the first writer (content-addressed semantics)…
    assert second.json()["owner"] == "res-owner-c"
    # …but BOTH owners may retrieve: the second writer is not locked out.
    for owner in ("res-owner-c", "res-owner-d"):
        resp = client.get(f"/v1/retrieve/{cid}", params={"owner": owner})
        assert resp.status_code == 200, owner


@pytest.mark.unit
def test_delete_requires_owner_and_removes_blob() -> None:
    """DELETE /blobs/{cid} is owner-gated and actually removes the record."""
    client = TestClient(app)
    body = _store(client, "res-owner-e", b"residual delete blob")
    cid = body["content_address"]
    forbidden = client.delete(f"/v1/blobs/{cid}", params={"owner": "res-intruder"})
    assert forbidden.status_code == 403
    deleted = client.delete(f"/v1/blobs/{cid}", params={"owner": "res-owner-e"})
    assert deleted.status_code == 204
    gone = client.get(f"/v1/retrieve/{cid}", params={"owner": "res-owner-e"})
    assert gone.status_code == 404


@pytest.mark.unit
def test_ttl_expiry_makes_blob_vanish(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blob past MEMORY_BLOB_TTL_SECONDS reads as missing and is dropped."""
    client = TestClient(app)
    monkeypatch.setattr(settings, "memory_blob_ttl_seconds", 60)
    body = _store(client, "res-owner-f", b"residual ttl blob")
    cid = body["content_address"]
    # Age the record past its expiry without sleeping.
    api_module.store._store[cid]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    resp = client.get(f"/v1/retrieve/{cid}", params={"owner": "res-owner-f"})
    assert resp.status_code == 404
    assert cid not in api_module.store._store


@pytest.mark.unit
def test_expired_record_can_be_restored() -> None:
    """Re-storing content whose record expired writes a fresh record."""
    client = TestClient(app)
    data = base64.b64encode(b"residual restore blob").decode("ascii")
    first = _store(client, "res-owner-g", b"residual restore blob")
    cid = first["content_address"]
    api_module.store._store[cid]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    second = client.post("/v1/store", json={"owner": "res-owner-h", "data": data, "tags": {}})
    assert second.status_code == 201
    assert second.json()["owner"] == "res-owner-h"


@pytest.mark.unit
def test_api_key_gate_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """MEMORY_API_KEY set => X-API-Key required on store/retrieve/delete."""
    client = TestClient(app)
    monkeypatch.setattr(settings, "memory_api_key", "res-test-key")
    try:
        denied = client.post(
            "/v1/store",
            json={"owner": "res-owner-i", "data": base64.b64encode(b"keyed").decode("ascii"), "tags": {}},
        )
        assert denied.status_code == 401
        # Store with the key, then read it back without/with the key.
        resp = client.post(
            "/v1/store",
            json={"owner": "res-owner-i", "data": base64.b64encode(b"keyed").decode("ascii"), "tags": {}},
            headers={"X-API-Key": "res-test-key"},
        )
        assert resp.status_code == 201
        cid = resp.json()["content_address"]
        assert client.get(f"/v1/retrieve/{cid}", params={"owner": "res-owner-i"}).status_code == 401
        ok = client.get(f"/v1/retrieve/{cid}", params={"owner": "res-owner-i"}, headers={"X-API-Key": "res-test-key"})
        assert ok.status_code == 200
        assert client.delete(f"/v1/blobs/{cid}", params={"owner": "res-owner-i"}).status_code == 401
        assert (
            client.delete(
                f"/v1/blobs/{cid}", params={"owner": "res-owner-i"}, headers={"X-API-Key": "res-test-key"}
            ).status_code
            == 204
        )
    finally:
        monkeypatch.setattr(settings, "memory_api_key", None)
