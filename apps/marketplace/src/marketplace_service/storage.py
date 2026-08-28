"""
Database session management for Marketplace service
"""

import json
import os
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any

from aitbc_shared import MarketplaceOffer
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR

# Importing the models is what puts them on `marketplace_metadata`; create_all builds nothing
# otherwise. This service's own tables live there rather than on the global SQLModel registry --
# see domain/base.py (V23-72).
from .domain import global_marketplace as _global_models  # noqa: F401
from .domain import marketplace as _models  # noqa: F401
from .domain.base import marketplace_metadata

logger = get_logger(__name__)
DEFAULT_DB = f"sqlite+aiosqlite:///{DATA_DIR}/data/marketplace_service.db"
DATABASE_URL = os.getenv("MARKETPLACE_DATABASE_URL", os.getenv("DATABASE_URL", DEFAULT_DB))
engine = create_async_engine(DATABASE_URL, echo=False)
logger.info("Storage module loaded: engine=%s, DATABASE_URL=%s", engine, os.getenv("MARKETPLACE_DATABASE_URL", "not set"))


def _format_default_value(value: Any) -> str | None:
    """Convert a Python default value into an SQL literal for ALTER TABLE."""
    if value is None:
        return None
    if isinstance(value, int | float | bool):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    if isinstance(value, list | dict):
        return f"'{json.dumps(value).replace(chr(39), chr(39) + chr(39))}'"
    if isinstance(value, datetime):
        return f"'{value.isoformat()}'"
    return None


def _ensure_table_columns_sync(conn, table) -> None:
    """Add columns that exist in the model but are missing from the live table."""
    inspector = inspect(conn)
    dialect = conn.dialect

    if table.name not in inspector.get_table_names():
        return

    existing_column_names = {col["name"] for col in inspector.get_columns(table.name)}

    for col in table.columns:
        if col.name in existing_column_names:
            continue

        type_str = dialect.type_compiler.process(col.type)
        parts = [f"{col.name} {type_str}"]

        default_literal: str | None = None
        if col.default is not None and col.default.arg is not None:
            default_literal = _format_default_value(col.default.arg)
        elif col.server_default is not None and col.server_default.arg is not None:
            default_literal = str(col.server_default.arg)

        if default_literal is not None:
            parts.append(f"DEFAULT {default_literal}")

        if col.nullable is False and default_literal is not None and default_literal != "NULL":
            parts.append("NOT NULL")

        try:
            conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {' '.join(parts)}"))
            logger.info("Added missing column %s.%s", table.name, col.name)
        except Exception as e:
            logger.warning("Could not add column %s.%s: %s", table.name, col.name, e)


async def init_db() -> None:
    """Initialize database tables.

    Two registries, deliberately. This service's own twelve tables are on
    `marketplace_metadata`. `MarketplaceOffer` is not one of ours -- it is a single class in
    `packages/aitbc-shared` that we share with coordinator-api, so it stays on the global
    SQLModel registry and is named here explicitly.

    Naming it explicitly is the point of the change. `create_all` over the whole global
    registry also built `job_payments`, `marketplace_bid` and `payment_escrows`, which this
    service has no model for and never reads or writes; they arrived only because something in
    the import graph had touched them. `create_all` never drops, so databases that already have
    those three keep them (V23-72).
    """
    # Straight off the class, not looked up in `SQLModel.metadata`: two test conftests mutate
    # that registry -- one clears it, the other removes every table it does not own -- and a
    # name lookup then raises KeyError for a table that is perfectly intact. The `Table` object
    # the class holds survives being unregistered. The ignore is because SQLModel declares
    # `__tablename__` but not `__table__`, which SQLAlchemy adds when the class is mapped.
    shared = MarketplaceOffer.__table__  # type: ignore[attr-defined]
    async with engine.begin() as conn:
        await conn.run_sync(marketplace_metadata.create_all)
        await conn.run_sync(lambda sync_conn: shared.create(sync_conn, checkfirst=True))
        for table in list(marketplace_metadata.sorted_tables) + [shared]:
            await conn.run_sync(lambda sync_conn, t=table: _ensure_table_columns_sync(sync_conn, t))
    logger.info("Marketplace service database initialized")


async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    try:
        logger.debug("Creating database session, engine=%s, id=%s", engine, id(engine))
        AsyncSessionClass = AsyncSession
        logger.debug("AsyncSession class: %s, callable: %s", AsyncSessionClass, callable(AsyncSessionClass))
        session = AsyncSessionClass(engine, expire_on_commit=False)
        logger.debug("Session created: %s", session)
        async with session:
            logger.debug("Database session yielded")
            yield session
            logger.debug("Database session closed")
    except Exception as e:
        logger.error("Error in get_session: %s: %s", type(e).__name__, str(e))
        logger.error("Traceback: %s", traceback.format_exc())
        raise


@asynccontextmanager
async def get_session_context() -> AsyncIterator[AsyncSession]:
    """Get database session as context manager"""
    async with AsyncSession(engine) as session:
        yield session
