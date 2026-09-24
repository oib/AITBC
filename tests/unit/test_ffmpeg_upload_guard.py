"""`/process` bounds what one caller can make the ffmpeg service allocate.

The endpoint used to do `input_tmp.write(await file.read())` with no limit
anywhere in the path, so peak RSS was a direct function of what the caller chose
to send. That mattered because per-request cost tracks upload size -- a 300 s
1080p job (229M upload, 190M output) peaked at 1.16G under the unit's 2G
`MemoryMax`, which was the only thing standing between an oversized upload and
the rest of the host.

Two layers now, and each exists because the other cannot cover its case:

* a Content-Length check in middleware, because resolving an `UploadFile`
  parameter means `await request.form()`, which spools the whole multipart body
  to disk before the endpoint is entered -- far too late to refuse the transfer;
* a streaming byte counter in `_spool_upload`, because Content-Length is absent
  on a chunked upload and a caller can lie about it anyway.

Unlike whisper there is no duration probe: transcode cost tracks bytes, not
decoded minutes, and the service has no decoder library of its own to probe a
container header with.

The real ffmpeg never runs here. `TestClient` is used without its context
manager so the lifespan never starts, and `_run_cmd` is replaced with a
stub that answers the `-hwaccels` probe and the transcode call -- these tests
are about what the service refuses, not about transcoding.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "apps/ffmpeg/main.py"

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


@pytest.fixture(scope="module")
def ffmpeg(tmp_path_factory):
    """Load `apps/ffmpeg/main.py` by path, with the log tree redirected.

    `apps/ffmpeg` is not a package and is not on `pythonpath`. The redirect is
    not optional: the module calls `configure_logging(..., to_file=True)` at
    import, and the resolver creates the directory it returns -- importing this
    under a root pytest run would otherwise leave `/var/log/aitbc/ffmpeg` owned
    by root, which the `aitbc` service user then could not write to.
    """
    logs = tmp_path_factory.mktemp("logs")
    old = os.environ.get("LOG_DIR")
    os.environ["LOG_DIR"] = str(logs)
    try:
        spec = importlib.util.spec_from_file_location("ffmpeg_main_under_test", MODULE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop("ffmpeg_main_under_test", None)
        if old is None:
            os.environ.pop("LOG_DIR", None)
        else:
            os.environ["LOG_DIR"] = old


def _fake_run(calls: list[list[str]] | None = None):
    """Stand in for _run_cmd: -hwaccels reports cuda, everything else succeeds."""

    async def _run(cmd, timeout=None, **kwargs):
        if calls is not None:
            calls.append(list(cmd))
        stdout = "cuda\nvaapi\n" if list(cmd[:2]) == ["ffmpeg", "-hwaccels"] else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    return _run


@pytest.fixture
def client(ffmpeg, tmp_path, monkeypatch):
    """A client with ffmpeg stubbed out, and every temp file confined to tmp_path.

    Pointing `tempfile.tempdir` here is what makes the cleanup assertions
    possible: the directory's contents are known, so anything left behind at the
    end of a request is a leak the test can see.
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(ffmpeg, "_run_cmd", _fake_run())
    # No `with`: the context manager runs the lifespan, which would shell out.
    return TestClient(ffmpeg.app)


def _post(client, data: bytes, filename: str = "clip.mp4", **form):
    return client.post("/process", files={"file": (filename, data, "video/mp4")}, data=form)


# --- the suffix, which becomes part of a filename -------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("clip.mp4", ".mp4"),
        ("clip.MKV", ".mkv"),
        ("clip.webm", ".webm"),
        (None, ".mp4"),
        ("", ".mp4"),
        ("no-extension", ".mp4"),
        ("clip." + "a" * 200, ".mp4"),
        ("clip.mp4;rm -rf /", ".mp4"),
        ("../../etc/passwd", ".mp4"),
    ],
)
def test_the_suffix_is_bounded(ffmpeg, filename, expected):
    assert ffmpeg._safe_suffix(filename) == expected


def test_the_suffix_can_never_contain_a_separator(ffmpeg):
    """The property the docstring leans on, asserted rather than assumed."""
    for name in ("a/b", "a.b/c", "x./../../etc/shadow", "f.mp4/../../root/.ssh/id_rsa"):
        assert os.sep not in ffmpeg._safe_suffix(name)


# --- the streaming byte limit ---------------------------------------------------


def _spool(ffmpeg, data: bytes):
    upload = UploadFile(file=io.BytesIO(data), filename="clip.mp4", size=len(data))
    return asyncio.run(ffmpeg._spool_upload(upload, ".mp4"))


