"""IPFS add→pin→retrieve for ffmpeg output delivery (Refs #1786)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import requests

_spec = importlib.util.spec_from_file_location("aitbc_ffmpeg_main", Path(__file__).resolve().parents[1] / "main.py")
ffmpeg_main = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ffmpeg_main)


class _MockResp:
    def __init__(self, *, status: int = 200, json_data: dict | None = None, content: bytes = b""):
        self.status_code = status
        self._json = json_data or {}
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self) -> dict:
        return self._json


def test_ipfs_add_file_pins_and_content_retrievable(monkeypatch, tmp_path: Path):
    payload = b"pinned-ffmpeg-output"
    media = tmp_path / "out.mp4"
    media.write_bytes(payload)
    calls: list[tuple[str, dict]] = []
    test_cid = "bafybeigdyrzt5sfp7udm7hx76e76zol5y4422mhemed2tzvm7ag4uqj3xu"

    def fake_post(url: str, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/api/v0/add"):
            return _MockResp(json_data={"Hash": test_cid})
        if url.endswith("/api/v0/pin/add"):
            assert kwargs.get("params", {}).get("arg") == test_cid
            return _MockResp()
        if url.endswith("/api/v0/cat"):
            assert kwargs.get("params", {}).get("arg") == test_cid
            return _MockResp(content=payload)
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(requests, "post", fake_post)

    cid = ffmpeg_main._ipfs_add_file(str(media), "output.mp4")
    assert cid == test_cid
    assert any(u.endswith("/api/v0/pin/add") for u, _ in calls)

    cat = requests.post(
        f"{ffmpeg_main._ISLAND_IPFS_API.rstrip('/')}/api/v0/cat",
        params={"arg": cid},
        timeout=30,
    )
    cat.raise_for_status()
    assert cat.content == payload


def test_ipfs_add_file_pin_failure_raises(monkeypatch, tmp_path: Path):
    media = tmp_path / "out.mp4"
    media.write_bytes(b"x")

    def fake_post(url: str, **kwargs):
        if url.endswith("/api/v0/add"):
            return _MockResp(json_data={"Hash": "bafyTEST"})
        if url.endswith("/api/v0/pin/add"):
            return _MockResp(status=500)
        raise AssertionError(url)

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(requests.HTTPError):
        ffmpeg_main._ipfs_add_file(str(media), "output.mp4")
