#!/usr/bin/env python3
"""AITBC Agent Management Service"""

import uvicorn
from fastapi import FastAPI
from aitbc import get_logger

# Local imports
from .core.config import settings
from .core.logging import setup_logging, get_logger
from .core.database import Base, get_engine, get_sessionmaker

# Setup logging
setup_logging(settings)
logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AITBC Agent Management API",
    description="AI agent lifecycle, orchestration, performance tracking, and security",
    version="0.1.0",
    debug=settings.debug
)

# Database setup
engine = get_engine(settings)
SessionLocal = get_sessionmaker(engine)

# Create tables on startup
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    logger.info("Agent Management service started")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Include routers
from .routers import (
    agent_router,
    agent_integration_router,
    agent_performance,
    agent_creativity,
    agent_security_router,
    services as agent_services_router
)

# Mount routers with prefix
app.include_router(agent_router.router, prefix=f"{settings.api_prefix}/agents")
app.include_router(agent_integration_router.router, prefix=f"{settings.api_prefix}/agents/integration")
app.include_router(agent_performance.router, prefix=f"{settings.api_prefix}/agents/performance")
app.include_router(agent_creativity.router, prefix=f"{settings.api_prefix}/agents/creativity")
app.include_router(agent_security_router.router, prefix=f"{settings.api_prefix}/agents/security")
app.include_router(agent_services_router.router, prefix=f"{settings.api_prefix}/services")

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": settings.service_name}

@app.get("/")
def root():
    return {"message": "Welcome to AITBC Agent Management Service"}

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug
    )
