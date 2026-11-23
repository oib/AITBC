"""#2712 — /v1/multi-modal-rl proxy pins.

Pre-fix the router imported ``..config`` (a package with no config module) and
silently fell back to ``http://localhost:8106`` — the exchange port — then
answered HTTP 200 with ``{"error": ...}`` dicts, and forwarded a caller-asserted
``client_id``. Pins: configured AI_SERVICE_URL upstream, real status codes,
caller-bound client_id.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import coordinator_api.contexts.multimodal.routers.multi_modal_rl as mmlrl
from aitbc.auth import create_access_token
from aitbc.exceptions import NetworkError
from coordinator_api.config import settings

BASE = "/v1/multi-modal-rl"


def _headers(sub: str = "client-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


class _FakeAIClient:
    """Captures the upstream calls the proxy makes."""

    calls: list[tuple[str, str, dict | None]] = []
    error: Exception | None = None

    def __init__(self, timeout: float) -> None:
        pass

    def _record(self, method: str, url: str, kwargs: dict | None) -> dict:
        type(self).calls.append((method, url, kwargs))
        if type(self).error is not None:
            raise type(self).error
        return {"ok": True, "upstream": url}

    def post(self, url: str, json: dict | None = None, data: dict | None = None) -> dict:
        return self._record("POST", url, {"json": json, "data": data})

    def get(self, url: str, params: dict | None = None) -> dict:
        return self._record("GET", url, {"params": params})


@pytest.fixture
def fake_ai(monkeypatch: pytest.MonkeyPatch) -> type[_FakeAIClient]:
    _FakeAIClient.calls = []
    _FakeAIClient.error = None
    monkeypatch.setattr(mmlrl, "AITBCHTTPClient", _FakeAIClient)
    monkeypatch.setattr(settings, "ai_service_url", "http://ai-engine.test:8005/")
    return _FakeAIClient


class TestUpstreamConfig:
    def test_uses_configured_ai_service_url(self, fake_ai: type[_FakeAIClient]) -> None:
        assert mmlrl.get_ai_service_url() == "http://ai-engine.test:8005"

    def test_submit_proxies_to_ai_service_not_exchange_port(self, client: TestClient, fake_ai: type[_FakeAIClient]) -> None:
        resp = client.post(
            f"{BASE}/jobs",
            json={"task_type": "caption", "task_data": {}},
            headers=_headers(),
        )
        assert resp.status_code == 200
        method, url, kwargs = fake_ai.calls[-1]
        assert method == "POST"
        assert url == "http://ai-engine.test:8005/jobs"
        assert "8106" not in url


class TestStatusCodes:
    def test_upstream_failure_is_502_not_200_error_dict(self, client: TestClient, fake_ai: type[_FakeAIClient]) -> None:
        fake_ai.error = NetworkError("connection refused")
        resp = client.get(f"{BASE}/jobs", headers=_headers())
        assert resp.status_code == 502
        assert "error" not in resp.json() or resp.json().get("detail")

    def test_local_error_is_500_not_200_error_dict(self, client: TestClient, fake_ai: type[_FakeAIClient]) -> None:
        fake_ai.error = RuntimeError("boom")
        resp = client.get(f"{BASE}/jobs", headers=_headers())
        assert resp.status_code == 500


class TestClientIdBinding:
    def test_non_admin_client_id_bound_to_token(self, client: TestClient, fake_ai: type[_FakeAIClient]) -> None:
        resp = client.post(
            f"{BASE}/jobs",
            json={"task_type": "t", "task_data": {}},
            params={"client_id": "victim-9"},
            headers=_headers("client-1"),
        )
        assert resp.status_code == 403
        assert fake_ai.calls == []

    def test_non_admin_own_id_and_default(self, client: TestClient, fake_ai: type[_FakeAIClient]) -> None:
        resp = client.get(f"{BASE}/jobs", headers=_headers("client-1"))
        assert resp.status_code == 200
        assert fake_ai.calls[-1][2]["params"]["client_id"] == "client-1"

        resp = client.get(f"{BASE}/jobs", params={"client_id": "client-1"}, headers=_headers("client-1"))
        assert resp.status_code == 200

    def test_admin_may_pass_other_client_id(self, client: TestClient, fake_ai: type[_FakeAIClient]) -> None:
        resp = client.get(f"{BASE}/jobs", params={"client_id": "victim-9"}, headers=_headers("root", "admin"))
        assert resp.status_code == 200
        assert fake_ai.calls[-1][2]["params"]["client_id"] == "victim-9"

    def test_requires_auth(self, client: TestClient, fake_ai: type[_FakeAIClient]) -> None:
        assert client.get(f"{BASE}/jobs").status_code in (401, 403)
