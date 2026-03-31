"""
Simple Main Application - Only enhanced routers for demonstration
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers.marketplace_enhanced_simple import router as marketplace_enhanced
from .routers.openclaw_enhanced_simple import router as openclaw_enhanced


def create_app() -> FastAPI:
    app = FastAPI(
        title="AITBC Enhanced API",
        version="0.1.0",
        description="Enhanced AITBC API with multi-modal and OpenClaw capabilities.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Include enhanced routers
    app.include_router(marketplace_enhanced, prefix="/v1")
    app.include_router(openclaw_enhanced, prefix="/v1")

    @app.get("/v1/health", tags=["health"], summary="Service healthcheck")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "enhanced"}

    return app
