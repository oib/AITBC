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
import re
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import the app settings so the DB URL matches the running service exactly.
from coordinator_api.config import settings as app_settings

# Import SQLModel metadata (populated when domain models are imported).
# Importing coordinator_api.main pulls in every router, which in turn imports
# all SQLModel subclasses, so SQLModel.metadata reflects the current schema.
# ponytail: target_metadata is only needed for autogenerate; stamp/upgrade
# run hand-written migrations and do not require it. We import it lazily so
# that a missing/renamed model module never blocks running migrations.
try:
    import coordinator_api.main  # noqa: F401 - imports routers to populate metadata
    from sqlmodel import SQLModel

    target_metadata = SQLModel.metadata
except Exception:  # pragma: no cover - defensive; metadata is optional for upgrade
    target_metadata = None

config = context.config

# Resolve the database URL from the app settings (honours .env / ENVIRONMENT).
# Allow DATABASE_URL or SQLITE_URL override so CI and local tests can target a temp DB.
_app_url = app_settings.database.effective_url
_override = os.environ.get("DATABASE_URL") or os.environ.get("SQLITE_URL")
_db_url = _override or _app_url


def _redact(url: str) -> str:
    """Hide the password in a DSN so it never reaches a log or a terminal scrollback."""
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", url)


if _override and _override != _app_url:
    # This override is why coordinator migrations went missing: the deployed env
    # file set DATABASE_URL to Postgres while the service itself ran on SQLite,
    # so `alembic upgrade` advanced a schema nothing reads and the live database
    # silently fell behind head. CI still needs the override, so keep it -- but
    # never let it be silent.
    print(
        "WARNING: DATABASE_URL/SQLITE_URL points somewhere the app does not read.\n"
        f"  migrating : {_redact(_override)}\n"
        f"  app reads : {_redact(_app_url)}\n"
        "  Unset the override to migrate the database the service actually uses.",
        file=sys.stderr,
    )
print(f"alembic: target database -> {_redact(_db_url)}", file=sys.stderr)
config.set_main_option("sqlalchemy.url", _db_url)

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
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
