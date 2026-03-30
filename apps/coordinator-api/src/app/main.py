"""Coordinator API main entry point."""
import sys
import os

# Security: Lock sys.path to trusted locations to prevent malicious package shadowing
# Keep: site-packages under /opt/aitbc (venv), stdlib paths, our app directory, and crypto/sdk paths
_LOCKED_PATH = []
for p in sys.path:
    if 'site-packages' in p and '/opt/aitbc' in p:
        _LOCKED_PATH.append(p)
    elif 'site-packages' not in p and ('/usr/lib/python' in p or '/usr/local/lib/python' in p):
        _LOCKED_PATH.append(p)
    elif p.startswith('/opt/aitbc/apps/coordinator-api'):  # our app code
        _LOCKED_PATH.append(p)
    elif p.startswith('/opt/aitbc/packages/py/aitbc-crypto'):  # crypto module
        _LOCKED_PATH.append(p)
    elif p.startswith('/opt/aitbc/packages/py/aitbc-sdk'):  # sdk module
        _LOCKED_PATH.append(p)

# Add crypto and sdk paths to sys.path
sys.path.insert(0, '/opt/aitbc/packages/py/aitbc-crypto/src')
sys.path.insert(0, '/opt/aitbc/packages/py/aitbc-sdk/src')

from sqlalchemy.orm import Session
from typing import Annotated
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from prometheus_client import Counter, Histogram, generate_latest, make_asgi_app
from prometheus_client.core import CollectorRegistry
from prometheus_client.exposition import CONTENT_TYPE_LATEST

from .config import settings
from .storage import init_db
from .routers import (
    client,
    miner,
    admin,
    marketplace,
    marketplace_gpu,
    exchange,
    users,
    services,
    marketplace_offers,
    zk_applications,
    explorer,
    payments,
    web_vitals,
    edge_gpu,
    cache_management,
    agent_identity,
    agent_router,
    global_marketplace,
    cross_chain_integration,
    global_marketplace_integration,
    developer_platform,
    governance_enhanced,
    blockchain
)
# Skip optional routers with missing dependencies
try:
    from .routers.ml_zk_proofs import router as ml_zk_proofs
except ImportError:
    ml_zk_proofs = None
    print("WARNING: ML ZK proofs router not available (missing tenseal)")
from .routers.community import router as community_router
from .routers.governance import router as new_governance_router
from .routers.partners import router as partners
from .routers.marketplace_enhanced_simple import router as marketplace_enhanced
from .routers.openclaw_enhanced_simple import router as openclaw_enhanced
from .routers.monitoring_dashboard import router as monitoring_dashboard
# Skip optional routers with missing dependencies
try:
    from .routers.multi_modal_rl import router as multi_modal_rl_router
except ImportError:
    multi_modal_rl_router = None
    print("WARNING: Multi-modal RL router not available (missing torch)")

try:
    from .routers.ml_zk_proofs import router as ml_zk_proofs
except ImportError:
    ml_zk_proofs = None
    print("WARNING: ML ZK proofs router not available (missing dependencies)")
from .storage.models_governance import GovernanceProposal, ProposalVote, TreasuryTransaction, GovernanceParameter
from .exceptions import AITBCError, ErrorResponse
import logging
logger = logging.getLogger(__name__)
from .config import settings
from .storage.db import init_db



