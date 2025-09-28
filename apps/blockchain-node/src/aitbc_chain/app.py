from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import APIRouter, FastAPI
from fastapi.responses import PlainTextResponse

from .config import settings
from .database import init_db
from .gossip import create_backend, gossip_broker
from .metrics import metrics_registry
from .rpc.router import router as rpc_router
from .rpc.websocket import router as websocket_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    backend = create_backend(
        settings.gossip_backend,
        broadcast_url=settings.gossip_broadcast_url,
    )
    await gossip_broker.set_backend(backend)
    try:
        yield
    finally:
        await gossip_broker.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="AITBC Blockchain Node", version="0.1.0", lifespan=lifespan)
    app.include_router(rpc_router, prefix="/rpc", tags=["rpc"])
    app.include_router(websocket_router, prefix="/rpc")
    metrics_router = APIRouter()

    @metrics_router.get("/metrics", response_class=PlainTextResponse, tags=["metrics"], summary="Prometheus metrics")
    async def metrics() -> str:
        return metrics_registry.render_prometheus()

    app.include_router(metrics_router)

    return app


app = create_app()
