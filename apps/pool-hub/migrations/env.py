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
from sqlalchemy.engine.url import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _get_postgres_dsn() -> str:
    """Get the async Postgres DSN from env var.

    DATABASE_URL / SQLITE_URL / POOLHUB_POSTGRES_DSN, in that order. Settings is
    not imported: it requires coordinator_shared_secret, which migrations do
    not. A bare invocation must NOT guess: the old hard-coded
    ``poolhub:poolhub@…/aitbc`` default could connect, migrate, and stamp the
    wrong database with no error on any host where those credentials exist.
    """
    dsn = os.getenv("DATABASE_URL") or os.getenv("SQLITE_URL") or os.getenv("POOLHUB_POSTGRES_DSN")
    if not dsn:
        raise RuntimeError(
            "no database DSN configured: set DATABASE_URL or "
            "POOLHUB_POSTGRES_DSN (source /etc/aitbc/aitbc-pool-hub.env)"
        )
    return dsn


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
    # Render with the password hidden — the plain DSN would leak credentials
    # into stderr, the journal, and any session transcript that runs alembic.
    safe_dsn = make_url(_get_postgres_dsn()).render_as_string(hide_password=True)
    print(f"alembic: target database -> {safe_dsn}", file=sys.stderr)
    connectable = create_async_engine(_get_postgres_dsn(), pool_pre_ping=True)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
