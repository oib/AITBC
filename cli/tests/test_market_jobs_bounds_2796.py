"""AUDIT-EDGE-CLI-MARKET-UNBOUNDED (#2796): market job whisper/ffmpeg/ollama
paths buffered whole input files and parsed unbounded provider responses.
Now: input files are size-checked against the services' own upload limits
before escrow, and response bodies are read under a 64 MiB cap.
"""

import io
import json

import pytest
from click import Abort

from aitbc_cli.commands.market import jobs


class _FakeResp:
    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def read(self, amt: int | None = None) -> bytes:
        return self._buf.read() if amt is None else self._buf.read(amt)


def test_response_json_capped_accepts_normal():
    resp = _FakeResp(json.dumps({"text": "hi"}).encode())
    assert jobs._read_response_json_capped(resp, "Whisper") == {"text": "hi"}


def test_response_json_capped_refuses_oversized():
    big = b"x" * (jobs._PROVIDER_RESPONSE_MAX_BYTES + 1)
    resp = _FakeResp(b'{"pad": "' + big + b'"}')
    with pytest.raises(ValueError, match="exceeds"):
        jobs._read_response_json_capped(resp, "FFmpeg")


def test_response_json_capped_boundary_exact():
    # exactly at the cap parses; one byte over refuses
    payload = b'{"a": "' + b"x" * (jobs._PROVIDER_RESPONSE_MAX_BYTES - 10) + b'"}'
    assert len(payload) <= jobs._PROVIDER_RESPONSE_MAX_BYTES
    assert isinstance(jobs._read_response_json_capped(_FakeResp(payload), "Ollama"), dict)


def test_checked_input_size_refuses_over_limit(tmp_path):
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * 16)
    with pytest.raises(Abort):
        jobs._checked_input_size(str(f), 8, "Whisper")


def test_checked_input_size_allows_under_limit(tmp_path):
    f = tmp_path / "small.bin"
    f.write_bytes(b"x" * 4)
    jobs._checked_input_size(str(f), 8, "FFmpeg")  # no raise


def test_upload_caps_match_service_defaults():
    # apps/whisper WHISPER_MAX_UPLOAD_MB default 100, apps/ffmpeg 512
    assert jobs._WHISPER_UPLOAD_MAX_BYTES == 100 * 1024 * 1024
    assert jobs._FFMPEG_UPLOAD_MAX_BYTES == 512 * 1024 * 1024
