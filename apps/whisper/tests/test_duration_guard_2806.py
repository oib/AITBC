"""AUDIT-EDGE pin for the whisper duration gate.

#2806: a container that opens but reports no duration (ffprobe absent or
equally silent) used to decode unbounded inside an unkillable thread,
wedging the single-slot service. Unknown duration now fails closed (415).
"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as whisper_main  # noqa: E402


def test_undeterminable_duration_fails_closed(monkeypatch, tmp_path) -> None:
    """#2806: probe returning None (no container.duration, no ffprobe) must
    refuse the job instead of starting an unbounded decode."""
    monkeypatch.setattr(whisper_main, "_model", object())
    monkeypatch.setattr(whisper_main, "_probe_duration", lambda p: None)
    monkeypatch.setattr(whisper_main, "_inflight", 0)
    f = tmp_path / "mystery.bin"
    f.write_bytes(b"not audio")

    class _Upload:
        filename = "mystery.bin"

        async def read(self, size: int = -1):
            return b""

    class _Req:
        headers = {}

    with pytest.raises(HTTPException) as ei:
        asyncio.run(whisper_main.transcribe(_Req(), _Upload(), None, "transcribe", 5))
    assert ei.value.status_code == 415
