"""
AITBC Database Utilities
Database connection and query utilities for AITBC applications
Enhanced with read replica support and query monitoring
"""

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from collections import defaultdict

# SQLAlchemy support for connection pooling
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from .aitbc_logging import get_logger
from .exceptions import DatabaseError

logger = get_logger(__name__)


@dataclass
class QueryMetrics:
    """Query performance metrics"""
    query: str
    execution_time_ms: float
    timestamp: datetime
    success: bool
    error_message: str | None = None
    row_count: int = 0


@dataclass
class DatabaseMetrics:
    """Database performance metrics"""
    total_queries: int = 0
    total_errors: int = 0
    avg_execution_time_ms: float = 0.0
    slow_queries: list[QueryMetrics] = field(default_factory=list)
    recent_queries: list[QueryMetrics] = field(default_factory=list)
    
    def add_query(self, metrics: QueryMetrics, slow_threshold_ms: float = 1000.0):
        """Add query metrics"""
        self.total_queries += 1
        if not metrics.success:
            self.total_errors += 1
        
        # Update average execution time
        total_time = self.avg_execution_time_ms * (self.total_queries - 1) + metrics.execution_time_ms
        self.avg_execution_time_ms = total_time / self.total_queries
        
        # Track slow queries
        if metrics.execution_time_ms > slow_threshold_ms:
            self.slow_queries.append(metrics)
        
        # Keep recent queries (last 100)
        self.recent_queries.append(metrics)
        if len(self.recent_queries) > 100:
            self.recent_queries.pop(0)


class QueryMonitor:
    """Query performance monitoring and logging"""
    
    def __init__(self, slow_query_threshold_ms: float = 1000.0, enable_logging: bool = True):
        """
        Initialize query monitor
        
        Args:
            slow_query_threshold_ms: Threshold for slow query detection
            enable_logging: Enable query logging
        """
        self.slow_query_threshold_ms = slow_query_threshold_ms
        self.enable_logging = enable_logging
        self.metrics = DatabaseMetrics()
        self.query_counts = defaultdict(int)
    
    def record_query(
        self,
        query: str,
        execution_time_ms: float,
        success: bool = True,
        error_message: str | None = None,
        row_count: int = 0
    ) -> None:
        """
        Record query execution metrics
        
        Args:
            query: SQL query string
            execution_time_ms: Execution time in milliseconds
            success: Whether query succeeded
            error_message: Error message if failed
            row_count: Number of rows affected/returned
        """
        metrics = QueryMetrics(
            query=query[:200],  # Truncate long queries
            execution_time_ms=execution_time_ms,
            timestamp=datetime.now(),
            success=success,
            error_message=error_message,
            row_count=row_count
        )
        
        self.metrics.add_query(metrics, self.slow_query_threshold_ms)
        self.query_counts[query[:100]] += 1
        
        if self.enable_logging:
            if not success:
                logger.error(f"Query failed: {error_message}")
            elif execution_time_ms > self.slow_query_threshold_ms:
                logger.warning(f"Slow query detected ({execution_time_ms:.2f}ms): {query[:100]}")
    
    def get_slow_queries(self, limit: int = 10) -> list[QueryMetrics]:
        """Get slow queries"""
        return sorted(self.metrics.slow_queries, key=lambda x: x.execution_time_ms, reverse=True)[:limit]
    
    def get_top_queries(self, limit: int = 10) -> list[tuple[str, int]]:
        """Get most frequently executed queries"""
        return sorted(self.query_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    
    def get_stats(self) -> dict[str, Any]:
        """Get monitoring statistics"""
        return {
            "total_queries": self.metrics.total_queries,
            "total_errors": self.metrics.total_errors,
            "error_rate": self.metrics.total_errors / self.metrics.total_queries if self.metrics.total_queries > 0 else 0,
            "avg_execution_time_ms": self.metrics.avg_execution_time_ms,
            "slow_query_count": len(self.metrics.slow_queries),
            "slow_query_threshold_ms": self.slow_query_threshold_ms
        }


class ReadReplicaManager:
    """Manages read replica database connections for PostgreSQL"""
    
    def __init__(
        self,
        primary_url: str,
        replica_urls: list[str] | None = None,
        read_weight: int = 70,  # Percentage of reads to replicas
        enable_auto_failover: bool = True
    ):
        """
        Initialize read replica manager
        
        Args:
            primary_url: Primary database URL for writes
            replica_urls: List of replica database URLs for reads
            read_weight: Percentage (0-100) of reads to route to replicas
            enable_auto_failover: Enable automatic failover to replicas
        """
        self.primary_url = primary_url
        self.replica_urls = replica_urls or []
        self.read_weight = max(0, min(100, read_weight))
        self.enable_auto_failover = enable_auto_failover
        
        self.primary_engine = None
        self.replica_engines = []
        self.current_replica_index = 0
        self.monitor = QueryMonitor()
        
        self._initialize_engines()
    
    def _initialize_engines(self) -> None:
        """Initialize primary and replica database engines"""
        # Create primary engine for writes
        self.primary_engine = create_engine(
            self.primary_url,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False
        )
        
        # Setup query monitoring for primary
        self._setup_monitoring(self.primary_engine, "primary")
        
        # Create replica engines for reads
        for replica_url in self.replica_urls:
            try:
                replica_engine = create_engine(
                    replica_url,
                    poolclass=QueuePool,
                    pool_size=10,
                    max_overflow=20,
                    pool_recycle=3600,
                    pool_pre_ping=True,
                    echo=False
                )
                self._setup_monitoring(replica_engine, f"replica_{len(self.replica_engines)}")
                self.replica_engines.append(replica_engine)
                logger.info(f"Connected to read replica: {replica_url}")
            except Exception as e:
                logger.warning(f"Failed to connect to replica {replica_url}: {e}")
        
        if not self.replica_engines:
            logger.warning("No read replicas available, all traffic will go to primary")
    
    def _setup_monitoring(self, engine, name: str) -> None:
        """Setup query monitoring for engine"""
        @event.listens_for(engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            context._query_start_time = time.time()
        
        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            if hasattr(context, '_query_start_time'):
                execution_time_ms = (time.time() - context._query_start_time) * 1000
                self.monitor.record_query(
                    query=statement,
                    execution_time_ms=execution_time_ms,
                    success=True,
                    row_count=cursor.rowcount if hasattr(cursor, 'rowcount') else 0
                )
    
    def get_read_engine(self):
        """
        Get a read engine (replica or primary)
        
        Returns:
            SQLAlchemy engine for read operations
        """
        # If no replicas or random selection falls in primary weight, use primary
        if not self.replica_engines or (self.read_weight < 100 and hash(time.time()) % 100 >= self.read_weight):
            return self.primary_engine
        
        # Round-robin replica selection
        if self.replica_engines:
            engine = self.replica_engines[self.current_replica_index]
            self.current_replica_index = (self.current_replica_index + 1) % len(self.replica_engines)
            return engine
        
        return self.primary_engine
    
    def get_write_engine(self):
        """
        Get write engine (always primary)
        
        Returns:
            SQLAlchemy engine for write operations
        """
        return self.primary_engine
    
    def get_session(self, read_only: bool = True):
        """
        Get database session
        
        Args:
            read_only: If True, use read engine; if False, use write engine
            
        Returns:
            SQLAlchemy session
        """
        engine = self.get_read_engine() if read_only else self.get_write_engine()
        Session = sessionmaker(bind=engine)
        return Session()
    
    def get_metrics(self) -> dict[str, Any]:
        """Get database performance metrics"""
        return {
            "query_monitor": self.monitor.get_stats(),
            "replica_count": len(self.replica_engines),
            "read_weight": self.read_weight,
            "slow_queries": [q.query for q in self.monitor.get_slow_queries(5)],
            "top_queries": [q[0] for q in self.monitor.get_top_queries(5)]
        }
    
    def close(self) -> None:
        """Close all database connections"""
        if self.primary_engine:
            self.primary_engine.dispose()
        for engine in self.replica_engines:
            engine.dispose()
        logger.info("All database connections closed")


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

    def get_slow_queries(self, limit: int = 10) -> list[QueryMetrics]:
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
        try:
            with self.cursor() as cursor:
                cursor.executemany(query, params_list)
        except sqlite3.Error as e:
            raise DatabaseError(f"Bulk execution failed: {e}") from e

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


# SQLAlchemy Connection Pooling Utilities

def create_pooled_engine(
    database_url: str,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_recycle: int = 3600,
    pool_pre_ping: bool = True,
    echo: bool = False,
    use_static_pool: bool = False
):
    """
    Create SQLAlchemy engine with connection pooling.

    Args:
        database_url: Database connection URL
        pool_size: Size of connection pool
        max_overflow: Maximum overflow connections
        pool_recycle: Connection recycle time in seconds
        pool_pre_ping: Test connections before using
        echo: Enable SQL query logging
        use_static_pool: Use StaticPool for SQLite (single connection)

    Returns:
        SQLAlchemy engine with connection pooling
    """
    if "sqlite" in database_url and use_static_pool:
        # SQLite with StaticPool (single connection, suitable for tests)
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=echo,
            pool_pre_ping=pool_pre_ping,
        )
    elif "sqlite" in database_url:
        # SQLite with QueuePool (limited pooling support)
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=QueuePool,
            pool_size=min(pool_size, 5),  # SQLite has limited concurrent access
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            echo=echo,
        )
    else:
        # PostgreSQL/MySQL with full connection pooling
        engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            echo=echo,
        )
    return engine


