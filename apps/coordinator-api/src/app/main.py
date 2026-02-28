from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from prometheus_client import make_asgi_app

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
    edge_gpu
)
from .routers.ml_zk_proofs import router as ml_zk_proofs
from .routers.community import router as community_router
from .routers.governance import router as new_governance_router
from .routers.partners import router as partners
from .routers.marketplace_enhanced_simple import router as marketplace_enhanced
from .routers.openclaw_enhanced_simple import router as openclaw_enhanced
from .routers.monitoring_dashboard import router as monitoring_dashboard
from .routers.multi_modal_rl import router as multi_modal_rl_router
from .storage.models_governance import GovernanceProposal, ProposalVote, TreasuryTransaction, GovernanceParameter
from .exceptions import AITBCError, ErrorResponse
from aitbc.logging import get_logger
from .config import settings
from .storage.db import init_db

logger = get_logger(__name__)


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events for the Coordinator API."""
    logger.info("Starting Coordinator API")
    
    try:
        # Initialize database
        init_db()
        logger.info("Database initialized successfully")
        
        # Validate configuration
        if settings.app_env == "production":
            logger.info("Production environment detected, validating configuration")
            # Configuration validation happens automatically via Pydantic validators
            
        # Initialize audit logging directory
        from pathlib import Path
        audit_dir = Path(settings.audit_log_dir)
        audit_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Audit logging directory: {audit_dir}")
        
        # Log service startup details
        logger.info(f"Coordinator API started on {settings.app_host}:{settings.app_port}")
        logger.info(f"Database adapter: {settings.database.adapter}")
        logger.info(f"Environment: {settings.app_env}")
        
    except Exception as e:
        logger.error(f"Failed to start Coordinator API: {e}")
        raise
    
    yield
    
    logger.info("Shutting down Coordinator API")
    try:
        # Cleanup resources
        logger.info("Coordinator API shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

def create_app() -> FastAPI:
    # Initialize rate limiter
    limiter = Limiter(key_func=get_remote_address)
    
    app = FastAPI(
        title="AITBC Coordinator API",
        version="0.1.0",
        description="Stage 1 coordinator service handling job orchestration between clients and miners.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
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

    app.include_router(client, prefix="/v1")
    app.include_router(miner, prefix="/v1")
    app.include_router(admin, prefix="/v1")
    app.include_router(marketplace, prefix="/v1")
    app.include_router(marketplace_gpu, prefix="/v1")
    app.include_router(exchange, prefix="/v1")
    app.include_router(users, prefix="/v1/users")
    app.include_router(services, prefix="/v1")
    app.include_router(payments, prefix="/v1")
    app.include_router(marketplace_offers, prefix="/v1")
    app.include_router(zk_applications.router, prefix="/v1")
    app.include_router(new_governance_router, prefix="/v1")
    app.include_router(community_router, prefix="/v1")
    app.include_router(partners, prefix="/v1")
    app.include_router(explorer, prefix="/v1")
    app.include_router(web_vitals, prefix="/v1")
    app.include_router(edge_gpu)
    app.include_router(ml_zk_proofs)
    app.include_router(marketplace_enhanced, prefix="/v1")
    app.include_router(openclaw_enhanced, prefix="/v1")
    app.include_router(monitoring_dashboard, prefix="/v1")
    app.include_router(multi_modal_rl_router, prefix="/v1")

    # Add Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

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
