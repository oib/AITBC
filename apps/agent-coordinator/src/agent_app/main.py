import os

import uvicorn
from fastapi import FastAPI
from aitbc.middleware import RequestValidationMiddleware, setup_cors

from aitbc.aitbc_logging import configure_logging, get_logger
from aitbc.rate_limiting import RateLimitMiddleware, client_ip_for_rate_limit

from .config import settings, validated_cors_origins
from .exceptions import register_exception_handlers
from .lifespan import lifespan
from .middleware import register_middleware
from .routers import ROUTERS
from .routers.health import router as health_router

configure_logging(level="INFO", service_name="agent-coordinator", to_file=True)
logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="AITBC Agent Coordinator",
        description="Advanced multi-agent coordination and management system",
        version="1.0.0",
        lifespan=lifespan,
    )

    setup_cors(app, allow_origins=validated_cors_origins(settings.cors_origins))

    # Cap request bodies at the edge of the app: this service binds :8107
    # directly and the api-gateway's 10MB cap only covers proxied paths —
    # without this middleware every pydantic body and `await request.body()`
    # was unbounded (DOS-AUDIT-1 / #1547). 5MB matches the nginx
    # client_max_body_size on the proxied /agent/* locations.
    app.add_middleware(RequestValidationMiddleware, max_request_size=5 * 1024 * 1024)

    # Add rate limiting middleware — scoped to mutating methods so GET
    # polling (dashboards, status pages, agent status reads) is never
    # throttled into a self-DoS, matching trading/pool-hub. Keyed by
    # client_ip_for_rate_limit (trusted-proxy aware) rather than the raw
    # peer default, which collapses proxied callers into one bucket.
    _MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
    app.add_middleware(
        RateLimitMiddleware,
        rate=100,
        per=60,
        key_func=client_ip_for_rate_limit,
        methods=_MUTATING_METHODS,
        exclude_paths=["/health", "/metrics", "/v1/metrics"],
        error_message="Agent coordinator rate limit exceeded",
    )

    for router in ROUTERS:
        # Check if router already has a prefix (like agent_messaging.router)
        if hasattr(router, "prefix") and router.prefix.startswith("/api"):
            app.include_router(router)
        else:
            app.include_router(router, prefix="/v1")

    # Add health router without prefix for direct access to /health
    app.include_router(health_router)

    register_middleware(app)
    register_exception_handlers(app)
    return app


app = create_app()


def main() -> None:
    uvicorn.run(
        "agent_app.main:app",
        host=settings.host,
        port=settings.port,
        reload=os.getenv("UVICORN_RELOAD", "false").lower() in ("true", "1", "yes"),
        log_level="critical",
        access_log=False,
    )


if __name__ == "__main__":
    main()
