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


@pytest.mark.unit
def test_media_download_normalizes_active_content_type(client, client_token, tmp_path, monkeypatch):
    """#1752: an uploader-declared active type is never reflected verbatim."""
    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "media_storage_dir", str(tmp_path / "media"))

    resp = client.post(
        "/v1/media/upload",
        files={"file": ("evil.svg", io.BytesIO(b"<svg onload=alert(1)>"), "image/svg+xml")},
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp.status_code == 200
    token = resp.json()["token"]

    download_resp = client.get(f"/v1/media/download/{token}")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"].startswith("application/octet-stream")


@pytest.mark.unit
def test_media_download_keeps_safe_content_type(client, client_token, tmp_path, monkeypatch):
    """#1752: allowlisted media types are still served as declared."""
    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "media_storage_dir", str(tmp_path / "media"))

    resp = client.post(
        "/v1/media/upload",
        files={"file": ("pic.png", io.BytesIO(b"\x89PNG"), "image/png")},
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp.status_code == 200
    token = resp.json()["token"]

    download_resp = client.get(f"/v1/media/download/{token}")
    assert download_resp.headers["content-type"].startswith("image/png")


@pytest.mark.unit
def test_media_upload_global_quota(client, client_token, tmp_path, monkeypatch):
    """#1752: the global byte quota rejects uploads once the store is full."""
    from coordinator_api.config import settings

    monkeypatch.setattr(settings, "media_storage_dir", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "media_storage_max_bytes", 5)

    resp = client.post(
        "/v1/media/upload",
        files={"file": ("a.txt", io.BytesIO(b"12345"), "text/plain")},
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp.status_code == 200

    # Second upload would exceed the 5-byte global quota → 507.
    resp2 = client.post(
        "/v1/media/upload",
        files={"file": ("b.txt", io.BytesIO(b"x"), "text/plain")},
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp2.status_code == 507


@pytest.mark.unit
def test_media_sweep_expires_old_blobs(client, client_token, tmp_path, monkeypatch):
    """#1752: blobs older than the TTL are GC'd on the next upload."""
    import os
    import time

    from coordinator_api.config import settings

    media_dir = tmp_path / "media"
    monkeypatch.setattr(settings, "media_storage_dir", str(media_dir))
    monkeypatch.setattr(settings, "media_storage_ttl_seconds", 60)

    # Seed an expired blob + meta directly.
    media_dir.mkdir(parents=True, exist_ok=True)
    old_blob = media_dir / "oldblob"
    old_blob.write_bytes(b"stale")
    (media_dir / "oldblob.json").write_text('{"filename": "old.txt"}')
    old_time = time.time() - 3600
    os.utime(old_blob, (old_time, old_time))
    os.utime(media_dir / "oldblob.json", (old_time, old_time))

    resp = client.post(
        "/v1/media/upload",
        files={"file": ("new.txt", io.BytesIO(b"fresh"), "text/plain")},
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp.status_code == 200

    assert not old_blob.exists()
    assert not (media_dir / "oldblob.json").exists()
    # The fresh upload survived.
    token = resp.json()["token"]
    assert (media_dir / token).exists()


@pytest.mark.unit
def test_media_download_rejects_non_token_names(client, tmp_path, monkeypatch):
    """#1932 F3: tokens are uuid4().hex — sidecar names and other shapes 404
    before touching the filesystem, even when a matching file exists."""
    from coordinator_api.config import settings

    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "media_storage_dir", str(media_dir))
    # A file literally named like a sidecar must still not be served.
    (media_dir / ("a" * 32 + ".json")).write_text("{}")

    for bad in ("a" * 32 + ".json", "not-a-token", "a" * 31, "A" * 32, "g" * 32):
        resp = client.get(f"/v1/media/download/{bad}")
        assert resp.status_code == 404, bad
