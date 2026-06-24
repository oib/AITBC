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
    "DatabaseMetrics",
    # Core database classes
    "DatabaseService",
    "DatabaseServiceFactory",
    "QueryMetrics",
    "QueryMonitor",
    "ReadReplicaManager",
    "SQLiteDatabaseService",
    "create_async_pooled_engine",
    "create_async_pooled_sessionmaker",
    "create_pooled_engine",
    "create_pooled_sessionmaker",
    "ensure_database",
    "get_database_connection",
    "get_table_info",
    "table_exists",
    "vacuum_database",
]
