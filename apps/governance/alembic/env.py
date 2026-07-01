import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add src directory to sys.path for module imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import SQLModel metadata
# Import all models to ensure they're registered with SQLModel.metadata
from sqlmodel import SQLModel

# this is the Alembic Config object
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
        name = os.getenv("DB_NAME", "aitbc_governance")
        user = os.getenv("DB_USER", "aitbc")
        password = os.getenv("DB_PASS", "")
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////var/lib/aitbc/data/governance_service.db")
    # Convert async driver to sync for Alembic
    return url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")


# Override the hardcoded URL in alembic.ini with the env-var-derived one
config.set_main_option("sqlalchemy.url", _sync_database_url())

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
target_metadata = SQLModel.metadata

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
