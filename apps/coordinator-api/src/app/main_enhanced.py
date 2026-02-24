"""
Enhanced Main Application - Adds new enhanced routers to existing AITBC Coordinator API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from .config import settings
from .storage import init_db
from .routers import (
    client,
    miner,
    admin,
    marketplace,
    exchange,
    users,
    services,
    marketplace_offers,
    zk_applications,
    explorer,
    payments,
    web_vitals,
    edge_gpu
)
from .routers.ml_zk_proofs import router as ml_zk_proofs
from .routers.governance import router as governance
from .routers.partners import router as partners
from .routers.marketplace_enhanced_simple import router as marketplace_enhanced
from .routers.openclaw_enhanced_simple import router as openclaw_enhanced
from .storage.models_governance import GovernanceProposal, ProposalVote, TreasuryTransaction, GovernanceParameter
from .exceptions import AITBCError, ErrorResponse
from .logging import get_logger
from .config import settings
from .storage.db import init_db

logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="AITBC Coordinator API",
        version="0.1.0",
        description="Stage 1 coordinator service handling job orchestration between clients and miners.",
    )
    
    init_db()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"]  # Allow all headers for API keys and content types
    )

    # Include existing routers
    app.include_router(client, prefix="/v1")
    app.include_router(miner, prefix="/v1")
    app.include_router(admin, prefix="/v1")
    app.include_router(marketplace, prefix="/v1")
    app.include_router(exchange, prefix="/v1")
    app.include_router(users, prefix="/v1/users")
    app.include_router(services, prefix="/v1")
    app.include_router(payments, prefix="/v1")
    app.include_router(marketplace_offers, prefix="/v1")
    app.include_router(zk_applications.router, prefix="/v1")
    app.include_router(governance, prefix="/v1")
    app.include_router(partners, prefix="/v1")
    app.include_router(explorer, prefix="/v1")
    app.include_router(web_vitals, prefix="/v1")
    app.include_router(edge_gpu)
    app.include_router(ml_zk_proofs)
    
    # Include enhanced routers
    app.include_router(marketplace_enhanced, prefix="/v1")
    app.include_router(openclaw_enhanced, prefix="/v1")

    # Add Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    @app.get("/v1/health", tags=["health"], summary="Service healthcheck")
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    return app
