"""FFMPEG-OUTPUT-VALIDATION-1 (#1818): a transcode that exits 0 but leaves
no usable artifact must fail loudly — not hash, upload, and settle an
empty/corrupt output as success.

``_run_cmd`` and ``_ipfs_add_file`` are mocked per the no-real-ffmpeg rule;
the fake ffmpeg writes whatever the test dictates to the output path.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("aitbc_ffmpeg_main_1818", Path(__file__).resolve().parents[1] / "main.py")
ffmpeg_main = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ffmpeg_main)


class _FakeUpload:
    filename = "clip.mp4"

    async def read(self, size: int = -1) -> bytes:
        if getattr(self, "_done", False):
            return b""
        self._done = True
        return b"fakevideo"


def _run(output_bytes: bytes | None, probe: subprocess.CompletedProcess | None = None):
    """Fake _run_cmd: ffmpeg 'succeeds'; ffprobe returns ``probe`` (default
    a healthy 12.5s duration). ``output_bytes=None`` means ffmpeg writes
    nothing at all."""

    async def fake_run(cmd, timeout):
        if cmd[0] == "ffprobe":
            return probe if probe is not None else subprocess.CompletedProcess(cmd, 0, "12.5\n", "")
        if "-i" not in cmd:
            return subprocess.CompletedProcess(cmd, 0, "cuda\n", "")
        if output_bytes is not None:
            Path(cmd[-1]).write_bytes(output_bytes)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return fake_run


def _process(monkeypatch, output_bytes, probe=None):
    monkeypatch.setattr(ffmpeg_main, "_run_cmd", _run(output_bytes, probe))
    monkeypatch.setattr(ffmpeg_main, "_ipfs_add_file", lambda path, name: "bafycid")
    return asyncio.run(
        ffmpeg_main.process_video(
            file=_FakeUpload(),
            output_format="mp4",
            codec="h264",
            resolution="1080p",
            bitrate="5M",
        )
    )


def _status(exc: BaseException) -> int | None:
    return getattr(exc, "status_code", None)


def test_missing_output_file_fails(monkeypatch):
    """ffmpeg exits 0 but the output path is gone — must not reach IPFS.
    (The service pre-creates the temp file, so 'missing' means ffmpeg
    deleted it or it vanished; the empty-file case is covered separately.)"""
    uploaded: list[str] = []

    async def fake_run(cmd, timeout):
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, "12.5\n", "")
        if "-i" not in cmd:
            return subprocess.CompletedProcess(cmd, 0, "cuda\n", "")
        os.unlink(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(ffmpeg_main, "_run_cmd", fake_run)
    monkeypatch.setattr(ffmpeg_main, "_ipfs_add_file", lambda p, n: uploaded.append(p) or "cid")
    with pytest.raises(Exception) as ei:
        asyncio.run(
            ffmpeg_main.process_video(file=_FakeUpload(), output_format="mp4", codec="h264", resolution="1080p", bitrate="5M")
        )
    assert _status(ei.value) == 500
    assert "no output file" in str(ei.value.detail)
    assert uploaded == []


def test_empty_output_file_fails(monkeypatch):
    with pytest.raises(Exception) as ei:
        _process(monkeypatch, b"")
    assert _status(ei.value) == 500
    assert "empty output" in str(ei.value.detail)


def test_ffprobe_failure_fails(monkeypatch):
    probe = subprocess.CompletedProcess(["ffprobe"], 1, "", "moov atom not found")
    with pytest.raises(Exception) as ei:
        _process(monkeypatch, b"out", probe)
    assert _status(ei.value) == 500
    assert "ffprobe" in str(ei.value.detail)


@pytest.mark.parametrize("stdout", ["0\n", "-1.5\n", "N/A\n", "\n"])
def test_zero_or_unparseable_duration_fails(monkeypatch, stdout):
    probe = subprocess.CompletedProcess(["ffprobe"], 0, stdout, "")
    with pytest.raises(Exception) as ei:
        _process(monkeypatch, b"out", probe)
    assert _status(ei.value) == 500
    assert "no playable duration" in str(ei.value.detail)


def test_valid_output_still_completes(monkeypatch):
    resp = _process(monkeypatch, b"FAKE-TRANSCODED-OUTPUT")
    assert resp.status_code == 200
    assert resp.body
