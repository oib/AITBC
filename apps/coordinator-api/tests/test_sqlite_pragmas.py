"""#1560: coordinator-api sqlite engines get WAL + busy_timeout pragmas."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine

from coordinator_api.sqlite_pragmas import install_sqlite_pragmas


def test_sync_engine_pragmas(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path}/sync.db")
    install_sqlite_pragmas(engine)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA synchronous").scalar() == 1
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
    engine.dispose()


async def test_async_engine_pragmas(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/async.db")
    install_sqlite_pragmas(engine)
    async with engine.connect() as conn:
        assert (await conn.exec_driver_sql("PRAGMA journal_mode")).scalar() == "wal"
        assert (await conn.exec_driver_sql("PRAGMA busy_timeout")).scalar() == 30000
    await engine.dispose()


def test_non_sqlite_engine_is_noop() -> None:
    engine = create_engine("postgresql://localhost/db")
    install_sqlite_pragmas(engine)  # must not raise or attach listeners
    engine.dispose()
