"""Router tests for /v1/inference/* (#1289 round 9 batch 4).

Thin Ollama proxy via SharedHttpClient. No Ollama in tests -> the pinned
contract is the honest degradation shape: 503 on connect failure, empty
model list, SSE error event, per-prompt error capture in batch.
Matrix /v1/inference* -> ANY.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from aitbc.auth.security_matrix import AuthLevel, get_auth_level

BASE = "/v1/inference"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('u', 'client')}"}


class TestInferenceContract:
    def test_matrix_any(self) -> None:
        assert get_auth_level("/v1/inference/generate") == AuthLevel.ANY

    def test_generate_ollama_down_503(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/generate", json={"prompt": "hi"}, headers=_headers())
        assert resp.status_code == 503

    def test_generate_validation(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/generate", json={}, headers=_headers()).status_code == 422
        assert client.post(f"{BASE}/generate", json={"prompt": "x", "temperature": 5.0}, headers=_headers()).status_code == 422

    def test_generate_stream_sse_error_event(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/generate/stream", json={"prompt": "hi"}, headers=_headers())
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "error" in resp.text

    def test_batch_captures_per_prompt_errors(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/batch", json={"prompts": ["a", "b"]}, headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["completed"] == 0
        assert body["failed"] == 2

    def test_batch_validation(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/batch", json={"prompts": []}, headers=_headers()).status_code == 422

    def test_models_empty_when_down(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/models", headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_pull_ollama_down_503(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/models/llama2/pull", headers=_headers())
        assert resp.status_code == 503

    def test_health_reports_ollama_state(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/health", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "inference"
        assert body["ollama_available"] is False
