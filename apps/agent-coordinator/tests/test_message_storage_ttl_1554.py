"""#1554: the SQLite message fallback must honour MESSAGE_TTL_SECONDS.

The Redis path expires message hashes after 7 days; the SQLite fallback kept
every row forever whenever Redis was down. ``_sqlite_store`` now purges rows
whose ``timestamp`` is older than the TTL before inserting.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")
pytest.importorskip("aiosqlite", reason="aiosqlite not installed")

from agent_app.storage.message_storage import MESSAGE_TTL_SECONDS, MessageStorage  # noqa: E402


@pytest.fixture
async def sqlite_storage(tmp_path):
    storage = MessageStorage(redis_url="redis://localhost:6379/0", database_url=f"sqlite:///{tmp_path}/messages.db")
    storage.redis = None
    await storage.start()
    assert storage.sqlite_conn is not None
    yield storage
    await storage.stop()


@pytest.mark.asyncio
async def test_store_purges_rows_past_ttl(sqlite_storage):
    # Seed one fresh and one expired row directly.
    await sqlite_storage.sqlite_conn.execute(
        "INSERT INTO messages (message_id, data, sender, receiver, timestamp, status) VALUES (?, ?, ?, ?, ?, ?)",
        ("fresh-1", "{}", "a", "b", time.time(), "pending"),
    )
    await sqlite_storage.sqlite_conn.execute(
        "INSERT INTO messages (message_id, data, sender, receiver, timestamp, status) VALUES (?, ?, ?, ?, ?, ?)",
        ("stale-1", "{}", "a", "b", time.time() - MESSAGE_TTL_SECONDS - 60, "pending"),
    )
    await sqlite_storage.sqlite_conn.commit()

    # Any store triggers the purge.
    await sqlite_storage._sqlite_store("new-1", {"message_id": "new-1", "sender": "a", "recipient": "b"})

    cursor = await sqlite_storage.sqlite_conn.execute("SELECT message_id FROM messages")
    ids = {row[0] for row in await cursor.fetchall()}
    assert "stale-1" not in ids
    assert {"fresh-1", "new-1"} <= ids


@pytest.mark.asyncio
async def test_recent_rows_survive_purge(sqlite_storage):
    await sqlite_storage._sqlite_store("m-1", {"message_id": "m-1", "sender": "a", "recipient": "b"})
    cursor = await sqlite_storage.sqlite_conn.execute("SELECT COUNT(*) FROM messages")
    row = await cursor.fetchone()
    assert row is not None and row[0] == 1
