"""
Enhanced Marketplace Service - FastAPI Entry Point
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from aitbc.rate_limiting import rate_limit

from .marketplace_enhanced_health import router as health_router
from .marketplace_enhanced_simple import router

app = FastAPI(
    title="AITBC Enhanced Marketplace Service",
    version="1.0.0",
    description="Enhanced marketplace with royalties, licensing, and verification",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8001",
        "http://localhost:8203",
        "http://localhost:8016",
        "http://localhost:8107",
        "http://127.0.0.1:8001",
        "http://127.0.0.1:8203",
        "http://127.0.0.1:8016",
        "http://127.0.0.1:8107",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include the router
app.include_router(router, prefix="/v1")

# Include health check router
app.include_router(health_router, tags=["health"])


@app.get("/health")
@rate_limit(rate=1000, per=60)
async def health(request: Request) -> dict[str, str]:
    return {"status": "ok", "service": "marketplace-enhanced"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8002)
