"""Client-side bounds on bulk /rpc/blocks-range fetch (#1594)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from aitbc_chain.config import settings
from aitbc_chain.sync import ChainSync


class _RecordingStream:
    def __init__(self, payload: Any, calls: list[tuple[str, Any]]):
        self._body = json.dumps(payload).encode()
        self._calls = calls
        self._url = ""

    async def __aenter__(self) -> _RecordingStream:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self):
        yield self._body


class _RecordingClient:
    def __init__(self):
        self.calls: list[tuple[str, Any]] = []

    def stream(self, method: str, url: str, params: Any = None) -> _RecordingStream:
        self.calls.append((url, params))
        return _RecordingStream({"success": True, "blocks": [{"height": params["start"]}]}, self.calls)


@pytest.mark.asyncio
async def test_fetch_blocks_range_clamps_span_before_request(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "blocks_range_max_span", 3)
    sync = ChainSync(lambda: (_ for _ in ()).throw(RuntimeError("unused")), chain_id="c", validate_signatures=False)
    client = _RecordingClient()
    sync._client = client  # type: ignore[assignment]
    blocks = await sync.fetch_blocks_range(10, 99, "http://peer")
    assert len(blocks) == 1
    assert client.calls[0][1]["start"] == 10
    assert client.calls[0][1]["end"] == 12


@pytest.mark.asyncio
async def test_fetch_blocks_range_oversized_body_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "sync_blocks_range_response_max_bytes", 8)

    class _HugeStream:
        async def __aenter__(self) -> _HugeStream:
            return self

        async def __aexit__(self, *args: Any) -> bool:
            return False

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"x" * 64

    class _HugeClient:
        def stream(self, method: str, url: str, params: Any = None) -> _HugeStream:
            return _HugeStream()

    sync = ChainSync(lambda: (_ for _ in ()).throw(RuntimeError("unused")), chain_id="c", validate_signatures=False)
    sync._client = _HugeClient()  # type: ignore[assignment]
    assert await sync.fetch_blocks_range(0, 0, "http://peer") == []
