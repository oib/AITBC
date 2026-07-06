"""
FastAPI application setup for Coordinator API.
"""

from fastapi import FastAPI

from aitbc.aitbc_logging import get_logger
from aitbc.health_checks import create_simple_health_response

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    from .lifespan import lifespan
    from .middleware import setup_middleware
    from .routers import register_routers

    app = FastAPI(
        title="AITBC Coordinator API", description="Coordinator API for AITBC Network", version="1.0.0", lifespan=lifespan
    )

    # Setup middleware
    setup_middleware(app)

    # Register routers
    register_routers(app)

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return create_simple_health_response("coordinator-api")

    logger.info("FastAPI application created successfully")
    return app
