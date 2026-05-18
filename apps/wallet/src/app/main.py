from __future__ import annotations

from fastapi import FastAPI
import uvicorn

import sys
sys.path.insert(0, "/opt/aitbc")

from aitbc.rate_limiting import RateLimitMiddleware

from .api_jsonrpc import router as jsonrpc_router
from .api_rest import router as receipts_router
from .settings import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    
    # Add rate limiting middleware
    app.add_middleware(
        RateLimitMiddleware,
        rate=100,
        per=60
    )
    
    app.include_router(receipts_router)
    app.include_router(jsonrpc_router)
    
    # Add health check endpoint
    @app.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "env": "dev",
            "python_version": "3.13.5"
        }
    
    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8015)
