"""Tests for the DB-backed partner registry router.

The router is deliberately not mounted on the production app (see main.py) —
nothing delivers webhooks yet, so open registration would be dead attack
surface. These tests mount it on a minimal app to keep full coverage.
"""

from __future__ import annotations

import hashlib
from collections.abc import Generator

import pytest
from sqlmodel import Session, select

from coordinator_api.contexts.enterprise_integration.domain.partner import Partner, PartnerWebhook
from coordinator_api.contexts.enterprise_integration.routers.partners import router as partners_router
from coordinator_api.storage import get_session

REGISTER_BODY = {
    "name": "Test Explorer",
    "description": "An integration test partner",
    "website": "https://example.com",
    "contact": "ops@example.com",
    "integration_type": "explorer",
}


@pytest.fixture
def client(db_session):
    """TestClient over a minimal app mounting only the partners router."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    test_app = FastAPI()
    test_app.include_router(partners_router, prefix="/v1")

    def override_get_session() -> Generator[Session]:
        yield db_session

    test_app.dependency_overrides[get_session] = override_get_session
    yield TestClient(test_app)


def _register(client) -> dict:
    resp = client.post("/v1/partners/register", json=REGISTER_BODY)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_register_persists_hashes_not_plaintext(client, db_session: Session) -> None:
    data = _register(client)

    row = db_session.get(Partner, data["partner_id"])
    assert row is not None
    assert row.api_key_hash == hashlib.sha256(data["api_key"].encode()).hexdigest()
    assert row.api_secret_hash == hashlib.sha256(data["api_secret"].encode()).hexdigest()
    # Plaintext credentials must not be recoverable from the stored row
    assert data["api_key"] not in row.api_key_hash
    assert data["api_secret"] not in row.api_secret_hash


def test_credentials_visible_to_a_fresh_session(client, db_engine) -> None:
    """A second session on the same engine sees the registration (restart/worker safety)."""
    data = _register(client)

    with Session(db_engine) as other:
        row = other.get(Partner, data["partner_id"])
        assert row is not None
        assert row.name == REGISTER_BODY["name"]


def test_get_partner_requires_valid_api_key(client) -> None:
    data = _register(client)

    ok = client.get(f"/v1/partners/{data['partner_id']}", params={"api_key": data["api_key"]})
    assert ok.status_code == 200
    assert ok.json()["partner_id"] == data["partner_id"]

    bad = client.get(f"/v1/partners/{data['partner_id']}", params={"api_key": "aitbc_wrong"})
    assert bad.status_code == 401


def test_webhook_lifecycle(client) -> None:
    data = _register(client)
    key = data["api_key"]

    created = client.post(
        "/v1/partners/webhooks",
        params={"api_key": key},
        json={"url": "https://example.com/hook", "events": ["block.created"]},
    )
    assert created.status_code == 200, created.text
    webhook_id = created.json()["webhook_id"]

    listed = client.get("/v1/partners/webhooks", params={"api_key": key})
    assert listed.status_code == 200
    assert [w["webhook_id"] for w in listed.json()] == [webhook_id]

    deleted = client.delete(f"/v1/partners/webhooks/{webhook_id}", params={"api_key": key})
    assert deleted.status_code == 200

    listed = client.get("/v1/partners/webhooks", params={"api_key": key})
    assert listed.json() == []


def test_webhook_requires_valid_api_key(client) -> None:
    resp = client.post(
        "/v1/partners/webhooks",
        params={"api_key": "aitbc_wrong"},
        json={"url": "https://example.com/hook", "events": ["block.created"]},
    )
    assert resp.status_code == 401


def test_webhook_rejects_unknown_event(client) -> None:
    data = _register(client)
    resp = client.post(
        "/v1/partners/webhooks",
        params={"api_key": data["api_key"]},
        json={"url": "https://example.com/hook", "events": ["bogus.event"]},
    )
    assert resp.status_code == 400


def test_delete_webhook_scoped_to_owning_partner(client) -> None:
    owner = _register(client)
    other = _register(client)

    created = client.post(
        "/v1/partners/webhooks",
        params={"api_key": owner["api_key"]},
        json={"url": "https://example.com/hook", "events": ["block.created"]},
    )
    webhook_id = created.json()["webhook_id"]

    resp = client.delete(f"/v1/partners/webhooks/{webhook_id}", params={"api_key": other["api_key"]})
    assert resp.status_code == 404


def test_usage_analytics_requires_valid_key(client) -> None:
    data = _register(client)

    ok = client.get("/v1/partners/analytics/usage", params={"api_key": data["api_key"]})
    assert ok.status_code == 200
    assert ok.json()["period"] == "24h"

    bad = client.get("/v1/partners/analytics/usage", params={"api_key": "aitbc_wrong"})
    assert bad.status_code == 401


# --- API_KEY_HASH_SECRET reader / rotation overlap (#852) ---------------------
# These exercise the hash helpers directly: /partners/register is rate-limited
# to 10/min and the suite's HTTP registrations already sit near the cap.


def _hmac(secret: str, value: str) -> str:
    import hmac as hmac_mod

    return hmac_mod.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def _partner_row(db_session: Session, partner_id: str, api_key_hash: str) -> Partner:
    row = Partner(
        id=partner_id,
        name="Hash Test",
        description="partner row for hash tests",
        website="https://example.com",
        contact="hash@example.com",
        integration_type="other",
        api_key_hash=api_key_hash,
        api_secret_hash="x",
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_hmac_secret_used_when_set(monkeypatch) -> None:
    """ROTATE-SECRET-SCRIPTS-BROKEN-1 (#852): API_KEY_HASH_SECRET is the reader
    the rotation script rotates — digests are HMAC-derived when it is set."""
    from coordinator_api.contexts.enterprise_integration.routers.partners import _hash

    monkeypatch.delenv("API_KEY_HASH_SECRET_NEW", raising=False)
    monkeypatch.delenv("API_KEY_HASH_SECRET_PREVIOUS", raising=False)
    monkeypatch.setenv("API_KEY_HASH_SECRET", "hash-secret-one-0123456789abcdef0123456789")
    api_key = "aitbc_key123"

    assert _hash(api_key) == _hmac("hash-secret-one-0123456789abcdef0123456789", api_key)


def test_rotation_overlap_accepts_new_and_previous(db_session: Session, monkeypatch) -> None:
    """A key issued under the retired secret keeps working after the flip, and
    digests under API_KEY_HASH_SECRET_NEW verify during the overlap window."""
    from coordinator_api.contexts.enterprise_integration.routers.partners import (
        _hash_candidates,
        find_partner_by_api_key,
        verify_partner_api_key,
    )

    api_key = "aitbc_rotated"
    _partner_row(db_session, "p-old", _hmac("old-hash-secret-0123456789abcdef0123456", api_key))
    _partner_row(db_session, "p-new", _hmac("new-hash-secret-0123456789abcdef0123456", api_key + "2"))

    # Post-flip env: new primary, retired secret in *_PREVIOUS.
    monkeypatch.setenv("API_KEY_HASH_SECRET", "new-hash-secret-0123456789abcdef0123456")
    monkeypatch.setenv("API_KEY_HASH_SECRET_PREVIOUS", "old-hash-secret-0123456789abcdef0123456")
    monkeypatch.delenv("API_KEY_HASH_SECRET_NEW", raising=False)

    assert verify_partner_api_key(db_session, "p-old", api_key) is not None
    assert verify_partner_api_key(db_session, "p-new", api_key + "2") is not None
    assert find_partner_by_api_key(db_session, api_key).id == "p-old"
    # Wrong key still fails under every candidate.
    assert verify_partner_api_key(db_session, "p-old", "aitbc_wrong") is None

    # During the window, *_NEW digests are also acceptable candidates.
    monkeypatch.setenv("API_KEY_HASH_SECRET_NEW", "inflight-secret-0123456789abcdef0123456")
    assert _hmac("inflight-secret-0123456789abcdef0123456", api_key) in _hash_candidates(api_key)


def test_legacy_sha256_rows_still_verify(db_session: Session, monkeypatch) -> None:
    """Rows written before the secret was read (plain SHA-256) stay valid."""
    from coordinator_api.contexts.enterprise_integration.routers.partners import verify_partner_api_key

    api_key = "aitbc_legacy"
    _partner_row(db_session, "p-legacy", hashlib.sha256(api_key.encode()).hexdigest())
    monkeypatch.setenv("API_KEY_HASH_SECRET", "hash-secret-one-0123456789abcdef0123456789")
    assert verify_partner_api_key(db_session, "p-legacy", api_key) is not None


def test_webhook_row_persisted_with_foreign_key(client, db_session: Session) -> None:
    data = _register(client)
    client.post(
        "/v1/partners/webhooks",
        params={"api_key": data["api_key"]},
        json={"url": "https://example.com/hook", "events": ["block.created", "governance.vote_cast"]},
    )

    rows = db_session.exec(select(PartnerWebhook)).all()
    assert len(rows) == 1
    assert rows[0].partner_id == data["partner_id"]
    assert rows[0].events == ["block.created", "governance.vote_cast"]
