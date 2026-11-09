"""Router tests for /v1/inference/* (#1289 round 9 batch 4).

Thin Ollama proxy via SharedHttpClient — faked at the module boundary
(node2 has a live service on :11434, so real-connect tests would be
nondeterministic). Contract: 503 on connect failure, 502 on upstream
HTTP error, SSE error event, per-prompt error capture in batch,
empty-list degradation on models.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

import coordinator_api.contexts.infrastructure.routers.inference as inf_mod
from aitbc.auth import create_access_token

BASE = "/v1/inference"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u', 'client')}"}


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None, lines: list[str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self._lines = lines or []
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://ollama/")
            raise httpx.HTTPStatusError("err", request=request, response=httpx.Response(self.status_code))

    def json(self):
        return self._payload

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStream:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *a):
        return False


class _FakeClient:
    post_response: _FakeResponse = _FakeResponse()
    get_response: _FakeResponse = _FakeResponse()
    post_error: Exception | None = None
    get_error: Exception | None = None
    stream_response: _FakeResponse = _FakeResponse()

    @classmethod
    async def post(cls, url, **kw):
        if cls.post_error:
            raise cls.post_error
        return cls.post_response

    @classmethod
    async def get(cls, url, **kw):
        if cls.get_error:
            raise cls.get_error
        return cls.get_response

    @classmethod
    def stream(cls, method, url, **kw):
        return _FakeStream(cls.stream_response)


@pytest.fixture
def fake_ollama(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    _FakeClient.post_response = _FakeResponse(200, {"response": "hello", "context": [1], "total_duration": 5})
    _FakeClient.get_response = _FakeResponse(200, {"models": []})
    _FakeClient.post_error = None
    _FakeClient.get_error = None
    _FakeClient.stream_response = _FakeResponse(
        lines=[json.dumps({"response": "tok"}), json.dumps({"done": True, "context": [1]})]
    )
    monkeypatch.setattr(inf_mod, "SharedHttpClient", _FakeClient)
    return _FakeClient


class TestInferenceUpstream:
    def test_matrix_any(self) -> None:
        from aitbc.auth.security_matrix import AuthLevel, get_auth_level

        assert get_auth_level("/v1/inference/generate") == AuthLevel.ANY

    def test_generate_success(self, client: TestClient, fake_ollama: type[_FakeClient]) -> None:
        resp = client.post(
            f"{BASE}/generate",
            json={"prompt": "hi", "system": "sys", "temperature": 0.5, "max_tokens": 10},
            headers=_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["response"] == "hello"
        assert body["model"] == "llama2"

    def test_generate_connect_error_503(self, client: TestClient, fake_ollama: type[_FakeClient]) -> None:
        fake_ollama.post_error = httpx.ConnectError("refused")
        resp = client.post(f"{BASE}/generate", json={"prompt": "hi"}, headers=_headers())
        assert resp.status_code == 503

    def test_generate_upstream_500_502(self, client: TestClient, fake_ollama: type[_FakeClient]) -> None:
        fake_ollama.post_response = _FakeResponse(500)
        resp = client.post(f"{BASE}/generate", json={"prompt": "hi"}, headers=_headers())
        assert resp.status_code == 502

    def test_generate_validation(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/generate", json={}, headers=_headers()).status_code == 422
        assert client.post(f"{BASE}/generate", json={"prompt": "x", "temperature": 5.0}, headers=_headers()).status_code == 422

    def test_generate_stream_sse_tokens(self, client: TestClient, fake_ollama: type[_FakeClient]) -> None:
        resp = client.post(f"{BASE}/generate/stream", json={"prompt": "hi"}, headers=_headers())
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert '"token": "tok"' in resp.text
        assert '"done": true' in resp.text

    def test_batch_success_and_errors(self, client: TestClient, fake_ollama: type[_FakeClient]) -> None:
        resp = client.post(f"{BASE}/batch", json={"prompts": ["a", "b"]}, headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2 and body["completed"] == 2 and body["failed"] == 0

    def test_batch_per_prompt_errors(self, client: TestClient, fake_ollama: type[_FakeClient]) -> None:
        # upstream 500 -> per-prompt error capture, endpoint still 200
        fake_ollama.post_response = _FakeResponse(500)
        resp = client.post(f"{BASE}/batch", json={"prompts": ["a"]}, headers=_headers())
        body = resp.json()
        assert body["completed"] == 0 and body["failed"] == 1

    def test_models_list(self, client: TestClient, fake_ollama: type[_FakeClient]) -> None:
        fake_ollama.get_response = _FakeResponse(
            200,
            {
                "models": [
                    {
                        "name": "llama2",
                        "size": 3826793677,
                        "details": {"parameter_size": "7B", "quantization_level": "Q4_0", "format": "gguf"},
                    }
                ]
            },
        )
        resp = client.get(f"{BASE}/models", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["models"][0]["name"] == "llama2"
        assert body["models"][0]["parameter_size"] == "7B"

    def test_models_degrades_empty_on_error(self, client: TestClient, fake_ollama: type[_FakeClient]) -> None:
        fake_ollama.get_error = httpx.HTTPStatusError(
            "err", request=httpx.Request("GET", "http://x"), response=httpx.Response(500)
        )
        resp = client.get(f"{BASE}/models", headers=_headers())
        assert resp.status_code == 200
        assert resp.json() == {"models": [], "count": 0}

    def test_pull_model(self, client: TestClient, fake_ollama: type[_FakeClient]) -> None:
        fake_ollama.post_response = _FakeResponse(200, {"status": "success", "completed": True})
        resp = client.post(f"{BASE}/models/mistral/pull", headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["model_name"] == "mistral"

    def test_health_reports_ollama_state(self, client: TestClient, fake_ollama: type[_FakeClient]) -> None:
        resp = client.get(f"{BASE}/health", headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["ollama_available"] is True

    def test_health_ollama_down(self, client: TestClient, fake_ollama: type[_FakeClient]) -> None:
        fake_ollama.get_error = httpx.ConnectError("refused")
        resp = client.get(f"{BASE}/health", headers=_headers())
        assert resp.json()["ollama_available"] is False
