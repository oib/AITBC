"""#2002 SERVICE-ROUTE-TTL-UNBOUNDED-1 — public /v1/services/* TTL bounds."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from coordinator_api.config import settings
from coordinator_api.contexts.infrastructure.routers import services as services_mod
from coordinator_api.contexts.infrastructure.services.jobs import JobService
from coordinator_api.models.services import BlenderRequest, WhisperRequest


def _headers(sub: str = "client-1") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, 'client')}"}


@pytest.mark.unit
def test_public_service_routes_pass_ttl_cap(monkeypatch) -> None:
    """Every typed service job path must pass ttl_cap=settings.job_ttl_seconds."""
    captured: list[int | None] = []

    def _capture_create(self, client_id, req, *, ttl_cap=None, enforce_inflight_cap=False, **_kwargs):
        captured.append(ttl_cap)
        job = MagicMock()
        job.id = "job-x"
        job.state = "QUEUED"
        job.expires_at = MagicMock(isoformat=lambda: "2030-01-01T00:00:00+00:00")
        return job

    monkeypatch.setattr(JobService, "create_job", _capture_create)

    class _Session:
        pass

    user = {"sub": "client-1"}
    services_mod.whisper_transcribe(
        MagicMock(),
        WhisperRequest(audio_url="https://x/a.mp3"),
        _Session(),
        user,
    )
    services_mod.blender_render(
        MagicMock(),
        BlenderRequest(blend_file_url="https://x/s.blend"),
        _Session(),
        user,
    )
    assert captured == [settings.job_ttl_seconds, settings.job_ttl_seconds]


@pytest.mark.unit
def test_blender_rejects_unbounded_frame_span(client: TestClient) -> None:
    max_frames = max(1, settings.job_ttl_seconds // 30)
    resp = client.post(
        "/v1/services/blender/render",
        json={
            "blend_file_url": "https://x/s.blend",
            "frame_start": 1,
            "frame_end": max_frames + 100,
        },
        headers=_headers(),
    )
    assert resp.status_code == 422


@pytest.mark.unit
def test_blender_job_ttl_capped_at_public_ceiling(client: TestClient, db_session) -> None:
    max_frames = max(1, settings.job_ttl_seconds // 30)
    resp = client.post(
        "/v1/services/blender/render",
        json={
            "blend_file_url": "https://x/s.blend",
            "frame_start": 1,
            "frame_end": max_frames,
        },
        headers=_headers(),
    )
    assert resp.status_code == 201, resp.text
    from coordinator_api.contexts.infrastructure.domain import Job

    job = db_session.get(Job, resp.json()["job_id"])
    assert job is not None
    assert job.ttl_seconds <= settings.job_ttl_seconds
