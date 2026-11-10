"""AUDIT-RETRY (#1576): MarketDataCollector.initialize() must be idempotent.

Each call spawns one loop per DataSource plus aggregation/cleanup loops and
a WebSocket server; racing callers through get_market_collector must not
multiply them.
"""

from __future__ import annotations

import pytest

import coordinator_api.contexts.trading.services.market_data_collector as mdc
from coordinator_api.contexts.trading.services.market_data_collector import (
    DataSource,
    MarketDataCollector,
)


@pytest.fixture
def collector(monkeypatch: pytest.MonkeyPatch) -> tuple[MarketDataCollector, list[str]]:
    spawned: list[str] = []

    def fake_create_task(coro, name: str | None = None):  # noqa: ANN001, ANN202
        spawned.append(name or "?")
        coro.close()
        return None

    async def fake_ws_server(self) -> None:  # noqa: ANN001
        return None

    monkeypatch.setattr(mdc, "create_task_with_logging", fake_create_task)
    monkeypatch.setattr(MarketDataCollector, "_start_websocket_server", fake_ws_server)
    return MarketDataCollector({}), spawned


async def test_initialize_spawns_loops_once(collector) -> None:
    col, spawned = collector
    await col.initialize()
    expected = len(DataSource) + 2  # per-source collectors + aggregate + cleanup
    assert len(spawned) == expected


async def test_initialize_is_idempotent(collector) -> None:
    col, spawned = collector
    await col.initialize()
    await col.initialize()
    await col.initialize()
    expected = len(DataSource) + 2
    assert len(spawned) == expected
    assert col._initialized is True