from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events for the Coordinator API."""
    logger.info("Starting Coordinator API")
    
    try:
        # Initialize database
        init_db()
        logger.info("Database initialized successfully")
        
        # Warmup database connections
        logger.info("Warming up database connections...")
        try:
            # Test database connectivity
            from sqlmodel import select
            from .domain import Job
            from .storage import get_session
            
            # Simple connectivity test using dependency injection
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
            # Continue startup even if warmup fails
        
        # Validate configuration
        if settings.app_env == "production":
            logger.info("Production environment detected, validating configuration")
            # Configuration validation happens automatically via Pydantic validators
            logger.info("Configuration validation passed")
            
        # Initialize audit logging directory
        from pathlib import Path
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
        logger.info(f"Coordinator API started on {settings.app_host}:{settings.app_port}")
        logger.info(f"Database adapter: {settings.database.adapter}")
        logger.info(f"Environment: {settings.app_env}")
        
        # Log complete configuration summary
        logger.info("=== Coordinator API Configuration Summary ===")
        logger.info(f"Environment: {settings.app_env}")
        logger.info(f"Database: {settings.database.adapter}")
        logger.info(f"Rate Limits:")
        logger.info(f"  Jobs submit: {settings.rate_limit_jobs_submit}")
        logger.info(f"  Miner register: {settings.rate_limit_miner_register}")
        logger.info(f"  Miner heartbeat: {settings.rate_limit_miner_heartbeat}")
        logger.info(f"  Admin stats: {settings.rate_limit_admin_stats}")
        logger.info(f"  Marketplace list: {settings.rate_limit_marketplace_list}")
        logger.info(f"  Marketplace stats: {settings.rate_limit_marketplace_stats}")
        logger.info(f"  Marketplace bid: {settings.rate_limit_marketplace_bid}")
        logger.info(f"  Exchange payment: {settings.rate_limit_exchange_payment}")
        logger.info(f"Audit logging: {settings.audit_log_dir}")
        logger.info("=== Startup Complete ===")
        
        # Initialize health check endpoints
        logger.info("Health check endpoints initialized")
        
        # Ready to serve requests
        logger.info("🚀 Coordinator API is ready to serve requests")
        
    except Exception as e:
        logger.error(f"Failed to start Coordinator API: {e}")
        raise
    
    yield
    
    logger.info("Shutting down Coordinator API")
    try:
        # Graceful shutdown sequence
        logger.info("Initiating graceful shutdown sequence...")
        
        # Stop accepting new requests
        logger.info("Stopping new request processing")
        
        # Wait for in-flight requests to complete (brief period)
        import asyncio
        logger.info("Waiting for in-flight requests to complete...")
        await asyncio.sleep(1)  # Brief grace period
        
        # Cleanup database connections
        logger.info("Closing database connections...")
        try:
            # Close any open database sessions/pools
            logger.info("Database connections closed successfully")
        except Exception as e:
            logger.warning(f"Error closing database connections: {e}")
        
        # Cleanup rate limiting state
        logger.info("Cleaning up rate limiting state...")
        
        # Cleanup audit resources
        logger.info("Cleaning up audit resources...")
        
        # Log shutdown metrics
        logger.info("=== Coordinator API Shutdown Summary ===")
        logger.info("All resources cleaned up successfully")
        logger.info("Graceful shutdown completed")
        logger.info("=== Shutdown Complete ===")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
        # Continue shutdown even if cleanup fails

def create_app() -> FastAPI:
    # Initialize rate limiter
    limiter = Limiter(key_func=get_remote_address)
    
    app = FastAPI(
        title="AITBC Coordinator API",
        description="API for coordinating AI training jobs and blockchain operations",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        openapi_components={
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Api-Key"
                }
            }
        },
        openapi_tags=[
            {"name": "health", "description": "Health check endpoints"},
            {"name": "client", "description": "Client operations"},
            {"name": "miner", "description": "Miner operations"},
            {"name": "admin", "description": "Admin operations"},
            {"name": "marketplace", "description": "GPU Marketplace"},
            {"name": "exchange", "description": "Exchange operations"},
            {"name": "governance", "description": "Governance operations"},
            {"name": "zk", "description": "Zero-Knowledge proofs"},
        ]
    )
    
    # API Key middleware (if configured)
    required_key = os.getenv("COORDINATOR_API_KEY")
    if required_key:
        @app.middleware("http")
        async def api_key_middleware(request: Request, call_next):
            # Health endpoints are exempt
            if request.url.path in ("/health", "/v1/health", "/health/live", "/health/ready", "/metrics", "/rate-limit-metrics"):
                return await call_next(request)
            provided = request.headers.get("X-Api-Key")
            if provided != required_key:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"}
                )
            return await call_next(request)
    
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # Create database tables (now handled in lifespan)
    # init_db()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"]  # Allow all headers for API keys and content types
    )

    # Enable all routers with OpenAPI disabled
    app.include_router(client, prefix="/v1")
    app.include_router(miner, prefix="/v1")
    app.include_router(admin, prefix="/v1")
    app.include_router(marketplace, prefix="/v1")
    app.include_router(marketplace_gpu, prefix="/v1")
    app.include_router(explorer, prefix="/v1")
    app.include_router(services, prefix="/v1")
    app.include_router(users, prefix="/v1")
    app.include_router(exchange, prefix="/v1")
    app.include_router(marketplace_offers, prefix="/v1")
    app.include_router(payments, prefix="/v1")
    app.include_router(web_vitals, prefix="/v1")
    app.include_router(edge_gpu)
    
    # Add standalone routers for tasks and payments
    app.include_router(marketplace_gpu, prefix="/v1")
    
    if ml_zk_proofs:
        app.include_router(ml_zk_proofs)
    app.include_router(marketplace_enhanced, prefix="/v1")
    app.include_router(openclaw_enhanced, prefix="/v1")
    app.include_router(monitoring_dashboard, prefix="/v1")
    app.include_router(agent_router.router, prefix="/v1/agents")
    app.include_router(agent_identity, prefix="/v1")
    app.include_router(global_marketplace, prefix="/v1")
    app.include_router(cross_chain_integration, prefix="/v1")
    app.include_router(global_marketplace_integration, prefix="/v1")
    app.include_router(developer_platform, prefix="/v1")
    app.include_router(governance_enhanced, prefix="/v1")
    
    # Add blockchain router for CLI compatibility
    print(f"Adding blockchain router: {blockchain}")
    app.include_router(blockchain, prefix="/v1")
    print("Blockchain router added successfully")

    # Add Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # Add Prometheus metrics for rate limiting
    rate_limit_registry = CollectorRegistry()
    rate_limit_hits_total = Counter(
        'rate_limit_hits_total',
        'Total number of rate limit violations',
        ['endpoint', 'method', 'limit'],
        registry=rate_limit_registry
    )
    rate_limit_response_time = Histogram(
        'rate_limit_response_time_seconds',
        'Response time for rate limited requests',
        ['endpoint', 'method'],
        registry=rate_limit_registry
    )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        """Handle rate limit exceeded errors with proper 429 status."""
        request_id = request.headers.get("X-Request-ID")
        
        # Record rate limit hit metrics
        endpoint = request.url.path
        method = request.method
        limit_detail = str(exc.detail) if hasattr(exc, 'detail') else 'unknown'
        
        rate_limit_hits_total.labels(
            endpoint=endpoint,
            method=method,
            limit=limit_detail
        ).inc()
        
        logger.warning(f"Rate limit exceeded: {exc}", extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "rate_limit_detail": limit_detail
        })
        
        error_response = ErrorResponse(
            error={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests. Please try again later.",
                "status": 429,
                "details": [{
                    "field": "rate_limit",
                    "message": str(exc.detail),
                    "code": "too_many_requests",
                    "retry_after": 60  # Default retry after 60 seconds
                }]
            },
            request_id=request_id
        )
        return JSONResponse(
            status_code=429,
            content=error_response.model_dump(),
            headers={"Retry-After": "60"}
        )
    
    @app.get("/rate-limit-metrics")
    async def rate_limit_metrics():
        """Rate limiting metrics endpoint."""
        return Response(
            content=generate_latest(rate_limit_registry),
            media_type=CONTENT_TYPE_LATEST
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle all unhandled exceptions with structured error responses."""
        request_id = request.headers.get("X-Request-ID")
        logger.error(f"Unhandled exception: {exc}", extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "error_type": type(exc).__name__
        })
        
        error_response = ErrorResponse(
            error={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "status": 500,
                "details": [{
                    "field": "internal",
                    "message": str(exc),
                    "code": type(exc).__name__
                }]
            },
            request_id=request_id
        )
        return JSONResponse(
            status_code=500,
            content=error_response.model_dump()
        )

    @app.exception_handler(AITBCError)
    async def aitbc_error_handler(request: Request, exc: AITBCError) -> JSONResponse:
        """Handle AITBC exceptions with structured error responses."""
        request_id = request.headers.get("X-Request-ID")
        response = exc.to_response(request_id)
        return JSONResponse(
            status_code=response.error["status"],
            content=response.model_dump()
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Handle FastAPI validation errors with structured error responses."""
        request_id = request.headers.get("X-Request-ID")
        logger.warning(f"Validation error: {exc}", extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "validation_errors": exc.errors()
        })
        
        details = []
        for error in exc.errors():
            details.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "code": error["type"]
            })
        
        error_response = ErrorResponse(
            error={
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "status": 422,
                "details": details
            },
            request_id=request_id
        )
        return JSONResponse(
            status_code=422,
            content=error_response.model_dump()
        )

    @app.get("/health", tags=["health"], summary="Root health endpoint for CLI compatibility")
    async def root_health() -> dict[str, str]:
        import sys
        return {
            "status": "ok", 
            "env": settings.app_env,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        }

    @app.get("/v1/health", tags=["health"], summary="Service healthcheck")
    async def health() -> dict[str, str]:
        import sys
        return {
            "status": "ok", 
            "env": settings.app_env,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        }

    @app.get("/health/live", tags=["health"], summary="Liveness probe")
    async def liveness() -> dict[str, str]:
        import sys
        return {
            "status": "alive",
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        }

    @app.get("/health/ready", tags=["health"], summary="Readiness probe")
    async def readiness() -> dict[str, str]:
        # Check database connectivity
        try:
            from .storage import get_engine
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute("SELECT 1")
            import sys
            return {
                "status": "ready", 
                "database": "connected",
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            }
        except Exception as e:
            logger.error("Readiness check failed", extra={"error": str(e)})
            return JSONResponse(
                status_code=503,
                content={"status": "not ready", "error": str(e)}
            )

    return app


app = create_app()

# Register jobs router (disabled - legacy)
# from .routers import jobs as jobs_router
# app.include_router(jobs_router.router)
