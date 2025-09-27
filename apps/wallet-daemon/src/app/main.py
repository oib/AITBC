from __future__ import annotations

from fastapi import FastAPI

from .api_jsonrpc import router as jsonrpc_router
from .api_rest import router as receipts_router
from .settings import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    app.include_router(receipts_router)
    app.include_router(jsonrpc_router)
    return app


app = create_app()
