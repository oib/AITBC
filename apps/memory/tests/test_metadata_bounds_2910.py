"""AUDIT-EDGE pins: #2910 memory owner/tags metadata must be bounded and
counted toward the store's byte cap."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from memory_app import api as api_module
from memory_app.config import settings
from memory_app.main import app


@pytest.mark.unit
def test_oversize_tags_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_max_metadata_bytes", 128)
    client = TestClient(app)
    resp = client.post(
        "/v1/store",
        json={
            "owner": "meta-user",
            "data": base64.b64encode(b"x").decode("ascii"),
            "tags": {"blob": "y" * 4096},
        },
    )
    assert resp.status_code == 413


@pytest.mark.unit
def test_oversize_owner_rejected() -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/store",
        json={
            "owner": "o" * 300,
            "data": base64.b64encode(b"x").decode("ascii"),
            "tags": {},
        },
    )
    assert resp.status_code == 422  # pydantic max_length


@pytest.mark.unit
def test_metadata_counts_toward_total_bytes() -> None:
    """stored_bytes must exceed len(data) — owner+tags are accounted."""
    client = TestClient(app)
    data = b"tiny"
    resp = client.post(
        "/v1/store",
        json={
            "owner": "acct-user",
            "data": base64.b64encode(data).decode("ascii"),
            "tags": {"k": "v" * 100},
        },
    )
    assert resp.status_code == 201
    health = client.get("/v1/health").json()
    # The shared store holds other tests' blobs too; assert the delta
    # accounting by checking the record itself.
    cid = resp.json()["content_address"]
    record = api_module.store._store[cid]
    assert record["accounted_bytes"] > record["size"]
    assert health["stored_bytes"] >= record["accounted_bytes"]


@pytest.mark.unit
def test_metadata_counts_against_store_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tiny blob with metadata must hit the byte cap, not slip under —
    cap below data+meta is StoreFullError regardless of eviction."""
    client = TestClient(app)
    monkeypatch.setattr(settings, "memory_max_total_bytes", 100)
    resp = client.post(
        "/v1/store",
        json={
            "owner": "cap-meta-user",
            "data": base64.b64encode(b"z").decode("ascii"),
            "tags": {"pad": "p" * 500},
        },
    )
    # data(1)+owner(~13)+tags(~520) > 100-byte cap -> refused.
    assert resp.status_code == 507
