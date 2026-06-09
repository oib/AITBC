"""
Database connection management for AITBC applications.
"""

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import DatabaseError
from .monitoring import QueryMonitor

logger = get_logger(__name__)


class DatabaseConnection:
    """
    Base database connection class for AITBC applications.
    Provides common database operations with error handling and query monitoring.
    """

    def __init__(self, db_path: Path, timeout: int = 30, enable_monitoring: bool = True):
        """
        Initialize database connection.

        Args:
            db_path: Path to database file
            timeout: Connection timeout in seconds
            enable_monitoring: Enable query performance monitoring
        """
        self.db_path = db_path
        self.timeout = timeout
        self._connection = None
        self.enable_monitoring = enable_monitoring
        self.monitor = QueryMonitor() if enable_monitoring else None

    def connect(self) -> sqlite3.Connection:
        """
        Establish database connection.

        Returns:
            SQLite connection object

        Raises:
            DatabaseError: If connection fails
        """
        try:
            self._connection = sqlite3.connect(
                self.db_path,
                timeout=self.timeout
            )
            self._connection.row_factory = sqlite3.Row
            return self._connection
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to connect to database: {e}") from e

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def get_monitoring_stats(self) -> dict[str, Any] | None:
        """
        Get query monitoring statistics
        
        Returns:
            Dictionary of monitoring statistics or None if monitoring disabled
        """
        if self.monitor:
            return self.monitor.get_stats()
        return None

    def get_slow_queries(self, limit: int = 10) -> list:
        """
        Get slow queries
        
        Args:
            limit: Maximum number of slow queries to return
            
        Returns:
            List of slow query metrics
        """
        if self.monitor:
            return self.monitor.get_slow_queries(limit)
        return []

    @contextmanager
    def cursor(self):
        """
        Context manager for database cursor.

        Yields:
            Database cursor
        """
        if not self._connection:
            self.connect()
        cursor = self._connection.cursor()
        try:
            yield cursor
            self._connection.commit()
        except Exception as e:
            self._connection.rollback()
            raise DatabaseError(f"Database operation failed: {e}") from e
        finally:
            cursor.close()

    def execute(
        self,
        query: str,
        params: tuple[Any, ...] | None = None
    ) -> sqlite3.Cursor:
        """
        Execute a SQL query.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Cursor object

        Raises:
            DatabaseError: If query fails
        """
        start_time = time.time()
        try:
            with self.cursor() as cursor:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if self.monitor:
                    execution_time_ms = (time.time() - start_time) * 1000
                    self.monitor.record_query(
                        query=query,
                        execution_time_ms=execution_time_ms,
                        success=True,
                        row_count=cursor.rowcount if hasattr(cursor, 'rowcount') else 0
                    )
                
                return cursor
        except sqlite3.Error as e:
            if self.monitor:
                execution_time_ms = (time.time() - start_time) * 1000
                self.monitor.record_query(
                    query=query,
                    execution_time_ms=execution_time_ms,
                    success=False,
                    error_message=str(e)
                )
            raise DatabaseError(f"Query execution failed: {e}") from e

    def fetch_one(
        self,
        query: str,
        params: tuple[Any, ...] | None = None
    ) -> dict[str, Any] | None:
        """
        Fetch a single row from query.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Row as dictionary or None
        """
        with self.cursor() as cursor:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            row = cursor.fetchone()
            return dict(row) if row else None

    def fetch_all(
        self,
        query: str,
        params: tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        """
        Fetch all rows from query.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of rows as dictionaries
        """
        with self.cursor() as cursor:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def execute_many(
        self,
        query: str,
        params_list: list[tuple[Any, ...]]
    ) -> None:
        """
        Execute query with multiple parameter sets.

        Args:
            query: SQL query string
            params_list: List of parameter tuples

        Raises:
            DatabaseError: If query fails
        """
        start_time = time.time()
        try:
            with self.cursor() as cursor:
                cursor.executemany(query, params_list)
                
                if self.monitor:
                    execution_time_ms = (time.time() - start_time) * 1000
                    self.monitor.record_query(
                        query=query,
                        execution_time_ms=execution_time_ms,
                        success=True,
                        row_count=len(params_list)
                    )
        except sqlite3.Error as e:
            if self.monitor:
                execution_time_ms = (time.time() - start_time) * 1000
                self.monitor.record_query(
                    query=query,
                    execution_time_ms=execution_time_ms,
                    success=False,
                    error_message=str(e)
                )
            raise DatabaseError(f"Batch query execution failed: {e}") from e
