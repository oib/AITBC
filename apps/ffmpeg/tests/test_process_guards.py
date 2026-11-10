"""Tests for the /process input guards (FFMPEG-ARGV-1 #1456, FFMPEG-CONC-1 #1459).

The endpoint is invoked directly — no TestClient, no lifespan — with the
subprocess boundary (``_run_cmd``) and the IPFS uploader mocked, per the
no-real-ffmpeg rule.
"""

from __future__ import annotations

import asyncio
import importlib.util
import subprocess
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("aitbc_ffmpeg_main_guards", Path(__file__).resolve().parents[1] / "main.py")
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


def _process(**overrides):
    kwargs = {
        "file": _FakeUpload(),
        "output_format": "mp4",
        "codec": "h264",
        "resolution": "1080p",
        "bitrate": "5M",
    }
    kwargs.update(overrides)
    return asyncio.run(ffmpeg_main.process_video(**kwargs))


def _http_status(exc: BaseException) -> int | None:
    return getattr(exc, "status_code", None)


# --- FFMPEG-ARGV-1: codec / bitrate validation ---


@pytest.mark.parametrize("codec", ["h264; rm -rf /", "-i /etc/passwd", "H264 NVENC", "x" * 40, "", "h264 codec"])
def test_process_rejects_bad_codec(codec: str) -> None:
    with pytest.raises(Exception) as ei:
        _process(codec=codec)
    assert _http_status(ei.value) == 400


@pytest.mark.parametrize("bitrate", ["", "abc", "-5M", "5M;id", "1e9", "999999999G", "2G"])
def test_process_rejects_bad_or_huge_bitrate(bitrate: str) -> None:
    """Empty/junk rates used to IndexError or produce nonsense VBV values.
    "2G" is syntactically fine but over the 400 Mbit/s ceiling."""
    with pytest.raises(Exception) as ei:
        _process(bitrate=bitrate)
    assert _http_status(ei.value) == 400


def test_process_accepts_unitless_and_kbit_bitrates(monkeypatch) -> None:
    """'5' -> 5M, '2500k' and '0.3G' are legitimate; validation must not break them."""
    _fake_ffmpeg_run(monkeypatch)
    for bitrate in ("5", "2500k", "10M", "0.3G"):
        resp = _process(bitrate=bitrate)
        assert resp.status_code == 200


# --- FFMPEG-OUT-1 (#1648): output_format muxer allowlist + -fs output cap ---


@pytest.mark.parametrize("output_format", ["m3u8", "hls", "dash", "segment", "mp4/../../x", "png"])
def test_process_rejects_segmenting_or_unknown_output_format(output_format: str) -> None:
    """output_format lands in the temp suffix and picks the ffmpeg muxer —
    segmenting formats (m3u8/hls/dash) write sidecars the cleanup never
    deletes, and unknown extensions are refused outright."""
    with pytest.raises(Exception) as ei:
        _process(output_format=output_format)
    assert _http_status(ei.value) == 400


def test_process_accepts_empty_output_format_as_default(monkeypatch) -> None:
    _fake_ffmpeg_run(monkeypatch)
    resp = _process(output_format="")
    assert resp.status_code == 200


def test_process_passes_fs_output_cap(monkeypatch) -> None:
    """-fs bounds the transcode output; without it duration×bitrate is unbounded."""
    captured: list[list[str]] = []

    async def fake_run(cmd, timeout):
        captured.append(list(cmd))
        if "-i" not in cmd:
            return subprocess.CompletedProcess(cmd, 0, "cuda\n", "")
        Path(cmd[-1]).write_bytes(b"out")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(ffmpeg_main, "_run_cmd", fake_run)
    monkeypatch.setattr(ffmpeg_main, "_ipfs_add_file", lambda path, name: "bafycid")

    resp = _process(output_format="mkv")
    assert resp.status_code == 200
    cmd = captured[-1]
    assert cmd[cmd.index("-fs") + 1] == str(ffmpeg_main._MAX_OUTPUT_BYTES)
    assert cmd[-1].endswith(".mkv")


# --- FFMPEG-CONC-1: admission bound ---


def test_process_busy_returns_503(monkeypatch) -> None:
    _fake_ffmpeg_run(monkeypatch)
    monkeypatch.setattr(ffmpeg_main, "_inflight", ffmpeg_main._MAX_CONCURRENT)
    with pytest.raises(Exception) as ei:
        _process()
    assert _http_status(ei.value) == 503
    assert ffmpeg_main._inflight == ffmpeg_main._MAX_CONCURRENT


def test_process_releases_slot_after_job(monkeypatch) -> None:
    _fake_ffmpeg_run(monkeypatch)
    _process()
    assert ffmpeg_main._inflight == 0
    _process()
    assert ffmpeg_main._inflight == 0


def test_process_releases_slot_on_ffmpeg_failure(monkeypatch) -> None:
    async def failing_run(cmd, timeout):
        if "-i" not in cmd:
            # hwaccels probe must report cuda support.
            return subprocess.CompletedProcess(cmd, 0, "cuda\n", "")
        return subprocess.CompletedProcess(cmd, 1, "", "boom")

    monkeypatch.setattr(ffmpeg_main, "_run_cmd", failing_run)
    with pytest.raises(Exception) as ei:
        _process()
    assert _http_status(ei.value) == 500
    assert ffmpeg_main._inflight == 0


# --- argv shape ---


def test_process_builds_expected_argv(monkeypatch) -> None:
    captured: list[list[str]] = []

    async def fake_run(cmd, timeout):
        captured.append(list(cmd))
        if "-i" not in cmd:
            # hwaccels probe must report cuda support.
            return subprocess.CompletedProcess(cmd, 0, "cuda\n", "")
        # Write a small output file where ffmpeg would have written it.
        Path(cmd[-1]).write_bytes(b"out")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(ffmpeg_main, "_run_cmd", fake_run)
    monkeypatch.setattr(ffmpeg_main, "_ipfs_add_file", lambda path, name: "bafycid")

    resp = _process(codec="hevc", bitrate="2500k", output_format="webm")
    assert resp.status_code == 200
    cmd = captured[-1]
    assert cmd[cmd.index("-c:v") + 1] == "hevc_nvenc"
    assert cmd[cmd.index("-b:v") + 1] == "2500k"
    assert cmd[cmd.index("-bufsize") + 1] == "2500k"
    # The IPFS filename uses the sanitized suffix, not raw output_format.
    # (filename asserted via the patched _ipfs_add_file below)


def _fake_ffmpeg_run(monkeypatch) -> None:
    """Default happy-path mocks: ffmpeg succeeds, IPFS returns a CID."""

    async def fake_run(cmd, timeout):
        if "-i" not in cmd:
            return subprocess.CompletedProcess(cmd, 0, "cuda\n", "")
        Path(cmd[-1]).write_bytes(b"out")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(ffmpeg_main, "_run_cmd", fake_run)
    monkeypatch.setattr(ffmpeg_main, "_ipfs_add_file", lambda path, name: "bafycid")
