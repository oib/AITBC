"""#3029 AUTHZ-MEMORY-OPEN-MODE-FAILOPEN-1 pins.

With neither MEMORY_API_KEY nor MEMORY_API_KEY_OWNERS configured, the
memory service used to run "open mode" silently — any caller could
store/read/delete under ANY owner namespace. Open mode now requires the
explicit ``memory_open_mode`` opt-in; unconfigured-without-opt-in fails
closed with 503 on every authenticated route. /v1/health stays up so
probes and orchestration still work.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from memory_app.config import settings
from memory_app.main import app


def _no_keys(monkeypatch) -> None:
    monkeypatch.setattr(settings, "memory_api_key", None)
    monkeypatch.setattr(settings, "memory_api_key_owners", None)


def _store(client: TestClient, owner: str = "pin-owner") -> dict:
    return client.post(
        "/v1/store",
        json={
            "owner": owner,
            "data": base64.b64encode(b"pin blob").decode("ascii"),
            "tags": {},
        },
    )


@pytest.mark.unit
def test_unconfigured_without_optin_refuses_store(monkeypatch) -> None:
    """No keys + no MEMORY_OPEN_MODE → /store refuses closed."""
    _no_keys(monkeypatch)
    monkeypatch.setattr(settings, "memory_open_mode", False)
    client = TestClient(app)

    resp = _store(client)
    assert resp.status_code == 503
    assert "MEMORY_OPEN_MODE" in resp.json()["detail"]


@pytest.mark.unit
def test_unconfigured_without_optin_refuses_retrieve_and_delete(monkeypatch) -> None:
    """The gate covers every authenticated route, not just /store."""
    _no_keys(monkeypatch)
    monkeypatch.setattr(settings, "memory_open_mode", False)
    client = TestClient(app)

    cid = "cid:deadbeef"
    assert client.get(f"/v1/retrieve/{cid}", params={"owner": " anyone "}).status_code == 503
    assert client.delete(f"/v1/blobs/{cid}", params={"owner": "anyone"}).status_code == 503


@pytest.mark.unit
def test_health_still_up_when_locked(monkeypatch) -> None:
    """/v1/health carries no auth dependency — probes keep working."""
    _no_keys(monkeypatch)
    monkeypatch.setattr(settings, "memory_open_mode", False)
    client = TestClient(app)

    assert client.get("/v1/health").status_code == 200


@pytest.mark.unit
def test_explicit_open_mode_keeps_self_asserted_owner(monkeypatch) -> None:
    """Opted-in open mode: single-tenant self-asserted owner still works."""
    _no_keys(monkeypatch)
    monkeypatch.setattr(settings, "memory_open_mode", True)
    client = TestClient(app)

    body = _store(client, "open-owner").json()
    assert body["owner"] == "open-owner"

    got = client.get(f"/v1/retrieve/{body['content_address']}", params={"owner": "open-owner"})
    assert got.status_code == 200


@pytest.mark.unit
def test_keyed_auth_unaffected_by_open_mode_flag(monkeypatch) -> None:
    """Control: with MEMORY_API_KEY set, wrong keys still 401 and the right
    key binds the shared tenant regardless of the open-mode flag."""
    monkeypatch.setattr(settings, "memory_api_key", "pin-secret")
    monkeypatch.setattr(settings, "memory_api_key_owners", None)
    monkeypatch.setattr(settings, "memory_open_mode", False)
    client = TestClient(app)

    assert _store(client).status_code == 401

    resp = client.post(
        "/v1/store",
        json={
            "owner": "ignored-when-authed",
            "data": base64.b64encode(b"k").decode("ascii"),
            "tags": {},
        },
        headers={"X-API-Key": "pin-secret"},
    )
    assert resp.status_code == 201
    assert resp.json()["owner"] == "shared"
