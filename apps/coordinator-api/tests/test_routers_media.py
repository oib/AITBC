"""Tests for the media upload/download router."""

import io

import pytest

from aitbc.auth import create_access_token


@pytest.fixture
def client_token() -> str:
    return create_access_token("client1", "client")


@pytest.mark.unit
def test_media_upload_requires_auth(client):
    """POST /v1/media/upload requires an authenticated client/admin."""
    resp = client.post(
        "/v1/media/upload",
        files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.unit
def test_media_upload_and_download(client, client_token, tmp_path, monkeypatch):
    """An authenticated client can upload a file and anyone with the token can download it."""
    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "media_storage_dir", str(tmp_path / "media"))

    resp = client.post(
        "/v1/media/upload",
        files={"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")},
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["filename"] == "test.txt"
    assert data["size"] == 11
    assert "download_url" in data
    assert "token" in data

    token = data["token"]
    download_resp = client.get(f"/v1/media/download/{token}")
    assert download_resp.status_code == 200
    assert download_resp.content == b"hello world"
    assert download_resp.headers["content-type"].startswith("text/plain")


@pytest.mark.unit
def test_media_upload_size_guard(client, client_token, tmp_path, monkeypatch):
    """Files larger than max_media_upload_bytes are rejected with 413."""
    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "media_storage_dir", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "max_media_upload_bytes", 4)

    resp = client.post(
        "/v1/media/upload",
        files={"file": ("big.txt", io.BytesIO(b"hello"), "text/plain")},
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp.status_code == 413
