from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..database import close_engine, create_engine
from ..redis_cache import close_redis, create_redis
from ..settings import settings
from .routers import health_router, match_router, metrics_router


@asynccontextmanager
async def lifespan(_: FastAPI):
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


def create_app() -> FastAPI:
    return app
