"""
Trading Service main application.

The route handlers have been split into feature routers under
``trading_service.routers``; this file is now a thin app factory that
wires them together with middleware and lifecycle events.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from aitbc.aitbc_logging import configure_logging, get_logger
from aitbc.middleware import (
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
)

from .config import settings
from .routers import (
    exchange_compat_router,
    inter_chain_router,
    legacy_trading_router,
    offers_router,
    settlement_router,
    subscriptions_router,
    system_router,
    transactions_router,
)
from .services.gossip_client import GossipClient
from .services.lease_tracker import OfferLeaseTracker
from .state import set_gossip_client, set_lease_tracker, shutdown
from .storage import init_db

configure_logging(level="INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the Trading Service."""
    logger.info("Starting Trading Service")
    await init_db()

    # v0.10.1 §B18: Initialize gossip client on startup
    try:
        gossip_client: Any = GossipClient(
            backend=settings.gossip_backend,
            redis_url=settings.gossip_broadcast_url,
        )
        await gossip_client.start()
        set_gossip_client(gossip_client)
        logger.info("Gossip client initialized (backend=%s)", settings.gossip_backend)
    except Exception as e:
        logger.warning("Failed to initialize gossip client: %s — using fallback", e)

    # v0.10.1 §B19: Initialize lease tracker on startup
    try:
        lease_tracker: Any = OfferLeaseTracker(redis_url=settings.lease_tracker_redis_url)
        await lease_tracker.start()
        set_lease_tracker(lease_tracker)
        logger.info("Offer lease tracker initialized")
    except Exception as e:
        logger.warning("Failed to initialize lease tracker: %s — using fallback", e)

    yield

    # v0.10.1 §B18/B19: Shutdown gossip client and lease tracker
    await shutdown()
    logger.info("Shutting down Trading Service")


app = FastAPI(
    title="AITBC Trading Service",
    description="Manages trading operations",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10 * 1024 * 1024)
app.add_middleware(ErrorHandlerMiddleware)

# Register feature routers in order of route specificity (static paths first).
app.include_router(system_router)
app.include_router(legacy_trading_router)
app.include_router(transactions_router)
app.include_router(exchange_compat_router)
app.include_router(inter_chain_router)
app.include_router(offers_router)
app.include_router(subscriptions_router)
app.include_router(settlement_router)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("TRADING_BIND_HOST", "0.0.0.0")  # nosec B104 - intentional service bind-all; AITBC's systemd-only (Docker-free) services bind broadly by design, real boundary is the firewall/reverse-proxy layer
    port = int(os.getenv("TRADING_BIND_PORT", "8104"))

    uvicorn.run(app, host=host, port=port, access_log=False)
