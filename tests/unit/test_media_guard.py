"""CE-001 (#1170): untrusted media is opened with a protocol and format whitelist.

FFmpeg sniffs content, so a playlist uploaded as ``clip.mp4`` (or downloaded as
``input.m3u8``) is followed to nested resources of the uploader's choosing. The guard
must sit immediately before ``-i`` in every FFmpeg command the shop and miner build, and in
the PyAV probe the whisper service runs before faster-whisper decodes the same file.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from aitbc import media_guard

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_guard_is_file_only_and_excludes_every_playlist_or_script_demuxer():
    guard = media_guard.ffmpeg_input_guard()
    assert guard[:2] == ["-protocol_whitelist", "file"]
    assert guard[2] == "-format_whitelist"
    allowed = set(guard[3].split(","))
    for nested_capable in ("hls", "dash", "concat", "sdp", "rtsp", "ffmetadata", "data", "tcp", "http"):
        assert nested_capable not in allowed
    for plain in ("mov", "mp4", "matroska", "webm", "avi", "mpegts", "wav", "mp3", "ogg", "flac", "aac", "image2"):
        assert plain in allowed
    assert media_guard.pyav_open_options() == {"protocol_whitelist": "file", "format_whitelist": guard[3]}


def test_ffmpeg_service_puts_the_guard_before_dash_i(monkeypatch):
    from fastapi.testclient import TestClient

    mod = _load("e1170_ffmpeg_main", "apps/ffmpeg/main.py")
    seen: list[list[str]] = []

    async def fake_run_cmd(cmd, timeout=0):
        if cmd[:2] == ["ffmpeg", "-hwaccels"]:
            return subprocess.CompletedProcess(cmd, 0, "cuda", "")
        seen.append(cmd)
        Path(cmd[-1]).write_bytes(b"x")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(mod, "_run_cmd", fake_run_cmd)
    monkeypatch.setattr(mod, "_ipfs_add_file", lambda path, filename: "bafy")
    mod.app.dependency_overrides[mod.require_job_access] = lambda: {"job_id": "j"}
    try:
        r = TestClient(mod.app).post(
            "/process",
            files={"file": ("evil.m3u8", b"#EXTM3U\n", "application/octet-stream")},
            data={"output_format": "mp4", "codec": "h264"},
        )
    finally:
        mod.app.dependency_overrides.pop(mod.require_job_access, None)
    assert r.status_code == 200, r.text
    (cmd,) = seen
    i = cmd.index("-i")
    assert cmd[i - 4 : i] == media_guard.ffmpeg_input_guard(), cmd


def test_miner_reencode_puts_the_guard_before_dash_i(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "apps" / "miner"))  # sibling modules the miner imports by bare name
    monkeypatch.setenv("MINER_ID", "test-miner")  # the module refuses to import without an identity
    monkeypatch.setenv("MINER_AUTH_TOKEN", "test-auth-token")
    mod = _load("e1170_miner", "apps/miner/production_miner.py")
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    mod._run_ffmpeg("/tmp/input.m3u8", "/tmp/o.mp4", "mp4")
    (cmd,) = seen
    i = cmd.index("-i")
    assert cmd[i - 4 : i] == media_guard.ffmpeg_input_guard(), cmd


def test_whisper_probe_opens_with_the_guard_and_the_endpoint_refuses_an_unprobeable_file(monkeypatch, tmp_path):
    opened: dict[str, object] = {}

    class _Container:
        duration = 2_000_000

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake_av = types.ModuleType("av")
    fake_av.time_base = 1_000_000

    def fake_open(path, **kw):
        opened.update(kw)
        if str(path).endswith(".m3u8"):
            raise OSError("Format not on whitelist")
        return _Container()

    fake_av.open = fake_open
    monkeypatch.setitem(sys.modules, "av", fake_av)
    mod = _load("e1170_whisper", "apps/whisper/main.py")

    good = tmp_path / "a.wav"
    good.write_bytes(b"x")
    assert mod._probe_duration(str(good)) == 2.0
    assert opened["options"] == media_guard.pyav_open_options()

    bad = tmp_path / "evil.m3u8"
    bad.write_bytes(b"#EXTM3U\n")
    assert mod._audio_seconds(str(bad)) is None, "_audio_seconds keeps its None-for-unreadable contract"
    with pytest.raises(OSError):
        mod._probe_duration(str(bad))

    # The endpoint refuses what the guarded probe cannot open, before the model sees it.
    from fastapi.testclient import TestClient

    class _Model:
        calls = 0

        def transcribe(self, *a, **k):
            _Model.calls += 1
            return iter(()), types.SimpleNamespace(duration=0, language="en", language_probability=1.0)

    monkeypatch.setattr(mod, "_model", _Model())
    mod.app.dependency_overrides[mod.require_job_access] = lambda: {"job_id": "j"}
    try:
        client = TestClient(mod.app)
        r = client.post("/transcribe", files={"file": ("evil.m3u8", b"#EXTM3U\n", "application/octet-stream")})
        assert r.status_code == 415, r.text
        assert _Model.calls == 0, "faster-whisper was handed a file the guard refused"
        ok = client.post("/transcribe", files={"file": ("a.wav", b"x", "audio/wav")})
        assert ok.status_code == 200, ok.text
        assert _Model.calls == 1
    finally:
        mod.app.dependency_overrides.pop(mod.require_job_access, None)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs a real ffmpeg")
class TestRealFfmpeg:
    """The same options against the real binary: playlists refused, plain media untouched."""

    @pytest.fixture
    def media(self, tmp_path):
        mp4 = tmp_path / "secret.mp4"
        r = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=1:size=64x64:rate=5",
                "-c:v",
                "mpeg4",
                str(mp4),
            ],
            capture_output=True,
        )
        if r.returncode != 0:
            pytest.skip("ffmpeg cannot encode a test clip here")
        (tmp_path / "evil.m3u8").write_text(f"#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\nfile://{mp4}\n#EXT-X-ENDLIST\n")
        (tmp_path / "evil.mp4").write_text(f"#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\nfile://{mp4}\n#EXT-X-ENDLIST\n")
        return tmp_path

    def _transcode(self, src: Path, out: Path, guarded: bool) -> subprocess.CompletedProcess[bytes]:
        guard = media_guard.ffmpeg_input_guard() if guarded else []
        return subprocess.run(
            ["ffmpeg", "-v", "error", "-y", *guard, "-i", str(src), "-c:v", "mpeg4", str(out)], capture_output=True
        )

    def test_a_playlist_is_followed_without_the_guard_and_refused_with_it(self, media):
        # ffmpeg only sniffs HLS from an .m3u8 name, so that is the vector that is live here.
        assert self._transcode(media / "evil.m3u8", media / "open.mp4", guarded=False).returncode == 0
        refused = self._transcode(media / "evil.m3u8", media / "shut.mp4", guarded=True)
        assert refused.returncode != 0
        assert b"whitelist" in refused.stderr
        assert not (media / "shut.mp4").exists() or (media / "shut.mp4").stat().st_size == 0

    def test_plain_media_still_transcodes_with_the_guard(self, media):
        r = self._transcode(media / "secret.mp4", media / "ok.mp4", guarded=True)
        assert r.returncode == 0, r.stderr
        assert (media / "ok.mp4").stat().st_size > 0
