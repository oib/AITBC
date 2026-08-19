"""
Database session management for GPU service
"""

import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR

# Importing the models is what puts them on `gpu_metadata`; create_all builds nothing
# otherwise. This service's tables live there rather than on the global SQLModel registry --
# see domain/base.py (V23-72).
from .domain import gpu_marketplace as _models  # noqa: F401
from .domain.base import gpu_metadata

logger = get_logger(__name__)

# Database URL from environment variable or default
DEFAULT_DB = f"sqlite+aiosqlite:///{DATA_DIR}/data/gpu_service.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB)

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=False)


def _format_default_value(value: object) -> str | None:
    """Render a column default value as an SQL literal, or None if it cannot be rendered."""
    if value is None:
        return "NULL"
    if isinstance(value, Callable):  # type: ignore[arg-type]
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


def _ensure_all_columns_sync(conn) -> None:
    """Add any columns that exist in the SQLAlchemy model but are missing from the live DB.

    ``create_all`` only creates missing tables; it does not alter existing tables. This
    function fills the gap by adding missing columns with the same type and a default value
    when one is available, which is what SQLite requires for existing rows.
    """
    inspector = inspect(conn)
    dialect = conn.dialect

    for table in gpu_metadata.sorted_tables:
        if table.name not in inspector.get_table_names():
            continue

        existing_column_names = {col["name"] for col in inspector.get_columns(table.name)}

        for col in table.columns:
            if col.name in existing_column_names:
                continue

            type_str = dialect.type_compiler.process(col.type)
            parts = [f"{col.name} {type_str}"]

            default_literal: str | None = None
            if col.default is not None and col.default.arg is not None:
                # Some defaults are callables (e.g. datetime.now, list). Only literals can be
                # used in an ALTER TABLE ADD COLUMN statement in SQLite.
                default_literal = _format_default_value(col.default.arg)
            elif col.server_default is not None:
                default_literal = str(col.server_default.arg) if col.server_default.arg is not None else None

            if default_literal is not None:
                parts.append(f"DEFAULT {default_literal}")

            # SQLite requires a default for existing rows when adding a NOT NULL column.
            if col.nullable is False and default_literal is not None and default_literal != "NULL":
                parts.append("NOT NULL")

            try:
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {' '.join(parts)}"))
                logger.info("Added missing column %s.%s", table.name, col.name)
            except Exception as e:
                logger.warning("Could not add column %s.%s: %s", table.name, col.name, e)


async def init_db() -> None:
    """Initialize database tables and ensure existing tables match the current model."""

    async with engine.begin() as conn:
        await conn.run_sync(gpu_metadata.create_all)
        await conn.run_sync(_ensure_all_columns_sync)

    logger.info("GPU service database initialized")


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    async with AsyncSession(engine) as session:
        yield session
