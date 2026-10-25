"""Alembic environment for trading service (v0.8.0)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool


# Importing the models is what registers them on trading_metadata.
from trading_service.domain import exchange_payment as _exchange_payment  # noqa: F401
from trading_service.domain import inter_chain as _inter_chain  # noqa: F401
from trading_service.domain import trading as _trading  # noqa: F401
from trading_service.domain.base import trading_metadata

config = context.config


def _sync_database_url() -> str:
    """The same resolver storage.py uses, in the sync-driver form Alembic needs.

    Kept in ``aitbc.database.target`` so the app and the migrator can never
    disagree (PG-TARGET-1).
    """
    from aitbc.constants import DATA_DIR
    from aitbc.database.target import resolve_service_database_url

    return resolve_service_database_url(
        default_url=f"sqlite+aiosqlite:///{DATA_DIR}/data/trading_service.db",
        default_db_name="aitbc_trading",
        async_=False,
    )


# Override the hardcoded URL in alembic.ini with the env-var-derived one
config.set_main_option("sqlalchemy.url", _sync_database_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

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
