"""Smoke test for the decentralized memory service."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from memory_app.main import app


@pytest.mark.unit
def test_memory_store_and_retrieve() -> None:
    """Round-trip a blob through the memory service."""
    client = TestClient(app)

    assert client.get("/v1/health").status_code == 200

    payload = {
        "owner": "test-user",
        "data": base64.b64encode(b"hello memory").decode("ascii"),
        "tags": {"env": "test"},
    }
    resp = client.post("/v1/store", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["owner"] == "test-user"
    assert body["size"] == len(b"hello memory")
    assert body["content_address"].startswith("cid:")

    retrieved = client.get(f"/v1/retrieve/{body['content_address']}")
    assert retrieved.status_code == 200
    assert base64.b64decode(retrieved.json()["data"]) == b"hello memory"
