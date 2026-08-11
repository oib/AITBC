"""Alembic environment for the Edge API service.

V23-47: this app had no migration infrastructure. Its models declare money as ``Decimal``
with ``max_digits=20, decimal_places=8``, but ``init_db`` only calls
``SQLModel.metadata.create_all``, which adds *missing tables* and never alters existing ones
— so the deployed money columns were still ``FLOAT`` while the models said
``Numeric(20, 8)``.

The service runs on an async driver. Migrations deliberately use the **sync** driver against
the same database: batch-mode ALTER, which SQLite requires for a type change, is a
synchronous operation.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Importing the schema modules is what registers the tables on SQLModel.metadata.
from aitbc_edge.schemas import database, gpu, island, metrics, serve  # noqa: E402,F401
from sqlmodel import SQLModel  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _sync_database_url() -> str:
    """The service's own database URL, on a synchronous driver.

    Resolved through ``aitbc_edge.config.settings`` — the same source
    ``aitbc_edge.storage`` uses — so migrations and the running service cannot end up
    pointed at different databases. ``storage`` itself is not imported because it builds an
    async engine at module scope.

    **This does not read ``DATABASE_URL``.** The URL comes from the edge settings object
    (``EdgeSettings.database``, an ``aitbc_shared.DatabaseConfig``), so exporting
    ``DATABASE_URL=sqlite:///somewhere-else.db`` before ``alembic upgrade`` changes nothing
    and the migration runs against the deployed database.

    The variable that does work is **``URL``** -- ``DatabaseConfig`` is a ``BaseSettings``
    with no ``env_prefix``, so its ``url`` field maps to the bare name. To run against a copy::

        URL=sqlite:///path/to/copy.db alembic upgrade head

    and check the target line this function prints before it does anything.
    """
    from aitbc_edge.config import settings

    url: str = settings.database.effective_url
    return url.replace("+aiosqlite", "").replace("+asyncpg", "")


def _resolved_target() -> str:
    """The URL, echoed to stderr before anything runs.

    A migration should never be the first thing that tells you which database it chose.
    """
    url = _sync_database_url()
    print(f"alembic: target database -> {url}", file=sys.stderr)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_resolved_target(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _resolved_target()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
