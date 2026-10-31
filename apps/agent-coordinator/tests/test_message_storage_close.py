"""Refs #738 — MessageStorage.stop() must await sqlite_conn.close().

The aiosqlite connection's close() is a coroutine; calling it un-awaited
left the connection open and emitted "coroutine was never awaited"
RuntimeWarnings on every service restart.
"""

import warnings
from unittest.mock import AsyncMock

import pytest

from agent_app.storage.message_storage import MessageStorage


@pytest.mark.asyncio
async def test_stop_awaits_sqlite_close():
    storage = MessageStorage(redis_url="redis://localhost:6379/0")
    conn = AsyncMock()
    storage.sqlite_conn = conn
    storage.redis = None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        await storage.stop()

    conn.close.assert_awaited_once()
    assert not [w for w in caught if "never awaited" in str(w.message)], (
        f"un-awaited coroutine warnings: {[str(w.message) for w in caught]}"
    )
