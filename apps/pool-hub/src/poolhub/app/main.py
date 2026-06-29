from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from aitbc.aitbc_logging import configure_logging, get_logger

from ..database import close_engine, create_engine
from ..redis_cache import close_redis, create_redis
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
    try:
        yield
    finally:
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
