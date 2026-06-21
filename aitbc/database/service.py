"""
Database service layer for AITBC
Provides high-level database interaction services with connection pooling
"""

import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class DatabaseService(ABC):
    """Abstract base class for database service implementations"""

    @abstractmethod
    def execute_query(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute a SELECT query"""
        pass

    @abstractmethod
    def execute_update(self, query: str, params: tuple = ()) -> int:
        """Execute an INSERT/UPDATE/DELETE query"""
        pass

    @abstractmethod
    def execute_transaction(self, queries: list[tuple]) -> bool:
        """Execute multiple queries in a transaction"""
        pass


class SQLiteDatabaseService(DatabaseService):
    """SQLite database service with connection pooling"""

    def __init__(self, db_path: Path, pool_size: int = 5):
        """
        Initialize SQLite database service

        Args:
            db_path: Path to SQLite database file
            pool_size: Connection pool size
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self._connections: list[sqlite3.Connection] = []
        self._current_connection_index = 0
        self._ensure_database()
        logger.info("Initialized SQLite database service for %s", db_path)

    def _ensure_database(self) -> None:
        """Ensure database file and directory exist"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            self.db_path.touch()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a connection from the pool"""
        if self._connections and len(self._connections) >= self.pool_size:
            conn = self._connections[self._current_connection_index]
            self._current_connection_index = (self._current_connection_index + 1) % len(self._connections)
            return conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self._connections.append(conn)
        return conn

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error("Database error: %s", e)
            raise

    def execute_query(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        """
        Execute a SELECT query

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of dictionaries with query results
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def execute_update(self, query: str, params: tuple = ()) -> int:
        """
        Execute an INSERT/UPDATE/DELETE query

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Number of rows affected
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return int(cursor.rowcount)

    def execute_transaction(self, queries: list[tuple]) -> bool:
        """
        Execute multiple queries in a transaction

        Args:
            queries: List of (query, params) tuples

        Returns:
            True if transaction succeeded

        Raises:
            Exception: If transaction fails
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                for query, params in queries:
                    cursor.execute(query, params)
                return True
            except Exception as e:
                logger.error("Transaction failed: %s", e)
                raise

    def close(self) -> None:
        """Close all database connections"""
        for conn in self._connections:
            conn.close()
        self._connections.clear()
        logger.info("Closed all database connections")


class DatabaseServiceFactory:
    """Factory for creating database service instances"""

    @staticmethod
    def create_sqlite_service(db_path: Path, pool_size: int = 5) -> SQLiteDatabaseService:
        """
        Create SQLite database service

        Args:
            db_path: Path to SQLite database file
            pool_size: Connection pool size

        Returns:
            SQLiteDatabaseService instance
        """
        return SQLiteDatabaseService(db_path, pool_size)

    @staticmethod
    def create_service(db_type: str = "sqlite", **kwargs) -> DatabaseService:
        """
        Create database service by type

        Args:
            db_type: Type of database ("sqlite")
            **kwargs: Database-specific configuration

        Returns:
            DatabaseService instance

        Raises:
            ValueError: If database type is unknown
        """
        if db_type == "sqlite":
            return DatabaseServiceFactory.create_sqlite_service(**kwargs)
        else:
            raise ValueError(f"Unknown database type: {db_type}")
