"""
AITBC Database Utilities
Database connection and query utilities for AITBC applications
Enhanced with read replica support and query monitoring

This module consolidates database functionality split into logical submodules.
"""

from .connection import DatabaseConnection
from .monitoring import DatabaseMetrics, QueryMetrics, QueryMonitor
from .pooling import (
    create_async_pooled_engine,
    create_async_pooled_sessionmaker,
    create_pooled_engine,
    create_pooled_sessionmaker,
)
from .replica import ReadReplicaManager
from .service import (
    DatabaseService,
    DatabaseServiceFactory,
    SQLiteDatabaseService,
)
from .utils import (
    ensure_database,
    get_database_connection,
    get_table_info,
    table_exists,
    vacuum_database,
)

__all__ = [
    "DatabaseConnection",
    "QueryMetrics",
    "DatabaseMetrics",
    "QueryMonitor",
    "create_pooled_engine",
    "create_pooled_sessionmaker",
    "create_async_pooled_engine",
    "create_async_pooled_sessionmaker",
    "ReadReplicaManager",
    "get_database_connection",
    "ensure_database",
    "vacuum_database",
    "get_table_info",
    "table_exists",
    # Core database classes
    "DatabaseService",
    "SQLiteDatabaseService",
    "DatabaseServiceFactory",
]
