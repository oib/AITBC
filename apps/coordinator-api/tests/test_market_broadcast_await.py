"""#749-class regression: ``_broadcast_data_point`` must await the websocket
send — pre-fix it called ``websocket.send_text(...)``, a method that does
not exist on ``websockets.asyncio.server.ServerConnection`` (pinned 14.2),
so every broadcast raised AttributeError into the generic except and the
client was wrongly dropped: the stream silently never worked.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from types import SimpleNamespace

import pytest
from coordinator_api.contexts.trading.services.market_data_collector import MarketDataCollector


class _Source(Enum):
    X = "x"


class _FakeWs:
    def __init__(self):
        self.sent: list[str] = []

    async def send(self, message):
        self.sent.append(message)


def _point():
    return SimpleNamespace(
        source=_Source.X,
        resource_id="r1",
        resource_type="gpu",
        region="eu",
        timestamp=datetime.now(UTC),
        value=1.0,
        metadata={},
    )


@pytest.mark.asyncio
async def test_broadcast_sends_and_keeps_client():
    ws = _FakeWs()
    collector = SimpleNamespace(websocket_connections={"c1": ws})
    await MarketDataCollector._broadcast_data_point(collector, _point())
    assert len(ws.sent) == 1, "broadcast send coroutine was never awaited"
    assert json.loads(ws.sent[0])["resource_id"] == "r1"
    assert "c1" in collector.websocket_connections, "client wrongly dropped by the send error path"


@pytest.mark.asyncio
async def test_broadcast_drops_closed_client():
    class _Closed:
        async def send(self, message):
            raise RuntimeError("gone")

    collector = SimpleNamespace(websocket_connections={"c1": _Closed()})
    await MarketDataCollector._broadcast_data_point(collector, _point())
    assert "c1" not in collector.websocket_connections
