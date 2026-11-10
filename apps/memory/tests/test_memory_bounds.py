"""Bounds and idempotency tests for the memory service (#1426, #1427)."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from memory_app import api as api_module
from memory_app.config import settings
from memory_app.main import app


@pytest.mark.unit
def test_store_rejects_oversize_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blob over MEMORY_MAX_BLOB_BYTES is refused with 413, not stored."""
    monkeypatch.setattr(settings, "memory_max_blob_bytes", 8)
    client = TestClient(app)
    payload = {
        "owner": "bounds-user",
        "data": base64.b64encode(b"this is way more than eight bytes").decode("ascii"),
        "tags": {},
    }
    resp = client.post("/v1/store", json=payload)
    assert resp.status_code == 413


@pytest.mark.unit
def test_store_rejects_oversize_encoded_body_before_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    """The route refuses on encoded length so the payload is never decoded."""
    monkeypatch.setattr(settings, "memory_max_blob_bytes", 8)
    client = TestClient(app)
    # ~1.5x the cap in base64 characters; decode would succeed but must not run.
    payload = {"owner": "bounds-user", "data": "A" * 32, "tags": {}}
    resp = client.post("/v1/store", json=payload)
    assert resp.status_code == 413


@pytest.mark.unit
def test_store_full_evicts_lru_instead_of_507(monkeypatch: pytest.MonkeyPatch) -> None:
    """At the blob count cap the store evicts the LRU entry, not StoreFullError (#1682)."""
    client = TestClient(app)
    monkeypatch.setattr(settings, "memory_max_blobs", len(api_module.store._store) + 1)
    first = client.post(
        "/v1/store",
        json={"owner": "cap-user", "data": base64.b64encode(b"cap-one").decode("ascii"), "tags": {}},
    )
    assert first.status_code == 201
    cid_first = first.json()["content_address"]
    # Make cap-one deterministically the LRU victim regardless of what
    # earlier tests left in the shared store.
    from datetime import UTC, datetime

    api_module.store._store[cid_first]["last_accessed"] = datetime(2000, 1, 1, tzinfo=UTC)
    second = client.post(
        "/v1/store",
        json={"owner": "cap-user", "data": base64.b64encode(b"cap-two").decode("ascii"), "tags": {}},
    )
    assert second.status_code == 201
    # The cap held: the oldest (LRU) entry was evicted to make room.
    assert len(api_module.store._store) == settings.memory_max_blobs
    gone = client.get(f"/v1/retrieve/{cid_first}", params={"owner": "cap-user"})
    assert gone.status_code == 404


@pytest.mark.unit
def test_store_full_only_when_nothing_can_be_evicted(monkeypatch: pytest.MonkeyPatch) -> None:
    """StoreFullError survives only for a degenerate max_blobs <= 0 config."""
    client = TestClient(app)
    monkeypatch.setattr(settings, "memory_max_blobs", 0)
    resp = client.post(
        "/v1/store",
        json={"owner": "cap-user", "data": base64.b64encode(b"cap-zero").decode("ascii"), "tags": {}},
    )
    assert resp.status_code == 507


@pytest.mark.unit
def test_restore_existing_address_is_idempotent() -> None:
    """Re-storing identical bytes keeps the first committed owner/tags (#1427)."""
    client = TestClient(app)
    data = base64.b64encode(b"idempotent blob").decode("ascii")
    first = client.post("/v1/store", json={"owner": "owner-a", "data": data, "tags": {"n": 1}})
    assert first.status_code == 201
    second = client.post("/v1/store", json={"owner": "owner-b", "data": data, "tags": {"n": 2}})
    assert second.status_code == 201
    assert second.json()["owner"] == "owner-a"
    assert second.json()["tags"] == {"n": 1}
    retrieved = client.get(f"/v1/retrieve/{first.json()['content_address']}", params={"owner": "owner-a"})
    assert retrieved.json()["owner"] == "owner-a"
