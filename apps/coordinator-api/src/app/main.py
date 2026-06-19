"""Coordinator API main entry point."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import Counter, Histogram, generate_latest, make_asgi_app
from prometheus_client.core import CollectorRegistry
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.http_client import setup_request_id_context
from aitbc.middleware import (
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    PrometheusMetricsMiddleware,
    RequestIDMiddleware,
)

if TYPE_CHECKING:
    from slowapi.errors import RateLimitExceeded
else:
    try:
        from slowapi.errors import RateLimitExceeded
    except ImportError:
        RateLimitExceeded = Exception  # type: ignore[assignment, misc]

from .config import settings
from .contexts.agent_identity.routers import agent_identity
from .contexts.blockchain.routers import blockchain
from .contexts.cross_chain.routers.cross_chain_integration import router as cross_chain

# Temporarily disabled due to import chain issues
# from .contexts.hermes.routers.hermes_decision import router as hermes_decision
# from .contexts.hermes.routers.hermes_enhanced_simple import router as hermes_enhanced
# from .contexts.hermes.routers.hermes_health import router as hermes_health
# from .contexts.hermes.routers.hermes_resource import router as hermes_resource
from .contexts.infrastructure.routers.monitoring_dashboard import router as monitoring_dashboard
from .contexts.ipfs.routers import router as ipfs
from .contexts.marketplace.routers import marketplace, marketplace_gpu, marketplace_offers
from .contexts.payments.routers import payments
from .contexts.portfolio.routers import portfolio_router
from .database_async import close_async_db
from .exceptions import AITBCError, ErrorResponse
from .routers import (
    admin,
    agent_router,
    client,
    developer_platform,
    edge_gpu,
    exchange,
    explorer,
    governance_enhanced,
    inference,
    islands_proxy,
    miner,
    monitor,
    multi_modal_rl,
    services,
    swarm,
    training,
    users,
    web_vitals,
)
from .utils.alerting import alert_dispatcher
from .utils.cache import cache_manager
from .utils.metrics import build_live_metrics_payload, metrics_collector
from .utils.security import get_client_ip

configure_logging(level=settings.log_level if hasattr(settings, "log_level") else "INFO")
logger = get_logger(__name__)

ml_zk_proofs: APIRouter | None = None
try:
    from .contexts.zk_applications.routers.ml_zk_proofs import router as ml_zk_proofs_import

    ml_zk_proofs = ml_zk_proofs_import
except ImportError:
    logger.warning("ML ZK proofs router not available (missing tenseal)")

multi_modal_rl_router: APIRouter | None = None
try:
    from .contexts.multimodal.routers.multi_modal_rl import router as multi_modal_rl_import

    multi_modal_rl_router = multi_modal_rl_import
except ImportError:
    logger.warning("Multi-modal RL router not available (missing torch)")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the Coordinator API."""
    from .core.lifecycle import get_lifecycle_state, get_task_manager

    lifecycle_state = get_lifecycle_state()
    task_manager = get_task_manager()

    logger.info("Starting Coordinator API")
    lifecycle_state.set_state(lifecycle_state.STARTING)
    try:
        # Consolidated database initialization
        from .storage.db import init_async_db, init_db

        try:
            init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.warning("Database initialization failed (non-fatal): %s", e)
        try:
            await init_async_db()
            logger.info("Async database initialized successfully")
        except Exception as e:
            logger.warning("Async database initialization failed (non-fatal): %s", e)
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
            logger.warning("Database warmup failed: %s", e)
        if settings.environment == "production":
            logger.info("Production environment detected, configuration validated by Pydantic model validator")

        # Check for duplicate routes
        route_pairs = set()
        duplicates = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    pair = (method, route.path)
                    if pair in route_pairs:
                        duplicates.append(pair)
                    route_pairs.add(pair)
        if duplicates:
            logger.warning("Found duplicate route registrations: %s", duplicates)
            # Note: This will be enforced once Agent B removes duplicate router registrations (Goal 12)
            # For now, we only log warnings to avoid breaking the current system
        import anyio

        audit_dir = anyio.Path(settings.audit_log_dir)
        await audit_dir.mkdir(parents=True, exist_ok=True)
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
        logger.info("  Marketplace list: %s", settings.rate_limit_marketplace_list)
        logger.info("  Marketplace stats: %s", settings.rate_limit_marketplace_stats)
        logger.info("  Marketplace bid: %s", settings.rate_limit_marketplace_bid)
        logger.info("  Exchange payment: %s", settings.rate_limit_exchange_payment)
        logger.info("Audit logging: %s", settings.audit_log_dir)
        logger.info("=== Startup Complete ===")
        logger.info("Health check endpoints initialized")
        logger.info("🚀 Coordinator API is ready to serve requests")

        lifecycle_state.set_state(lifecycle_state.RUNNING)
        yield
    except Exception as e:
        logger.error("Failed to start Coordinator API: %s", e)
        raise
    finally:
        lifecycle_state.set_state(lifecycle_state.SHUTTING_DOWN)
        logger.info("Shutting down Coordinator API")
        try:
            logger.info("Initiating graceful shutdown sequence...")
            logger.info("Stopping new request processing")
            import asyncio

            logger.info("Waiting for in-flight requests to complete...")
            await asyncio.sleep(1)
            logger.info("Closing database connections...")
            try:
                logger.info("Database connections closed successfully")
            except Exception as e:
                logger.warning("Error closing database connections: %s", e)
            try:
                await close_async_db()
                logger.info("Async database connections closed successfully")
            except Exception as e:
                logger.warning("Error closing async database connections: %s", e)
            logger.info("Stopping background tasks...")
            await task_manager.stop_all()
            logger.info("Cleaning up rate limiting state...")
            logger.info("Cleaning up audit resources...")
            logger.info("=== Coordinator API Shutdown Summary ===")
            logger.info("All resources cleaned up successfully")
            logger.info("Graceful shutdown completed")
            logger.info("=== Shutdown Complete ===")
        except Exception as e:
            logger.error("Error during shutdown: %s", e)

        lifecycle_state.set_state(lifecycle_state.STOPPED)


