from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from poolhub.models import Base
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_postgres_dsn() -> str:
    """Get the async Postgres DSN from env var, falling back to the default.

    Reads POOLHUB_POSTGRES_DSN directly instead of importing poolhub.settings,
    which requires coordinator_shared_secret to be set — not needed for
    migrations.
    """
    return os.getenv(
        "POOLHUB_POSTGRES_DSN",
        "postgresql+asyncpg://poolhub:poolhub@127.0.0.1:5432/aitbc",
    )


def _configure_context(connection=None, *, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        dialect_opts={"paramstyle": "named"},
    )


def run_migrations_offline() -> None:
    _configure_context(url=_get_postgres_dsn())
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(_get_postgres_dsn(), pool_pre_ping=True)
    async with connectable.connect() as connection:
        await connection.run_sync(_configure_context)
        await connection.run_sync(lambda conn: context.run_migrations())
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
