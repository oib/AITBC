"""
FastAPI application setup for Coordinator API.
"""

import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    from .lifespan import lifespan
    from .middleware import setup_middleware
    from .routers import register_routers

    app = FastAPI(
        title="AITBC Coordinator API",
        description="Coordinator API for AITBC Network",
        version="1.0.0",
        lifespan=lifespan
    )

    # Setup middleware
    setup_middleware(app)

    # Register routers
    register_routers(app)

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy", "service": "coordinator-api"}

    logger.info("FastAPI application created successfully")
    return app