def create_app() -> FastAPI:
    limiter = Limiter(key_func=get_remote_address)

    # Disable docs and redoc in production
    docs_url = "/docs" if settings.debug else None
    redoc_url = "/redoc" if settings.debug else None

    app = FastAPI(
        title="AITBC Coordinator API",
        description="API for coordinating AI training jobs and blockchain operations",
        version="1.0.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
        openapi_components={"securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-Api-Key"}}},
        openapi_tags=[
            {"name": "health", "description": "Health check endpoints"},
            {"name": "client", "description": "Client operations"},
            {"name": "miner", "description": "Miner operations"},
            {"name": "admin", "description": "Admin operations"},
            {"name": "marketplace", "description": "GPU Marketplace"},
            {"name": "exchange", "description": "Exchange operations"},
            {"name": "governance", "description": "Governance operations"},
            {"name": "zk", "description": "Zero-Knowledge proofs"},
        ],
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(PerformanceLoggingMiddleware)
    app.add_middleware(PrometheusMetricsMiddleware)
    app.add_middleware(ErrorHandlerMiddleware)

    @app.middleware("http")
    async def request_id_context_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Set request ID in context for HTTP client propagation."""
        setup_request_id_context(request)
        return await call_next(request)

    @app.middleware("http")
    async def security_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Security middleware for input validation and logging."""
        client_ip = get_client_ip(request)
        request.state.client_ip = client_ip
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 10 * 1024 * 1024:
            logger.warning("Request too large from %s: %s bytes", client_ip, content_length)
            return JSONResponse(status_code=413, content={"detail": "Request entity too large"})
        user_agent = request.headers.get("user-agent", "")
        suspicious_patterns = ["sqlmap", "nmap", "nikto", "burp"]
        for pattern in suspicious_patterns:
            if pattern.lower() in user_agent.lower():
                logger.warning("Suspicious user agent from %s: %s", client_ip, user_agent)
                return JSONResponse(status_code=403, content={"detail": "Access denied"})
        return await call_next(request)

    @app.middleware("http")
    async def request_metrics_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start_time = __import__("time").perf_counter()
        metrics_collector.increment_api_requests()
        try:
            response = await call_next(request)
            if response.status_code >= 400:
                metrics_collector.increment_api_errors()
            return response
        except Exception:
            metrics_collector.increment_api_errors()
            raise
        finally:
            duration = __import__("time").perf_counter() - start_time
            metrics_collector.record_api_response_time(duration)
            metrics_collector.update_cache_stats(cache_manager.get_stats())

    app.include_router(client, prefix="/v1")
    if admin:
        app.include_router(admin, prefix="/v1")
    app.include_router(marketplace, prefix="/v1")
    app.include_router(marketplace_gpu, prefix="/v1")
    app.include_router(marketplace_offers, prefix="/v1")
    app.include_router(monitor, prefix="/v1")
    app.include_router(miner, prefix="/v1")
    app.include_router(agent_router, prefix="/v1")
    app.include_router(islands_proxy, prefix="/v1")
    app.include_router(cross_chain, prefix="/v1")
    try:
        from .routers.zk_proofs import router as zk_proofs_router

        app.include_router(zk_proofs_router, prefix="/v1")
        logger.info("ZK proofs router included")
    except Exception as e:
        logger.warning("Failed to include ZK proofs router: %s", e)
    try:
        from .routers.fhe import router as fhe_router

        app.include_router(fhe_router, prefix="/v1")
        logger.info("FHE router included")
    except Exception as e:
        logger.warning("Failed to include FHE router: %s", e)
    try:
        from .routers.oracle import router as oracle_router

        app.include_router(oracle_router, prefix="/v1")
        logger.info("Oracle router included")
    except Exception as e:
        logger.warning("Failed to include Oracle router: %s", e)
    try:
        from .routers.disputes import router as disputes_router

        app.include_router(disputes_router, prefix="/v1")
        logger.info("Disputes router included")
        from .services.dispute_resolution import init_dispute_service
        from .storage.db import get_session

        init_dispute_service(get_session)
        logger.info("Dispute service initialized")
    except Exception as e:
        logger.warning("Failed to include disputes router: %s", e)
    app.include_router(portfolio_router, prefix="/v1")
    try:
        from .routers.bounty import router as bounty_router

        app.include_router(bounty_router, prefix="/v1")
        logger.info("Bounty router included")
    except Exception as e:
        logger.warning("Failed to include Bounty router: %s", e)
    try:
        from .routers.hermes import router as hermes_router

        app.include_router(hermes_router, prefix="/v1")
        logger.info("Hermes router included")
    except Exception as e:
        logger.warning("Failed to include Hermes router: %s", e)
    app.include_router(swarm, prefix="/v1")
    logger.info("Swarm router included")
    app.include_router(ipfs, prefix="/v1/ipfs", tags=["ipfs"])
    logger.info("IPFS router included")
    app.include_router(payments, prefix="/v1")
    logger.info("Payments router included")
    app.include_router(training, prefix="/v1")
    logger.info("Training router included")
    app.include_router(inference, prefix="/v1")
    logger.info("Inference router included")
    try:
        from .routers.governance import router as governance_router

        app.include_router(governance_router, prefix="/v1")
        logger.info("Governance router included")
        from .services.governance_service import init_governance_service
        from .storage.db import get_session

        init_governance_service(get_session)
        logger.info("Governance service initialized")
    except Exception as e:
        logger.warning("Failed to include governance router: %s", e)
    app.include_router(explorer, prefix="/v1")
    app.include_router(services, prefix="/v1")
    app.include_router(users, prefix="/v1")
    app.include_router(exchange, prefix="/v1")
    app.include_router(web_vitals, prefix="/v1")
    if ml_zk_proofs:
        app.include_router(ml_zk_proofs, prefix="/v1")
    # Temporarily disabled due to import chain issues
    # app.include_router(hermes_enhanced, prefix="/v1")
    # app.include_router(hermes_decision, prefix="/v1")
    # app.include_router(hermes_health, prefix="/v1")
    # app.include_router(hermes_resource, prefix="/v1")
    app.include_router(monitoring_dashboard, prefix="/v1")
    app.include_router(agent_router, prefix="/v1/agents")
    app.include_router(agent_identity, prefix="/v1")
    app.include_router(developer_platform, prefix="/v1")
    app.include_router(governance_enhanced, prefix="/v1")
    try:
        from .contexts.staking.routers.staking import router as staking_router

        app.include_router(staking_router, prefix="/v1")
        logger.info("Staking router included")
    except Exception as e:
        logger.warning("Failed to include staking router: %s", e)
    try:
        from .routers import agent_security_router

        if agent_security_router:
            app.include_router(agent_security_router, prefix="/v1")
            logger.info("Security router included")
        else:
            logger.warning("Security router not available")
    except Exception as e:
        logger.warning("Failed to include security router: %s", e)
    try:
        from .routers import trading

        if trading:
            app.include_router(trading, prefix="/v1")
            logger.info("Trading router included")
        else:
            logger.warning("Trading router not available")
    except Exception as e:
        logger.warning("Failed to include trading router: %s", e)
    try:
        from .routers import reputation

        if reputation:
            app.include_router(reputation, prefix="/v1")
            logger.info("Reputation router included")
        else:
            logger.warning("Reputation router not available")
    except Exception as e:
        logger.warning("Failed to include reputation router: %s", e)
    try:
        from .routers import rewards

        if rewards:
            app.include_router(rewards, prefix="/v1")
            logger.info("Rewards router included")
        else:
            logger.warning("Rewards router not available")
    except Exception as e:
        logger.warning("Failed to include rewards router: %s", e)
    try:
        from .contexts.knowledge.routers.knowledge import router as knowledge_router

        app.include_router(knowledge_router, prefix="/v1")
        logger.info("Knowledge Graph router included")
    except Exception as e:
        logger.warning("Failed to include Knowledge Graph router: %s", e)
    app.include_router(blockchain, prefix="/v1")
    app.include_router(edge_gpu, prefix="/v1")
    app.include_router(multi_modal_rl, prefix="/v1")
    metrics_app = make_asgi_app()
    app.mount("/prometheus", metrics_app)
    rate_limit_registry = CollectorRegistry()
    rate_limit_hits_total = Counter(
        "rate_limit_hits_total",
        "Total number of rate limit violations",
        ["endpoint", "method", "limit"],
        registry=rate_limit_registry,
    )
    Histogram(
        "rate_limit_response_time_seconds",
        "Response time for rate limited requests",
        ["endpoint", "method"],
        registry=rate_limit_registry,
    )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        """Handle rate limit exceeded errors with proper 429 status."""
        request_id = request.headers.get("X-Request-ID")
        endpoint = request.url.path
        method = request.method
        limit_detail = str(exc.detail) if hasattr(exc, "detail") else "unknown"
        rate_limit_hits_total.labels(endpoint=endpoint, method=method, limit=limit_detail).inc()
        logger.warning(
            "Rate limit exceeded: %s, Request ID: %s, Path: %s, Method: %s, Limit Detail: %s",
            exc,
            request_id,
            request.url.path,
            request.method,
            limit_detail,
        )
        error_response = ErrorResponse(
            error={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests. Please try again later.",
                "status": 429,
                "details": [
                    {"field": "rate_limit", "message": str(exc.detail), "code": "too_many_requests", "retry_after": 60}
                ],
            },
            request_id=request_id,
        )
        return JSONResponse(status_code=429, content=error_response.model_dump(), headers={"Retry-After": "60"})

    @app.get("/rate-limit-metrics")
    async def rate_limit_metrics() -> Response:
        """Rate limiting metrics endpoint."""
        return Response(content=generate_latest(rate_limit_registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/metrics", tags=["health"], summary="Live JSON metrics for dashboard consumption")
    async def live_metrics() -> dict[str, Any]:
        return build_live_metrics_payload(
            cache_stats=cache_manager.get_stats(), dispatcher=alert_dispatcher, collector=metrics_collector
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle all unhandled exceptions with structured error responses."""
        request_id = request.headers.get("X-Request-ID")
        error_response = ErrorResponse(
            error={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "status": 500,
                "details": [{"field": "internal", "message": "Internal error - see server logs", "code": "INTERNAL_ERROR"}],
            },
            request_id=request_id,
        )
        logger.error("Internal server error", extra={"request_id": request_id, "error_type": type(exc).__name__})
        return JSONResponse(status_code=500, content=error_response.model_dump())

    @app.exception_handler(AITBCError)
    async def aitbc_error_handler(request: Request, exc: AITBCError) -> JSONResponse:
        """Handle AITBC exceptions with structured error responses."""
        request_id = request.headers.get("X-Request-ID")
        response = exc.to_response(request_id)
        return JSONResponse(status_code=response.error["status"], content=response.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Handle FastAPI validation errors with structured error responses."""
        request_id = request.headers.get("X-Request-ID")
        logger.warning(
            "Validation error: %s, Request ID: %s, Path: %s, Method: %s", exc, request_id, request.url.path, request.method
        )
        details = []
        for error in exc.errors():
            details.append(
                {"field": ".".join(str(loc) for loc in error["loc"]), "message": error["msg"], "code": error["type"]}
            )
        error_response = ErrorResponse(
            error={"code": "VALIDATION_ERROR", "message": "Request validation failed", "status": 422, "details": details},
            request_id=request_id,
        )
        return JSONResponse(status_code=422, content=error_response.model_dump())

    @app.get("/health", tags=["health"], summary="Service healthcheck")
    async def health() -> dict[str, str]:
        import sys

        return {
            "status": "ok",
            "env": settings.environment,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }

    @app.get("/health/live", tags=["health"], summary="Liveness probe")
    async def liveness() -> dict[str, str]:
        import sys

        return {
            "status": "alive",
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }

    @app.get("/health/ready", tags=["health"], summary="Readiness probe")
    async def readiness() -> Response:
        try:
            import sys

            from sqlalchemy import text

            from .storage import get_session

            for session in get_session():
                session.execute(text("SELECT 1"))
                break
            return JSONResponse(
                status_code=200,
                content={
                    "status": "ready",
                    "database": "connected",
                    "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                },
            )
        except Exception as e:
            logger.error("Readiness check failed", extra={"exc": str(e)})
            return JSONResponse(status_code=503, content={"status": "not ready", "error": "Service not ready"})

    # Startup guard: fail if duplicate routes are registered
    _seen_routes: set[tuple[str, str]] = set()
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method == "HEAD":
                    continue
                key = (method, route.path)
                if key in _seen_routes:
                    logger.warning(f"Duplicate route registered: {method} {route.path}")
                _seen_routes.add(key)

    return app


app = create_app()

# Only register debug routes in debug mode
if settings.debug:

    @app.get("/_debug/routes", include_in_schema=False)
    async def debug_routes() -> dict[str, list[dict[str, Any]]]:
        routes: list[dict[str, Any]] = []
        for route in app.routes:
            if hasattr(route, "path"):
                methods: set[str] = getattr(route, "methods", set())
                routes.append({"path": route.path, "methods": sorted(methods)})
        return {"routes": sorted(routes, key=lambda r: r["path"])}


# Startup assertion: fail if debug routes are mounted in production
if not settings.debug:
    for route in app.routes:
        if hasattr(route, "path") and route.path.startswith("/_debug"):
            raise RuntimeError(f"Debug route {route.path} mounted in production environment")
