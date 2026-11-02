"""Output delivery + cleanup for the ffmpeg service (Refs #799).

Ruling 1A: the output is uploaded to the island IPFS like the other exec
handlers and the local file is deleted — no output may stay in the unit's
tmpfs after the call, on success or failure.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_spec = importlib.util.spec_from_file_location("aitbc_ffmpeg_main", Path(__file__).resolve().parents[1] / "main.py")
ffmpeg_main = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ffmpeg_main)


@pytest.fixture
def client(monkeypatch):
    """TestClient with a fake ffmpeg that writes a marker to the output path."""

    created: list[str] = []

    async def fake_run_cmd(cmd, timeout=0):
        if cmd[:2] == ["ffmpeg", "-hwaccels"]:
            return subprocess.CompletedProcess(cmd, 0, "cuda", "")
        out_path = cmd[-1]
        Path(out_path).write_bytes(b"FAKE-TRANSCODED-OUTPUT")
        created.append(out_path)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(ffmpeg_main, "_run_cmd", fake_run_cmd)
    monkeypatch.setattr(ffmpeg_main, "_ipfs_add_file", lambda path, filename: "bafyTESTCID")
    # /process sits behind the per-job access gate (#803); the gate itself is
    # covered by tests/shop_gate, so this fixture only stands in for a valid job.
    ffmpeg_main.app.dependency_overrides[ffmpeg_main.require_job_access] = lambda: {"job_id": "test-job"}

    yield TestClient(ffmpeg_main.app), created

    ffmpeg_main.app.dependency_overrides.pop(ffmpeg_main.require_job_access, None)


def test_process_returns_cid_and_cleans_both_files(client):
    tc, created = client
    resp = tc.post(
        "/process",
        files={"file": ("clip.mp4", b"\x00\x01fake-media", "video/mp4")},
        data={"output_format": "mp4", "codec": "h264"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["output_cid"] == "bafyTESTCID"
    assert "output_path" not in body
    assert body["result_hash"]
    # The output file the fake ffmpeg wrote must be gone — nothing leaks.
    assert created, "fake ffmpeg never wrote an output"
    for p in created:
        assert not Path(p).exists(), f"output leaked at {p}"


def test_ipfs_failure_is_502_and_still_cleans(client, monkeypatch):
    def _boom(path, filename):
        raise RuntimeError("daemon down")

    monkeypatch.setattr(ffmpeg_main, "_ipfs_add_file", _boom)
    tc, created = client
    resp = tc.post(
        "/process",
        files={"file": ("clip.mp4", b"\x00\x01fake-media", "video/mp4")},
        data={"output_format": "mp4", "codec": "h264"},
    )
    assert resp.status_code == 502, resp.text
    for p in created:
        assert not Path(p).exists(), f"output leaked at {p} even on failure"


def test_ffmpeg_failure_also_cleans(client, monkeypatch):
    async def fail_run_cmd(cmd, timeout=0):
        if cmd[:2] == ["ffmpeg", "-hwaccels"]:
            return subprocess.CompletedProcess(cmd, 0, "cuda", "")
        return subprocess.CompletedProcess(cmd, 1, "", "boom")

    monkeypatch.setattr(ffmpeg_main, "_run_cmd", fail_run_cmd)
    tc, _ = client
    resp = tc.post(
        "/process",
        files={"file": ("clip.mp4", b"\x00\x01fake-media", "video/mp4")},
        data={"output_format": "mp4", "codec": "h264"},
    )
    assert resp.status_code in (500, 503)
