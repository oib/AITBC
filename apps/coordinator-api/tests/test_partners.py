"""Tests for the DB-backed partner registry router."""

from __future__ import annotations

import hashlib

from sqlmodel import Session, select

from coordinator_api.contexts.enterprise_integration.domain.partner import Partner, PartnerWebhook

REGISTER_BODY = {
    "name": "Test Explorer",
    "description": "An integration test partner",
    "website": "https://example.com",
    "contact": "ops@example.com",
    "integration_type": "explorer",
}


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
