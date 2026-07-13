"""Alembic environment for AITBC Coordinator API.

Resolves the database URL from the application's ``Settings`` — the same source
the running service uses — so migrations always target the correct database
without hardcoding a URL in ``alembic.ini``.

Usage::

    cd apps/coordinator-api
    alembic stamp <revision>      # mark current DB state
    alembic upgrade <revision>    # apply migrations up to <revision>
    alembic upgrade head          # apply all pending migrations
    alembic revision -m "..."     # autogenerate a new migration
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import the app settings so the DB URL matches the running service exactly.
from coordinator_api.config import settings as app_settings

# Import SQLModel metadata (populated when domain models are imported).
# ponytail: target_metadata is only needed for autogenerate; stamp/upgrade
# run hand-written migrations and do not require it. We import it lazily so
# that a missing/renamed model module never blocks running migrations.
try:
    from sqlmodel import SQLModel

    target_metadata = SQLModel.metadata
except Exception:  # pragma: no cover - defensive; metadata is optional for upgrade
    target_metadata = None

config = context.config

# Resolve the database URL from the app settings (honours .env / ENVIRONMENT).
# Allow a direct DATABASE_URL override so CI and local tests can target a temp DB.
config.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL", app_settings.database.effective_url))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to the DB and execute)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
