from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# Add src directory to sys.path for module imports (matches governance/trading env.py)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from poolhub.models import Base  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_postgres_dsn() -> str:
    """Get the async Postgres DSN from env var, falling back to the default.

    DATABASE_URL / SQLITE_URL / POOLHUB_POSTGRES_DSN, in that order. The dummy
    ``user:pass@localhost`` in alembic.ini is never a target. Settings is not
    imported: it requires coordinator_shared_secret, which migrations do not.
    """
    return (
        os.getenv("DATABASE_URL")
        or os.getenv("SQLITE_URL")
        or os.getenv("POOLHUB_POSTGRES_DSN")
        or "postgresql+asyncpg://poolhub:poolhub@127.0.0.1:5432/aitbc"
    )


def _configure_context(connection=None, *, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        dialect_opts={"paramstyle": "named"},
    )


def do_run_migrations(connection) -> None:
    _configure_context(connection=connection)
    # Without begin_transaction, async stamp/upgrade run and roll back on close.
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    _configure_context(url=_get_postgres_dsn())
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    print(f"alembic: target database -> {_get_postgres_dsn()}", file=sys.stderr)
    connectable = create_async_engine(_get_postgres_dsn(), pool_pre_ping=True)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
