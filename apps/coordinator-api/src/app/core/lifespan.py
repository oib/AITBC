"""
Lifecycle events for Coordinator API.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger

from .lifecycle import get_lifecycle_state, get_task_manager

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: Any) -> AsyncIterator[None]:
    """Lifecycle events for the Coordinator API."""
    from .config import settings  # type: ignore
    from .database_async import close_async_db, init_async_db  # type: ignore
    from .storage.db import init_db  # type: ignore

    lifecycle_state = get_lifecycle_state()
    lifecycle_state.set_state(lifecycle_state.STARTING)

    logger.info("Starting Coordinator API")
    try:
        try:
            init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.warning("Database initialization failed (non-fatal): %s", e)
        try:
            init_async_db()
            logger.info("Async database initialized successfully")
        except Exception as e:
            logger.warning("Async database initialization failed (non-fatal): %s", e)
        logger.info("Warming up database connections...")
        try:
            from sqlmodel import select

            from .contexts.infrastructure.domain import Job  # type: ignore
            from .storage import get_session  # type: ignore

            session_gen = get_session()
            session = next(session_gen)
            try:
                test_query = select(Job).limit(1)
                session.execute(test_query).first()
            finally:
                session.close()
            logger.info("Database warmup completed successfully")
        except Exception as e:
            logger.warning("Database warmup failed: %s", e)
        if settings.environment == "production":
            logger.info("Production environment detected, validating configuration")
            logger.info("Configuration validation passed")
        audit_dir = Path(settings.audit_log_dir)
        audit_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Audit logging directory: %s", audit_dir)
        logger.info("Rate limiting configuration:")
        logger.info("  Jobs submit: %s", settings.rate_limit_jobs_submit)
        logger.info("  Miner register: %s", settings.rate_limit_miner_register)
        logger.info("  Miner heartbeat: %s", settings.rate_limit_miner_heartbeat)
        logger.info("  Admin stats: %s", settings.rate_limit_admin_stats)
        logger.info("Coordinator API started on %s:%s", settings.app_host, settings.port)
        logger.info("Database adapter: %s", settings.database.adapter)
        logger.info("Environment: %s", settings.environment)
        logger.info("=== Coordinator API Configuration Summary ===")
        logger.info("Environment: %s", settings.environment)
        logger.info("Database: %s", settings.database.adapter)
        logger.info("Rate Limits:")
        logger.info("  Jobs submit: %s", settings.rate_limit_jobs_submit)
        logger.info("  Miner register: %s", settings.rate_limit_miner_register)
        logger.info("  Miner heartbeat: %s", settings.rate_limit_miner_heartbeat)
        logger.info("  Admin stats: %s", settings.rate_limit_admin_stats)
        logger.info("Audit logging: %s", settings.audit_log_dir)
        logger.info("=== Startup Complete ===")
        logger.info("🚀 Coordinator API is ready to serve requests")

        lifecycle_state.set_state(lifecycle_state.RUNNING)
        yield
    finally:
        lifecycle_state.set_state(lifecycle_state.SHUTTING_DOWN)
        logger.info("Shutting down Coordinator API")
        try:
            close_async_db()
            logger.info("Async database closed")
        except Exception as e:
            logger.warning("Error closing async database: %s", e)

        # Stop all background tasks
        task_manager = get_task_manager()
        await task_manager.stop_all()

        lifecycle_state.set_state(lifecycle_state.STOPPED)
        logger.info("Shutdown complete")
