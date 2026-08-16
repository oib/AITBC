from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from aitbc_chain import database  # noqa: F401  -- imports every model, registering the tables
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from alembic import context
from sqlalchemy import engine_from_config, pool

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Ensure the database path exists and propagate URL to Alembic config.
#
# DATABASE_URL / SQLITE_URL override the configured path so CI and local tests can target
# a temp database -- the same escape hatch coordinator-api's env.py has had. Without it
# there is no way to run a migration except against the real chain database, and the
# obvious way to test one (export DATABASE_URL, run `alembic upgrade`) silently ignores
# the variable and writes to settings.db_path instead.
_db_url = os.environ.get("DATABASE_URL") or os.environ.get("SQLITE_URL")
if not _db_url:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    _db_url = f"sqlite:///{settings.db_path}"
config.set_main_option("sqlalchemy.url", _db_url)

# V23-49: echo the target, because the default is NOT the database the node writes to.
#
# `settings.db_path` is /var/lib/aitbc/data/chain.db. A running node writes to a *per-island*
# file -- /var/lib/aitbc/data/<island>/chain.db -- so a bare `alembic upgrade head` migrates
# an empty database, records success, and leaves the real one untouched. That is exactly what
# had happened: the default target sat at head with 0 rows while the live island database,
# 93k blocks and the tables the migration was written for, had no alembic_version table at
# all. There is no single correct default here -- the island is chosen at runtime -- so the
# target is printed instead of guessed. Pass DATABASE_URL to name the island explicitly.
print(f"alembic: target database -> {_db_url}", file=sys.stderr)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This package's tables are on their own MetaData, not the global SQLModel one, because
# apps/coordinator-api defines a Transaction, Block and Receipt of its own -- see
# aitbc_chain/metadata.py (V23-74). Autogenerate must read the same registry create_all
# writes, or it would compare the chain database against an empty model set and emit a
# migration dropping every table.
target_metadata = chain_metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
