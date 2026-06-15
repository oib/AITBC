"""
Read replica management for PostgreSQL databases.
"""

import time
from typing import Any
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from aitbc.aitbc_logging import get_logger
from .monitoring import QueryMonitor

logger = get_logger(__name__)


class ReadReplicaManager:
    """Manages read replica database connections for PostgreSQL"""

    def __init__(
        self, primary_url: str, replica_urls: list[str] | None = None, read_weight: int = 70, enable_auto_failover: bool = True
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
        self.primary_engine = create_engine(
            self.primary_url,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False,
        )
        self._setup_monitoring(self.primary_engine, "primary")
        for replica_url in self.replica_urls:
            try:
                replica_engine = create_engine(
                    replica_url,
                    poolclass=QueuePool,
                    pool_size=10,
                    max_overflow=20,
                    pool_recycle=3600,
                    pool_pre_ping=True,
                    echo=False,
                )
                self._setup_monitoring(replica_engine, f"replica_{len(self.replica_engines)}")
                self.replica_engines.append(replica_engine)
                logger.info("Connected to read replica: %s", replica_url)
            except Exception as e:
                logger.warning("Failed to connect to replica %s: %s", replica_url, e)
        if not self.replica_engines:
            logger.warning("No read replicas available, all traffic will go to primary")

    def _setup_monitoring(self, engine, name: str) -> None:
        """Setup query monitoring for engine"""

        @event.listens_for(engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            context._query_start_time = time.time()

        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            if hasattr(context, "_query_start_time"):
                execution_time_ms = (time.time() - context._query_start_time) * 1000
                self.monitor.record_query(
                    query=statement,
                    execution_time_ms=execution_time_ms,
                    success=True,
                    row_count=cursor.rowcount if hasattr(cursor, "rowcount") else 0,
                )

    def get_read_engine(self):
        """
        Get a read engine (replica or primary)

        Returns:
            SQLAlchemy engine for read operations
        """
        if not self.replica_engines or (self.read_weight < 100 and hash(time.time()) % 100 >= self.read_weight):
            return self.primary_engine
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
        }

    def close(self) -> None:
        """Close all database connections"""
        if self.primary_engine:
            self.primary_engine.dispose()
        for engine in self.replica_engines:
            engine.dispose()
        logger.info("All database connections closed")
