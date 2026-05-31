"""Main FastAPI application for blockchain event bridge."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from aitbc.aitbc_logging import get_logger

from .bridge import BlockchainEventBridge
from .config import settings

logger = get_logger(__name__)

bridge_instance: BlockchainEventBridge | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    global bridge_instance

    logger.info(f"Starting {settings.app_name}...")

    # Initialize and start the bridge
    bridge_instance = BlockchainEventBridge(settings)
    await bridge_instance.start()

    logger.info(f"{settings.app_name} started successfully")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.app_name}...")
    if bridge_instance:
        await bridge_instance.stop()
    logger.info(f"{settings.app_name} shut down successfully")


app = FastAPI(
    title=settings.app_name,
    description="Bridge between AITBC blockchain events and hermes agent triggers",
    version="0.1.0",
    lifespan=lifespan,
)

# Add Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "bridge_running": bridge_instance is not None and bridge_instance.is_running,
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": settings.app_name,
        "version": "0.1.0",
        "status": "running",
    }
