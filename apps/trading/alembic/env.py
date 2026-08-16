"""Alembic environment for trading service (v0.8.0)."""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add src directory to sys.path for module imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Importing the models is what registers them on trading_metadata.
from trading_service.domain import inter_chain as _inter_chain  # noqa: F401
from trading_service.domain import trading as _trading  # noqa: F401
from trading_service.domain.base import trading_metadata

config = context.config


def _sync_database_url() -> str:
    """Build a sync DB URL from the same env vars as storage.py.

    storage.py uses async drivers (asyncpg/aiosqlite); Alembic uses sync
    drivers (psycopg2/sqlite). Convert the async URL to its sync equivalent.
    """
    db_type = os.getenv("DB_TYPE", "sqlite")
    if db_type == "postgresql":
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "aitbc_trading")
        user = os.getenv("DB_USER", "aitbc")
        password = os.getenv("DB_PASS", "")
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
    from aitbc.constants import DATA_DIR

    url = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR}/data/trading_service.db")
    # Convert async driver to sync for Alembic
    return url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")


# Override the hardcoded URL in alembic.ini with the env-var-derived one
config.set_main_option("sqlalchemy.url", _sync_database_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This service's tables are on their own MetaData, not the global SQLModel one, because
# apps/coordinator-api defines the same table names -- see trading_service/domain/base.py
# (V23-74). Autogenerate must read the same registry the migrations build, or it would
# compare this database against an empty model set and emit a migration dropping every
# table.
target_metadata = trading_metadata


def run_migrations_offline() -> None:
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
