"""
Minimal Main Application - Only includes existing routers plus enhanced ones
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from .config import settings
from .storage import init_db
from .routers import (
    client,
    miner,
    admin,
    marketplace,
    explorer,
    services,
)
from .routers.marketplace_offers import router as marketplace_offers
from .routers.marketplace_enhanced_simple import router as marketplace_enhanced
from .routers.openclaw_enhanced_simple import router as openclaw_enhanced
from .exceptions import AITBCError, ErrorResponse
from .logging import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="AITBC Coordinator API - Enhanced",
        version="0.1.0",
        description="Enhanced coordinator service with multi-modal and OpenClaw capabilities.",
    )
    
    init_db()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"]
    )

    # Include existing routers
    app.include_router(client, prefix="/v1")
    app.include_router(miner, prefix="/v1")
    app.include_router(admin, prefix="/v1")
    app.include_router(marketplace, prefix="/v1")
    app.include_router(explorer, prefix="/v1")
    app.include_router(services, prefix="/v1")
    app.include_router(marketplace_offers, prefix="/v1")
    
    # Include enhanced routers
    app.include_router(marketplace_enhanced, prefix="/v1")
    app.include_router(openclaw_enhanced, prefix="/v1")

    # Add Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    @app.get("/v1/health", tags=["health"], summary="Service healthcheck")
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    return app