def test_an_upload_under_the_limit_lands_on_disk(ffmpeg, tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    path = _spool(ffmpeg, b"x" * 4096)
    try:
        assert Path(path).read_bytes() == b"x" * 4096
    finally:
        os.unlink(path)


def test_an_oversized_upload_is_refused_with_413(ffmpeg, tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(ffmpeg, "_MAX_UPLOAD_BYTES", 1024)
    with pytest.raises(HTTPException) as excinfo:
        _spool(ffmpeg, b"x" * 8192)
    assert excinfo.value.status_code == 413


def test_a_refused_upload_leaves_no_temp_file(ffmpeg, tmp_path, monkeypatch):
    """`delete=False` means the file outlives its handle. Nothing else knows its
    name at that point, so if `_spool_upload` does not remove it, nothing will."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(ffmpeg, "_MAX_UPLOAD_BYTES", 1024)
    with pytest.raises(HTTPException):
        _spool(ffmpeg, b"x" * 8192)
    assert list(tmp_path.iterdir()) == []


def test_the_limit_is_enforced_while_reading_not_after(ffmpeg, tmp_path, monkeypatch):
    """The point of streaming: the whole upload must never be resident at once.

    A single `read()` with no size argument would defeat the limit entirely --
    the bytes would already be in memory by the time the counter saw them -- so
    this asserts the read is chunked, and that every chunk is bounded.
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(ffmpeg, "_UPLOAD_CHUNK", 1024)
    sizes = []

    class _CountingUpload(UploadFile):
        async def read(self, size: int = -1) -> bytes:  # type: ignore[override]
            sizes.append(size)
            return await super().read(size)

    upload = _CountingUpload(file=io.BytesIO(b"x" * 5000), filename="c.mp4", size=5000)
    path = asyncio.run(ffmpeg._spool_upload(upload, ".mp4"))
    try:
        assert len(sizes) > 1, "the upload was read in one call; the limit cannot bind"
        assert set(sizes) == {1024}, f"unbounded read among {sizes}"
    finally:
        os.unlink(path)


# --- the header check -----------------------------------------------------------


def test_an_oversized_body_is_refused_before_it_is_read(client, ffmpeg, tmp_path, monkeypatch):
    """413 from the middleware, and the endpoint never runs -- no temp file, no
    ffmpeg child. A small limit rather than a large body: the assertion is about
    where the refusal happens, not about moving half a gigabyte through a test."""
    monkeypatch.setattr(ffmpeg, "_MAX_BODY_BYTES", 128)
    calls: list[list[str]] = []
    monkeypatch.setattr(ffmpeg, "_run_cmd", _fake_run(calls))
    before = set(tmp_path.iterdir())
    response = _post(client, b"x" * 4096)
    assert response.status_code == 413
    assert "limit" in response.json()["detail"]
    assert calls == [], "the transcode ran for a request the middleware refused"
    assert set(tmp_path.iterdir()) == before


def test_a_body_within_the_header_limit_is_let_through(client, ffmpeg, tmp_path):
    assert _post(client, b"x" * 4096).status_code == 200


# --- no temp file survives any path --------------------------------------------


def test_a_completed_request_leaves_no_input_temp_file(client, ffmpeg, tmp_path):
    response = _post(client, b"x" * 4096)
    assert response.status_code == 200
    # The input spool is unlinked in the endpoint's finally; the output file is
    # deliberately kept for the caller, which is why it is the one file left.
    remaining = list(tmp_path.iterdir())
    assert len(remaining) == 1, f"expected only the kept output file, found {remaining}"
    assert remaining[0].name == response.json()["output_path"].split("/")[-1]


def test_the_output_hash_is_of_the_written_output(client, ffmpeg, tmp_path):
    """The hash covers the real output file -- the stub transcode writes nothing,
    so the expected digest is the empty-file one."""
    response = _post(client, b"x" * 4096)
    assert response.json()["result_hash"] == EMPTY_SHA256


# --- the shape of the fix, which a behavioural test cannot pin -----------------


def test_no_path_reads_a_file_whole_again(ffmpeg):
    """A bare `.read()` with no size argument is the bug this file exists for.

    Every guard above still passes if someone reinstates one -- the limits would
    just be applied to something already fully resident. That goes for the upload
    *and* for the output read-back that feeds the result hash. So this checks the
    source: an unbounded `.read()` anywhere in the module is what must not return.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE))
    bare = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "read"
        and not node.args
        and not node.keywords
    ]
    assert not bare, f"unbounded .read() at line(s) {[n.lineno for n in bare]}"
