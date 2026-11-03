"""Tests for the ollama shop gate (OLLAMA-PROXY-GATE-1, #841)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

import main as gate  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(gate.app, raise_server_exceptions=False) as c:
        yield c


def _backend_response(status: int = 200, body: bytes = b'{"response":"ok"}') -> httpx.Response:
    return httpx.Response(status, content=body, headers={"content-type": "application/json"})


def test_gated_route_rejects_anonymous(client):
    assert client.post("/api/generate", json={}).status_code in (401, 403)
    assert client.post("/api/chat", json={}).status_code in (401, 403)
    assert client.post("/api/embed", json={}).status_code in (401, 403)


def test_wrong_job_token_is_403(client):
    with patch("aitbc.shop_gate._verify", return_value={"job_id": "job-A"}):
        resp = client.post(
            "/api/generate",
            json={},
            headers={"X-Access-Key": "k", "X-Access-Secret": "s", "X-Job-Id": "job-B"},
        )
    assert resp.status_code == 403


def test_valid_token_reaches_backend(client):
    gate.app.dependency_overrides[gate.require_job_access] = lambda: {"job_id": "job-A"}
    try:
        mock_send = AsyncMock(return_value=_backend_response())
        with patch.object(gate._client, "send", mock_send):
            resp = client.post(
                "/api/generate",
                json={"model": "m", "prompt": "p"},
                headers={"X-Access-Key": "k", "X-Access-Secret": "s", "X-Job-Id": "job-A"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"response": "ok"}
        assert mock_send.call_args.args[0].url.path == "/api/generate"
    finally:
        gate.app.dependency_overrides.pop(gate.require_job_access, None)


def test_public_routes_pass_through(client):
    mock_get = AsyncMock(return_value=_backend_response(body=b'{"models":[]}'))
    with patch.object(gate._client, "get", mock_get):
        assert client.get("/api/tags").status_code == 200
        assert client.get("/api/version").status_code == 200


def test_model_management_routes_are_not_proxied(client):
    # A paid token must not buy model management: these paths don't exist here.
    for path in ("/api/pull", "/api/create", "/api/delete", "/api/copy", "/api/push", "/api/blobs/sha256:x"):
        assert client.post(path, json={}).status_code in (401, 404, 405)
