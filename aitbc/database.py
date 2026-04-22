"""
AITBC Database Utilities
Database connection and query utilities for AITBC applications
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager
from .exceptions import DatabaseError


class DatabaseConnection:
    """
    Base database connection class for AITBC applications.
    Provides common database operations with error handling.
    """
    
    def __init__(self, db_path: Path, timeout: int = 30):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to database file
            timeout: Connection timeout in seconds
        """
        self.db_path = db_path
        self.timeout = timeout
        self._connection = None
    
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
            raise DatabaseError(f"Failed to connect to database: {e}")
    
    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
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
            raise DatabaseError(f"Database operation failed: {e}")
        finally:
            cursor.close()
    
    async def execute(
        self,
        query: str,
        params: Optional[Tuple[Any, ...]] = None
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
        try:
            with self.cursor() as cursor:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                return cursor
        except sqlite3.Error as e:
            raise DatabaseError(f"Query execution failed: {e}")
    
    async def fetch_one(
        self,
        query: str,
        params: Optional[Tuple[Any, ...]] = None
    ) -> Optional[Dict[str, Any]]:
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
    
    async def fetch_all(
        self,
        query: str,
        params: Optional[Tuple[Any, ...]] = None
    ) -> List[Dict[str, Any]]:
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
    
    async def execute_many(
        self,
        query: str,
        params_list: List[Tuple[Any, ...]]
    ) -> None:
        """
        Execute query with multiple parameter sets.
        
        Args:
            query: SQL query string
            params_list: List of parameter tuples
            
        Raises:
            DatabaseError: If query fails
        """
        try:
            with self.cursor() as cursor:
                cursor.executemany(query, params_list)
        except sqlite3.Error as e:
            raise DatabaseError(f"Bulk execution failed: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


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
    except sqlite3.Error as e:
        raise DatabaseError(f"Database vacuum failed: {e}")


def get_table_info(db_path: Path, table_name: str) -> List[Dict[str, Any]]:
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
