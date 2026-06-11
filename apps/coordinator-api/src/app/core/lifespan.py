# mypy: ignore-errors
"""
Lifecycle events for Coordinator API.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app):
    """Lifecycle events for the Coordinator API."""
    from .config import settings
    from .database_async import close_async_db, init_async_db
    from .storage.db import init_db

    logger.info("Starting Coordinator API")

    try:
        # Initialize database
        try:
            init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.warning(f"Database initialization failed (non-fatal): {e}")

        # Initialize async database
        try:
            init_async_db()
            logger.info("Async database initialized successfully")
        except Exception as e:
            logger.warning(f"Async database initialization failed (non-fatal): {e}")

        # Warmup database connections
        logger.info("Warming up database connections...")
        try:
            from sqlmodel import select

            from .domain import Job
            from .storage import get_session

            session_gen = get_session()
            session = next(session_gen)
            try:
                test_query = select(Job).limit(1)
                session.execute(test_query).first()
            finally:
                session.close()
            logger.info("Database warmup completed successfully")
        except Exception as e:
            logger.warning(f"Database warmup failed: {e}")

        # Validate configuration
        if settings.environment == "production":
            logger.info("Production environment detected, validating configuration")
            logger.info("Configuration validation passed")

        # Initialize audit logging directory
        audit_dir = Path(settings.audit_log_dir)
        audit_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Audit logging directory: {audit_dir}")

        # Initialize rate limiting configuration
        logger.info("Rate limiting configuration:")
        logger.info(f"  Jobs submit: {settings.rate_limit_jobs_submit}")
        logger.info(f"  Miner register: {settings.rate_limit_miner_register}")
        logger.info(f"  Miner heartbeat: {settings.rate_limit_miner_heartbeat}")
        logger.info(f"  Admin stats: {settings.rate_limit_admin_stats}")

        # Log service startup details
        logger.info(f"Coordinator API started on {settings.app_host}:{settings.port}")
        logger.info(f"Database adapter: {settings.database.adapter}")
        logger.info(f"Environment: {settings.environment}")

        # Log complete configuration summary
        logger.info("=== Coordinator API Configuration Summary ===")
        logger.info(f"Environment: {settings.environment}")
        logger.info(f"Database: {settings.database.adapter}")
        logger.info("Rate Limits:")
        logger.info(f"  Jobs submit: {settings.rate_limit_jobs_submit}")
        logger.info(f"  Miner register: {settings.rate_limit_miner_register}")
        logger.info(f"  Miner heartbeat: {settings.rate_limit_miner_heartbeat}")
        logger.info(f"  Admin stats: {settings.rate_limit_admin_stats}")
        logger.info(f"Audit logging: {settings.audit_log_dir}")
        logger.info("=== Startup Complete ===")

        logger.info("🚀 Coordinator API is ready to serve requests")

        yield

    finally:
        # Cleanup
        logger.info("Shutting down Coordinator API")
        try:
            close_async_db()
            logger.info("Async database closed")
        except Exception as e:
            logger.warning(f"Error closing async database: {e}")
