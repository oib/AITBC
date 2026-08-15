"""Alembic environment for the GPU service.

V23-47: this app had no migration infrastructure at all. Its models declare money as
``Decimal`` with ``max_digits=20, decimal_places=8``, but ``init_db`` only calls
``SQLModel.metadata.create_all``, which adds *missing tables* and never alters existing
ones — so the deployed ``gpu_registry.price_per_hour`` was still ``FLOAT`` with live rows in
it while the model said ``Numeric(20, 8)``.

The service runs on an async driver (``sqlite+aiosqlite``). Migrations deliberately use the
**sync** driver against the same database: batch-mode ALTER, which SQLite requires for a type
change, is a synchronous operation, and there is nothing to be gained from driving DDL
through an event loop.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gpu_service.domain import gpu_marketplace  # noqa: E402,F401  (registers the tables)
from gpu_service.domain.base import gpu_metadata  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This service's tables are on their own MetaData, not the global SQLModel one, because
# apps/coordinator-api defines the same six table names -- see gpu_service/domain/base.py
# (V23-72). Autogenerate must read the same registry create_all writes, or it would compare
# this database against an empty model set and emit a migration dropping every table.
target_metadata = gpu_metadata


def _sync_database_url() -> str:
    """The service's own database URL, on a synchronous driver.

    Read from the same environment variable ``gpu_service.storage`` reads, so migrations and
    the running service cannot end up pointed at different files. Importing ``storage``
    directly would construct an async engine as a side effect, which is not wanted here.
    """
    import os

    from aitbc.constants import DATA_DIR

    url = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/data/gpu_service.db")
    return url.replace("+aiosqlite", "").replace("+asyncpg", "")


def _resolved_target() -> str:
    """The URL, echoed to stderr before anything runs.

    A migration should never be the first thing that tells you which database it chose.
    ``apps/edge``'s equivalent resolves through its settings object and ignores
    ``DATABASE_URL`` entirely -- the two apps answer this differently, which is exactly why
    both print it.
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
