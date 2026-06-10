import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aitbc.rate_limiting import RateLimitMiddleware

from .config import settings, validated_cors_origins
from .exceptions import register_exception_handlers
from .lifespan import lifespan
from .middleware import register_middleware
from .routers import ROUTERS
from .routers.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="AITBC Agent Coordinator",
        description="Advanced multi-agent coordination and management system",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=validated_cors_origins(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add rate limiting middleware
    app.add_middleware(
        RateLimitMiddleware,
        rate=100,
        per=60
    )

    for router in ROUTERS:
        # Check if router already has a prefix (like agent_messaging.router)
        if hasattr(router, 'prefix') and router.prefix.startswith('/api'):
            app.include_router(router)
        else:
            app.include_router(router, prefix="/v1")

    # Add health router without prefix for direct access to /health
    app.include_router(health_router)

    register_middleware(app)
    register_exception_handlers(app)
    return app


app = create_app()


def main():
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
