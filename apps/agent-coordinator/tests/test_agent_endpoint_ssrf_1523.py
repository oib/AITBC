"""SSRF-AUDIT-1 (#1523): agent-registered http endpoints pass the fleet
outbound-URL guard — loopback/link-local/metadata refused, private fleet
LAN allowed, operator allowlist escapes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_app.routers import agents as agents_router
from agent_app.routing.agent_discovery import AgentRegistry


@pytest.fixture
def registry():
    return AgentRegistry()


@pytest.fixture
def fake_storage():
    storage = MagicMock()
    storage.store_message = AsyncMock(return_value=True)
    return storage


@pytest.fixture
def client(monkeypatch, registry, fake_storage):
    app = FastAPI()
    app.include_router(agents_router.router, prefix="/v1")
    fake_state = MagicMock(agent_registry=registry, message_storage=fake_storage)
    monkeypatch.setattr(agents_router, "state", fake_state)
    return TestClient(app)


def _register(client: TestClient, agent_id: str, endpoint: str):
    return client.post(
        "/v1/agents/register",
        json={"agent_id": agent_id, "agent_type": "worker", "endpoints": {"http": endpoint}},
    )


def test_loopback_endpoint_rejected_without_allowlist(client, monkeypatch):
    monkeypatch.delenv("AITBC_OUTBOUND_URL_ALLOWED_TARGETS", raising=False)
    resp = _register(client, "ssrf-loop", "http://127.0.0.1:9")
    assert resp.status_code == 422, resp.text


def test_metadata_endpoint_rejected(client, monkeypatch):
    monkeypatch.delenv("AITBC_OUTBOUND_URL_ALLOWED_TARGETS", raising=False)
    resp = _register(client, "ssrf-meta", "http://169.254.169.254:80")
    assert resp.status_code == 422, resp.text


def test_private_fleet_endpoint_accepted(client, monkeypatch):
    monkeypatch.delenv("AITBC_OUTBOUND_URL_ALLOWED_TARGETS", raising=False)
    resp = _register(client, "ssrf-lan", "http://10.9.9.9:8107")
    assert resp.status_code == 200, resp.text


def test_query_in_endpoint_rejected(client, monkeypatch):
    """A stored '?x=1' would rewrite the concatenated /tasks/execute path."""
    monkeypatch.delenv("AITBC_OUTBOUND_URL_ALLOWED_TARGETS", raising=False)
    resp = _register(client, "ssrf-query", "http://10.9.9.9:8107?next=/admin")
    assert resp.status_code == 422, resp.text


def test_allowlist_escape_admits_loopback(client, monkeypatch):
    monkeypatch.setenv("AITBC_OUTBOUND_URL_ALLOWED_TARGETS", "127.0.0.1")
    resp = _register(client, "ssrf-allow", "http://127.0.0.1:9")
    assert resp.status_code == 200, resp.text
