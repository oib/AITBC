"""
AITBC Database Utilities
Database connection and query utilities for AITBC applications
Enhanced with read replica support and query monitoring

This module consolidates database functionality split into logical submodules.
"""

from .connection import DatabaseConnection
from .monitoring import QueryMetrics, DatabaseMetrics, QueryMonitor
from .pooling import (
    create_pooled_engine,
    create_pooled_sessionmaker,
    create_async_pooled_engine,
    create_async_pooled_sessionmaker,
)
from .replica import ReadReplicaManager
from .utils import (
    get_database_connection,
    ensure_database,
    vacuum_database,
    get_table_info,
    table_exists,
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
]
