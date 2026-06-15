"""Main FastAPI application for blockchain event bridge."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from aitbc.aitbc_logging import get_logger

from .bridge import BlockchainEventBridge
from .config import settings

logger = get_logger(__name__)
bridge_instance: BlockchainEventBridge | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager for startup/shutdown."""
    global bridge_instance
    logger.info("Starting %s...", settings.app_name)
    bridge_instance = BlockchainEventBridge(settings)
    await bridge_instance.start()
    logger.info("%s started successfully", settings.app_name)
    yield
    logger.info("Shutting down %s...", settings.app_name)
    if bridge_instance:
        await bridge_instance.stop()
    logger.info("%s shut down successfully", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="Bridge between AITBC blockchain events and hermes agent triggers",
    version="0.1.0",
    lifespan=lifespan,
)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health")
async def health_check() -> dict[str, object]:
    """Health check endpoint."""
    return {"status": "healthy", "bridge_running": bridge_instance is not None and bridge_instance.is_running}


@app.get("/")
async def root() -> dict[str, object]:
    """Root endpoint."""
    return {"service": settings.app_name, "version": "0.1.0", "status": "running"}
