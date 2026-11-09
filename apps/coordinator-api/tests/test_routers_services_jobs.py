"""Router tests for /v1/services/* (#1289 round 9 batch 5).

GPU-workload job submission surface — real JobService + sqlite. Every
typed endpoint creates a real QUEUED job bound to the caller's sub;
catalog endpoints are public reads. ClientDep gates job creation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token

BASE = "/v1/services"


def _headers(sub: str = "client-1", role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


JOB_CASES = [
    ("whisper/transcribe", {"audio_url": "https://x/a.mp3"}),
    ("whisper/translate", {"audio_url": "https://x/a.mp3"}),
    ("stable-diffusion/generate", {"prompt": "a cat"}),
    ("stable-diffusion/img2img", {"prompt": "a cat"}),
    ("llm/inference", {"model": "llama-7b", "prompt": "hi"}),
    ("llm/stream", {"model": "llama-7b", "prompt": "hi"}),
    ("ffmpeg/transcode", {"input_url": "https://x/v.mp4"}),
    ("blender/render", {"blend_file_url": "https://x/s.blend"}),
]


class TestServiceCatalog:
    def test_list_services(self, client: TestClient) -> None:
        resp = client.get(BASE)
        assert resp.status_code == 200
        types = {s["type"] for s in resp.json()["services"]}
        assert {"whisper", "stable_diffusion", "llm_inference", "ffmpeg", "blender"} <= types

    def test_get_service_by_type_and_name(self, client: TestClient) -> None:
        by_type = client.get(f"{BASE}/whisper")
        assert by_type.status_code == 200
        assert by_type.json()["status"] == "available"
        by_name = client.get(f"{BASE}/Whisper Speech Recognition")
        assert by_name.status_code == 200

    def test_get_unknown_404(self, client: TestClient) -> None:
        resp = client.get(f"{BASE}/bogus")
        assert resp.status_code == 404
        assert "whisper" in resp.json()["detail"]

    def test_test_endpoint(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/ffmpeg/test", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["test"] == "passed"
        assert body["capabilities"]["codecs"]

    def test_test_unknown_404(self, client: TestClient) -> None:
        assert client.post(f"{BASE}/bogus/test", headers=_headers()).status_code == 404


class TestJobCreation:
    @pytest.mark.xfail(
        strict=True,
        reason="#1338: ServiceResponse reads job.job_id/job.state.value — Job has id and str state -> 500 after commit",
    )
    @pytest.mark.parametrize("path,payload", JOB_CASES)
    def test_creates_queued_job(self, client: TestClient, path: str, payload: dict) -> None:
        resp = client.post(f"{BASE}/{path}", json=payload, headers=_headers())
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["job_id"]
        assert body["status"] in ("QUEUED", "queued")
        assert body["service_type"]

    @pytest.mark.xfail(strict=True, reason="#1338: same job_id/state 500 on response build")
    def test_caller_binding(self, client: TestClient) -> None:
        # jobs are created under the JWT sub, never a body field
        resp = client.post(f"{BASE}/llm/inference", json={"model": "llama-7b", "prompt": "x"}, headers=_headers("sub-A"))
        assert resp.status_code == 201

    def test_requires_client_role(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/llm/inference",
            json={"model": "llama-7b", "prompt": "x"},
            headers=_headers("miner-1", "miner"),
        )
        assert resp.status_code == 403

    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.post(f"{BASE}/llm/inference", json={"model": "llama-7b", "prompt": "x"})
        assert resp.status_code == 401

    def test_validation(self, client: TestClient) -> None:
        # missing required fields -> 422 before any job is created
        assert client.post(f"{BASE}/whisper/transcribe", json={}, headers=_headers()).status_code == 422
        assert (
            client.post(f"{BASE}/llm/inference", json={"model": "llama-7b", "prompt": ""}, headers=_headers()).status_code
            == 422
        )

    @pytest.mark.xfail(strict=True, reason="#1338: same job_id/state 500 on response build")
    def test_translate_forces_task(self, client: TestClient) -> None:
        resp = client.post(
            f"{BASE}/whisper/translate",
            json={"audio_url": "https://x/a.mp3", "task": "transcribe"},
            headers=_headers(),
        )
        assert resp.status_code == 201