def create_pooled_sessionmaker(
    engine,
    autoflush: bool = False,
    autocommit: bool = False
):
    """
    Create session factory with connection pooling.

    Args:
        engine: SQLAlchemy engine
        autoflush: Enable autoflush
        autocommit: Enable autocommit

    Returns:
        Session factory
    """
    return sessionmaker(bind=engine, autoflush=autoflush, autocommit=autocommit)


def create_async_pooled_engine(
    database_url: str,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_recycle: int = 3600,
    pool_pre_ping: bool = True,
    echo: bool = False
):
    """
    Create async SQLAlchemy engine with connection pooling.

    Args:
        database_url: Database connection URL
        pool_size: Size of connection pool
        max_overflow: Maximum overflow connections
        pool_recycle: Connection recycle time in seconds
        pool_pre_ping: Test connections before using
        echo: Enable SQL query logging

    Returns:
        Async SQLAlchemy engine with connection pooling
    """
    # Convert to async URL
    if "sqlite" in database_url:
        async_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    elif "postgresql" in database_url:
        async_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    else:
        async_url = database_url

    engine = create_async_engine(
        async_url,
        poolclass=QueuePool,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
        pool_pre_ping=pool_pre_ping,
        echo=echo,
    )
    return engine


def create_async_pooled_sessionmaker(
    engine,
    expire_on_commit: bool = False
):
    """
    Create async session factory with connection pooling.

    Args:
        engine: Async SQLAlchemy engine
        expire_on_commit: Expire objects on commit

    Returns:
        Async session factory
    """
    return async_sessionmaker(engine, expire_on_commit=expire_on_commit)
