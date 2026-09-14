"""`/transcribe` bounds what one caller can make the whisper service allocate.

The endpoint used to do `tmp.write(await file.read())` with no limit anywhere in
the path, so peak RSS was a direct function of what the caller chose to send. That
mattered because transcription cost tracks audio length -- roughly 1G of transient
allocation per ten minutes -- and the unit's `MemoryMax` was the only thing standing
between an oversized upload and the rest of the host.

Three layers now, and each exists because the others cannot cover its case:

* a Content-Length check in middleware, because resolving an `UploadFile` parameter
  means `await request.form()`, which spools the whole multipart body to disk before
  the endpoint is entered -- far too late to refuse the transfer;
* a streaming byte counter, because Content-Length is absent on a chunked upload and
  a caller can lie about it anyway;
* a duration probe off the container header, because bytes are a poor proxy for cost
  -- a small compressed file can decode into hours of audio, and
  `WhisperModel.transcribe()` only reports `info.duration` after decoding the whole
  clip into memory.

The model is never loaded here. `TestClient` is used without its context manager so
the lifespan never runs, and `_model` is replaced with a stub; these tests are about
what the service refuses, not about transcription.

`av` is a different matter and is not stubbed. It is faster-whisper's own decoder,
so it is installed where whisper runs -- which is one host -- and the tests that
reach the probe skip elsewhere rather than pretending to have checked it. Stubbing
it would leave the one thing worth testing, that a real container header gives a
real duration, untested everywhere.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import io
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "apps/whisper/main.py"

requires_av = pytest.mark.skipif(
    importlib.util.find_spec("av") is None,
    reason="av ships with faster-whisper, so it is present where whisper runs rather than fleet-wide",
)


def _write_wav(path: Path, seconds: float, rate: int = 16000) -> Path:
    """A real RIFF container, so the duration probe is tested against a real header."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(seconds * rate))
    return path


