from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from aitbc.aitbc_logging import configure_logging, get_logger

from ..database import close_engine, create_engine, get_session_factory
from ..redis_cache import close_redis, create_redis
from ..services.billing_integration import BillingIntegrationScheduler
from ..services.sla_collector import SLACollectorScheduler
from ..settings import settings
from .routers import health_router, match_router, metrics_router
from .routers.parameters import router as parameters_router
from .routers.services import router as services_router
from .routers.sla import router as sla_router
from .routers.ui import router as ui_router
from .routers.validation import router as validation_router

configure_logging(level="INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_engine()
    create_redis()
    # Create tables on startup (idempotent — safe for existing DBs)
    from sqlalchemy import text

    from ..database import get_engine
    from ..models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Enable citext extension if available (optional, ignore errors)
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
        except Exception:
            pass  # Extension not available — not required
    logger.info("Database tables ensured")

    # V23-101: both schedulers were defined with start()/stop() and a loop, and
    # constructed nowhere -- so SLA metrics were only ever collected when someone
    # POSTed /v1/sla/metrics/collect by hand, and usage was only ever synced by a
    # hand-made POST to /v1/sla/billing/sync.  Both flags default off; see
    # settings.py for why each one is the operator's decision to make.
    schedulers: list[SLACollectorScheduler | BillingIntegrationScheduler] = []
    if settings.enable_sla_collection:
        sla_scheduler = SLACollectorScheduler(get_session_factory())
        await sla_scheduler.start(settings.sla_collection_interval_seconds)
        schedulers.append(sla_scheduler)
    if settings.enable_billing_sync:
        billing_scheduler = BillingIntegrationScheduler(get_session_factory())
        await billing_scheduler.start(settings.billing_sync_interval_hours)
        schedulers.append(billing_scheduler)
    if not schedulers:
        logger.info("No background schedulers enabled (POOLHUB_ENABLE_SLA_COLLECTION, POOLHUB_ENABLE_BILLING_SYNC)")

    try:
        yield
    finally:
        for scheduler in reversed(schedulers):
            await scheduler.stop()
        await close_engine()
        await close_redis()


app = FastAPI(**settings.asgi_kwargs(), lifespan=lifespan)
app.include_router(match_router, prefix="/v1")
app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(services_router, prefix="/v1")
app.include_router(ui_router)
app.include_router(validation_router, prefix="/v1")
app.include_router(sla_router, prefix="/v1")
app.include_router(parameters_router, prefix="/v1")


def create_app() -> FastAPI:
    return app
