"""#1801: connect failures carry a bounded errno class.

The drill-mesh Errno-22 storms were undiagnosable from logs because every
connect_failed event reported the same shape. The backend now classifies
the OSError errno into a bounded label (EINVAL/ECONNREFUSED/…) on both the
metric and the event, so the next storm is attributable.
"""

from __future__ import annotations

import errno

import pytest
import websockets
from aitbc_chain.gossip.backends import websocket as wsmod
from aitbc_chain.gossip.backends.websocket import (
    WebsocketGossipBackend,
    _connect_error_class,
)


def test_connect_error_class_maps_known_errnos() -> None:
    assert _connect_error_class(OSError(errno.EINVAL, "Invalid argument")) == "EINVAL"
    assert _connect_error_class(OSError(errno.ECONNREFUSED, "refused")) == "ECONNREFUSED"
    assert _connect_error_class(OSError(errno.ETIMEDOUT, "timed out")) == "ETIMEDOUT"


def test_connect_error_class_bounds_unknown_and_missing() -> None:
    assert _connect_error_class(OSError(999999, "weird")) == "other"
    assert _connect_error_class(RuntimeError("no errno")) == "none"
    assert _connect_error_class(OSError("plain string")) == "none"


@pytest.mark.asyncio
async def test_connect_failed_event_carries_errno_class(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict] = []
    monkeypatch.setattr(wsmod, "gossip_event", lambda name, **kw: events.append({"name": name, **kw}))

    async def _boom(*a, **k):
        raise OSError(errno.EINVAL, "Invalid argument")

    monkeypatch.setattr(websockets, "connect", _boom)

    backend = WebsocketGossipBackend("ws://10.0.0.1:8202/rpc/gossip/ws")
    with pytest.raises(RuntimeError, match="Failed to connect"):
        await backend._ensure_connection_unsafe("transactions")

    failed = [e for e in events if e["name"] == "connect_failed"]
    assert failed and failed[0]["error_code"] == "EINVAL"
    assert "Invalid argument" in failed[0]["error"]
