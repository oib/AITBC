"""
Database utility functions for AITBC applications.
"""

import sqlite3
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import DatabaseError
from .connection import DatabaseConnection

logger = get_logger(__name__)


def get_database_connection(
    db_path: Path,
    timeout: int = 30
) -> DatabaseConnection:
    """
    Get a database connection for a given path.

    Args:
        db_path: Path to database file
        timeout: Connection timeout in seconds

    Returns:
        DatabaseConnection instance
    """
    return DatabaseConnection(db_path, timeout)


def ensure_database(db_path: Path) -> Path:
    """
    Ensure database file and parent directory exist.

    Args:
        db_path: Path to database file

    Returns:
        Database path
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def vacuum_database(db_path: Path) -> None:
    """
    Vacuum database to optimize storage.

    Args:
        db_path: Path to database file

    Raises:
        DatabaseError: If vacuum fails
    """
    try:
        with DatabaseConnection(db_path) as db:
            db.execute("VACUUM")
    except Exception as e:
        raise DatabaseError(f"Database vacuum failed: {e}") from e


def get_table_info(db_path: Path, table_name: str) -> list[dict[str, Any]]:
    """
    Get information about a table's columns.

    Args:
        db_path: Path to database file
        table_name: Name of table

    Returns:
        List of column information dictionaries
    """
    with DatabaseConnection(db_path) as db:
        return db.fetch_all(f"PRAGMA table_info({table_name})")


def table_exists(db_path: Path, table_name: str) -> bool:
    """
    Check if a table exists in the database.

    Args:
        db_path: Path to database file
        table_name: Name of table

    Returns:
        True if table exists
    """
    with DatabaseConnection(db_path) as db:
        result = db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return result is not None
