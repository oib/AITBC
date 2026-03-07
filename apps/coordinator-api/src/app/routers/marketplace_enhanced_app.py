from sqlalchemy.orm import Session
from typing import Annotated
"""
Enhanced Marketplace Service - FastAPI Entry Point
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from .marketplace_enhanced_simple import router
from .marketplace_enhanced_health import router as health_router
from ..storage import get_session

app = FastAPI(
    title="AITBC Enhanced Marketplace Service",
    version="1.0.0",
    description="Enhanced marketplace with royalties, licensing, and verification"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"]
)

# Include the router
app.include_router(router, prefix="/v1")

# Include health check router
app.include_router(health_router, tags=["health"])

@app.get("/health")
async def health():
    return {"status": "ok", "service": "marketplace-enhanced"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
