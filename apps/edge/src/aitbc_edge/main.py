"""Main FastAPI application for Edge API Service"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aitbc.aitbc_logging import get_logger

from .config import settings
from .routers import database_router as database
from .routers import gpu_router as gpu
from .routers import islands_router as islands
from .routers import metrics_router as metrics
from .routers import serve_router as serve
from .storage import init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager for startup/shutdown"""
    logger.info("Starting Edge API Service")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Edge API Service")


app = FastAPI(
    title="Edge API Service",
    description="REST API for AITBC island and edge operations",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint"""
    return {"status": "healthy", "service": "edge-api", "version": "0.1.0"}


@app.get("/ready")
async def readiness_check() -> dict[str, str]:
    """Readiness check endpoint"""
    return {"status": "ready", "service": "edge-api", "version": "0.1.0"}


app.include_router(islands, prefix=f"{settings.api_prefix}/islands", tags=["islands"])
app.include_router(gpu, prefix=f"{settings.api_prefix}/gpu", tags=["gpu"])
app.include_router(database, prefix=f"{settings.api_prefix}/database", tags=["database"])
app.include_router(serve, prefix=f"{settings.api_prefix}/serve", tags=["serve"])
app.include_router(metrics, prefix=f"{settings.api_prefix}/metrics", tags=["metrics"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler"""
    logger.error("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": "Internal error - see server logs"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "aitbc_edge.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
