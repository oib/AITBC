"""Main FastAPI application for Edge API Service"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aitbc import get_logger

from .config import settings
from .storage import init_db
from .routers import islands, gpu, database, serve, metrics

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    # Startup
    logger.info("Starting Edge API Service")
    await init_db()
    logger.info("Database initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Edge API Service")


# Create FastAPI application
app = FastAPI(
    title="Edge API Service",
    description="REST API for AITBC island and edge operations",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "edge-api",
        "version": "0.1.0"
    }


# Readiness check endpoint
@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint"""
    # TODO: Check database connection, blockchain RPC, GPU service
    return {
        "status": "ready",
        "service": "edge-api",
        "version": "0.1.0"
    }


# Include routers
app.include_router(islands.router, prefix=f"{settings.api_prefix}/islands", tags=["islands"])
app.include_router(gpu.router, prefix=f"{settings.api_prefix}/gpu", tags=["gpu"])
app.include_router(database.router, prefix=f"{settings.api_prefix}/database", tags=["database"])
app.include_router(serve.router, prefix=f"{settings.api_prefix}/serve", tags=["serve"])
app.include_router(metrics.router, prefix=f"{settings.api_prefix}/metrics", tags=["metrics"])


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc)
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "edge_api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level=settings.log_level.lower()
    )
