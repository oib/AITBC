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
)
from .routers.governance import router as governance
from .routers.partners import router as partners
from .storage.models_governance import GovernanceProposal, ProposalVote, TreasuryTransaction, GovernanceParameter
from .exceptions import AITBCError, ErrorResponse
from .logging import get_logger


logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="AITBC Coordinator API",
        version="0.1.0",
        description="Stage 1 coordinator service handling job orchestration between clients and miners.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
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
    
    # Create database tables
    init_db()

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
    app.include_router(governance, prefix="/v1")
    app.include_router(partners, prefix="/v1")
    app.include_router(explorer, prefix="/v1")
    app.include_router(web_vitals, prefix="/v1")

    # Add Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

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
        return {"status": "ok", "env": settings.app_env}

    @app.get("/health/live", tags=["health"], summary="Liveness probe")
    async def liveness() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready", tags=["health"], summary="Readiness probe")
    async def readiness() -> dict[str, str]:
        # Check database connectivity
        try:
            from .storage import get_engine
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute("SELECT 1")
            return {"status": "ready", "database": "connected"}
        except Exception as e:
            logger.error("Readiness check failed", extra={"error": str(e)})
            return JSONResponse(
                status_code=503,
                content={"status": "not ready", "error": str(e)}
            )

    return app


app = create_app()
