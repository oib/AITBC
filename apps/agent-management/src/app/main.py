#!/usr/bin/env python3
"""AITBC Agent Management Service"""

from collections.abc import Generator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import configure_logging, get_logger

# Local imports
from .core.config import settings
from .core.database import Base, get_engine, get_sessionmaker

# Setup logging
configure_logging(level=settings.log_level if hasattr(settings, "log_level") else "INFO")
logger = get_logger(__name__)

# Database setup
engine = get_engine(settings)
SessionLocal = get_sessionmaker(engine)


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    logger.info("Agent Management service started")
    yield
    # Shutdown
    logger.info("Agent Management service stopped")


# Create FastAPI app
app = FastAPI(
    title="AITBC Agent Management API",
    description="AI agent lifecycle, orchestration, performance tracking, and security",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)


# Dependency
def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Include routers
from .routers import (  # noqa: E402
    # agent_creativity_router,  # Temporarily disabled due to missing dependencies
    # agent_integration_router,  # Temporarily disabled due to missing dependencies
    # agent_performance_router,  # Temporarily disabled due to missing dependencies
    agent_router,
    # agent_security_router,  # Temporarily disabled due to missing dependencies
    # services_router,  # Temporarily disabled due to missing dependencies
)

# Mount routers with prefix
app.include_router(agent_router, prefix=f"{settings.api_prefix}/agents")
# app.include_router(agent_integration_router, prefix=f"{settings.api_prefix}/agents/integration")
# app.include_router(agent_performance_router, prefix=f"{settings.api_prefix}/agents/performance")
# app.include_router(agent_creativity_router, prefix=f"{settings.api_prefix}/agents/creativity")
# app.include_router(agent_security_router, prefix=f"{settings.api_prefix}/agents/security")
# app.include_router(services_router, prefix=f"{settings.api_prefix}/services")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": settings.service_name}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Welcome to AITBC Agent Management Service"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=settings.debug)