@pytest.fixture(scope="module")
def whisper(tmp_path_factory):
    """Load `apps/whisper/main.py` by path, with the log tree redirected.

    `apps/whisper` is not a package and is not on `pythonpath`. The redirect is not
    optional: the module calls `configure_logging(..., to_file=True)` at import, and
    the resolver creates the directory it returns -- importing this under a root
    pytest run would otherwise leave `/var/log/aitbc/whisper` owned by root, which
    the `aitbc` service user then could not write to.
    """
    logs = tmp_path_factory.mktemp("logs")
    old = os.environ.get("LOG_DIR")
    os.environ["LOG_DIR"] = str(logs)
    try:
        spec = importlib.util.spec_from_file_location("whisper_main_under_test", MODULE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop("whisper_main_under_test", None)
        if old is None:
            os.environ.pop("LOG_DIR", None)
        else:
            os.environ["LOG_DIR"] = old


class _StubSegment:
    start = 0.0
    end = 1.0
    text = " hello "


class _StubInfo:
    duration = 1.0
    language = "en"
    language_probability = 0.99


class _StubModel:
    """Stands in for WhisperModel. Records what it was handed, transcribes nothing."""

    def __init__(self):
        self.calls = []

    def transcribe(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return iter([_StubSegment()]), _StubInfo()


@pytest.fixture
def client(whisper, tmp_path, monkeypatch):
    """A client with a stub model, and every temp file confined to tmp_path.

    Pointing `tempfile.tempdir` here is what makes the cleanup assertions possible:
    the directory's contents are known, so anything left behind at the end of a
    request is a leak the test can see.
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(whisper, "_model", _StubModel())
    # No `with`: the context manager runs the lifespan, which would load the model.
    return TestClient(whisper.app)


def _post(client, data: bytes, filename: str = "clip.wav", **form):
    return client.post("/transcribe", files={"file": (filename, data, "audio/wav")}, data=form)


# --- the suffix, which becomes part of a filename -------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("clip.wav", ".wav"),
        ("clip.MP3", ".mp3"),
        ("clip.flac", ".flac"),
        (None, ".wav"),
        ("", ".wav"),
        ("no-extension", ".wav"),
        ("clip." + "a" * 200, ".wav"),
        ("clip.wav;rm -rf /", ".wav"),
        ("../../etc/passwd", ".wav"),
    ],
)
def test_the_suffix_is_bounded(whisper, filename, expected):
    assert whisper._safe_suffix(filename) == expected


def test_the_suffix_can_never_contain_a_separator(whisper):
    """The property the docstring leans on, asserted rather than assumed."""
    for name in ("a/b", "a.b/c", "x./../../etc/shadow", "f.wav/../../root/.ssh/id_rsa"):
        assert os.sep not in whisper._safe_suffix(name)


# --- the streaming byte limit ---------------------------------------------------


def _spool(whisper, data: bytes):
    upload = UploadFile(file=io.BytesIO(data), filename="clip.wav", size=len(data))
    return asyncio.run(whisper._spool_upload(upload, ".wav"))


def test_an_upload_under_the_limit_lands_on_disk(whisper, tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    path = _spool(whisper, b"x" * 4096)
    try:
        assert Path(path).read_bytes() == b"x" * 4096
    finally:
        os.unlink(path)


def test_an_oversized_upload_is_refused_with_413(whisper, tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(whisper, "_MAX_UPLOAD_BYTES", 1024)
    with pytest.raises(HTTPException) as excinfo:
        _spool(whisper, b"x" * 8192)
    assert excinfo.value.status_code == 413


def test_a_refused_upload_leaves_no_temp_file(whisper, tmp_path, monkeypatch):
    """`delete=False` means the file outlives its handle. Nothing else knows its name
    at that point, so if `_spool_upload` does not remove it, nothing will."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(whisper, "_MAX_UPLOAD_BYTES", 1024)
    with pytest.raises(HTTPException):
        _spool(whisper, b"x" * 8192)
    assert list(tmp_path.iterdir()) == []


def test_the_limit_is_enforced_while_reading_not_after(whisper, tmp_path, monkeypatch):
    """The point of streaming: the whole upload must never be resident at once.

    A single `read()` with no size argument would defeat the limit entirely -- the
    bytes would already be in memory by the time the counter saw them -- so this
    asserts the read is chunked, and that every chunk is bounded.
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(whisper, "_UPLOAD_CHUNK", 1024)
    sizes = []

    class _CountingUpload(UploadFile):
        async def read(self, size: int = -1) -> bytes:  # type: ignore[override]
            sizes.append(size)
            return await super().read(size)

    upload = _CountingUpload(file=io.BytesIO(b"x" * 5000), filename="c.wav", size=5000)
    path = asyncio.run(whisper._spool_upload(upload, ".wav"))
    try:
        assert len(sizes) > 1, "the upload was read in one call; the limit cannot bind"
        assert set(sizes) == {1024}, f"unbounded read among {sizes}"
    finally:
        os.unlink(path)


# --- the duration probe ---------------------------------------------------------


@requires_av
def test_the_probe_reads_duration_without_decoding(whisper, tmp_path):
    path = _write_wav(tmp_path / "two.wav", seconds=2.0)
    assert whisper._audio_seconds(str(path)) == pytest.approx(2.0, abs=0.05)


@requires_av
def test_the_probe_returns_none_for_something_that_is_not_audio(whisper, tmp_path):
    """None, not an exception: an unreadable container is faster-whisper's to report,
    and its error names the real problem better than anything here could."""
    junk = tmp_path / "junk.wav"
    junk.write_bytes(b"not a container")
    assert whisper._audio_seconds(str(junk)) is None


@requires_av
def test_audio_over_the_duration_limit_is_refused(client, whisper, tmp_path, monkeypatch):
    monkeypatch.setattr(whisper, "_MAX_AUDIO_SECONDS", 1.0)
    data = _write_wav(tmp_path / "long.wav", seconds=3.0).read_bytes()
    response = _post(client, data)
    assert response.status_code == 413
    assert "minutes" in response.json()["detail"]
    assert whisper._model.calls == [], "the model was handed work that should have been refused"


@requires_av
def test_audio_within_the_duration_limit_is_transcribed(client, whisper, tmp_path):
    data = _write_wav(tmp_path / "short.wav", seconds=1.0).read_bytes()
    response = _post(client, data)
    assert response.status_code == 200
    assert response.json()["text"] == "hello"
    assert len(whisper._model.calls) == 1


# --- the parameters that drive decode cost --------------------------------------


@pytest.mark.parametrize("beam_size", [0, -1, 11, 10_000])
def test_an_out_of_range_beam_size_is_refused(client, whisper, tmp_path, beam_size):
    """coordinator-api already declares `ge=1, le=10` on WhisperRequest.beam_size.
    Beam width multiplies decode memory, so the service has to enforce it too -- a
    bound only the caller respects is not a bound."""
    data = _write_wav(tmp_path / "s.wav", seconds=1.0).read_bytes()
    response = _post(client, data, beam_size=beam_size)
    assert response.status_code == 400
    assert whisper._model.calls == []


@requires_av
@pytest.mark.parametrize("beam_size", [1, 5, 10])
def test_an_in_range_beam_size_is_passed_through(client, whisper, tmp_path, beam_size):
    data = _write_wav(tmp_path / "s.wav", seconds=1.0).read_bytes()
    assert _post(client, data, beam_size=beam_size).status_code == 200
    assert whisper._model.calls[0][1]["beam_size"] == beam_size


@requires_av
@pytest.mark.parametrize("task", ["translate", "transcribe"])
def test_the_two_real_tasks_are_accepted(client, whisper, tmp_path, task):
    data = _write_wav(tmp_path / "s.wav", seconds=1.0).read_bytes()
    assert _post(client, data, task=task).status_code == 200
    assert whisper._model.calls[0][1]["task"] == task


def test_an_unknown_task_is_refused_rather_than_raised(client, whisper, tmp_path):
    """Unvalidated, this reached faster-whisper and came back as an unexplained 500."""
    data = _write_wav(tmp_path / "s.wav", seconds=1.0).read_bytes()
    response = _post(client, data, task="rm -rf")
    assert response.status_code == 400
    assert whisper._model.calls == []


# --- the header check ------------------------------------------------------------


def test_an_oversized_body_is_refused_before_it_is_read(client, whisper, tmp_path, monkeypatch):
    """413 from the middleware, and the endpoint never runs -- no temp file, no model
    call. A small limit rather than a large body: the assertion is about where the
    refusal happens, not about moving a hundred megabytes through a test."""
    monkeypatch.setattr(whisper, "_MAX_BODY_BYTES", 128)
    data = _write_wav(tmp_path / "s.wav", seconds=1.0).read_bytes()
    before = set(tmp_path.iterdir())
    response = _post(client, data)
    assert response.status_code == 413
    assert "limit" in response.json()["detail"]
    assert whisper._model.calls == []
    assert set(tmp_path.iterdir()) == before


@requires_av
def test_a_body_within_the_header_limit_is_let_through(client, whisper, tmp_path):
    data = _write_wav(tmp_path / "s.wav", seconds=1.0).read_bytes()
    assert _post(client, data).status_code == 200


# --- no temp file survives any path ---------------------------------------------


@requires_av
def test_a_completed_request_leaves_no_temp_file(client, whisper, tmp_path):
    wav = _write_wav(tmp_path / "s.wav", seconds=1.0)
    assert _post(client, wav.read_bytes()).status_code == 200
    assert list(tmp_path.iterdir()) == [wav], "the transcription temp file outlived the request"


@requires_av
def test_a_rejected_request_leaves_no_temp_file(client, whisper, tmp_path, monkeypatch):
    monkeypatch.setattr(whisper, "_MAX_AUDIO_SECONDS", 1.0)
    wav = _write_wav(tmp_path / "s.wav", seconds=3.0)
    assert _post(client, wav.read_bytes()).status_code == 413
    assert list(tmp_path.iterdir()) == [wav]


# --- the shape of the fix, which a behavioural test cannot pin ------------------


def test_the_endpoint_never_reads_an_upload_whole_again(whisper):
    """`await file.read()` with no size argument is the bug this file exists for.

    Every guard above still passes if someone reinstates it -- the limits would just
    be applied to something already fully resident. So this checks the source: a bare
    `.read()` on the upload is what must not come back.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
    bare = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "read"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "file"
        and not node.args
    ]
    assert not bare, f"unbounded file.read() at line(s) {[n.lineno for n in bare]}"
