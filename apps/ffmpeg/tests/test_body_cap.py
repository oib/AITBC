"""MEDIA-UPLOAD-1 (#1671): the body-cap middleware refuses chunked uploads.

``_reject_oversized_body`` only saw ``Content-Length``; a chunked transfer
has none, so ``request.form()`` spooled an unbounded body to PrivateTmp
before ``_spool_upload``'s counter ran. Chunked is now refused with 411 —
every accepted upload declares its length up front.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("aitbc_ffmpeg_main_bodycap", Path(__file__).resolve().parents[1] / "main.py")
ffmpeg_main = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ffmpeg_main)


class _Req:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


async def _call_next(request):
    return "passed"


def _run(headers: dict[str, str]):
    return asyncio.run(ffmpeg_main._reject_oversized_body(_Req(headers), _call_next))


def test_chunked_transfer_encoding_rejected() -> None:
    resp = _run({"transfer-encoding": "chunked"})
    assert resp.status_code == 411


def test_chunked_among_other_codings_rejected() -> None:
    resp = _run({"transfer-encoding": "gzip, chunked"})
    assert resp.status_code == 411


def test_oversized_content_length_still_413() -> None:
    resp = _run({"content-length": str(ffmpeg_main._MAX_BODY_BYTES + 1)})
    assert resp.status_code == 413


def test_small_content_length_passes() -> None:
    assert _run({"content-length": "1024"}) == "passed"


def test_no_length_headers_passes() -> None:
    assert _run({}) == "passed"
