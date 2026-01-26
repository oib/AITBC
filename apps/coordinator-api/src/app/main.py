from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from .config import settings
from .database import create_db_and_tables
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
)
from .routers import zk_applications
from .routers.governance import router as governance
from .routers.partners import router as partners
from .storage.models_governance import GovernanceProposal, ProposalVote, TreasuryTransaction, GovernanceParameter


def create_app() -> FastAPI:
    app = FastAPI(
        title="AITBC Coordinator API",
        version="0.1.0",
        description="Stage 1 coordinator service handling job orchestration between clients and miners.",
    )
    
    # Create database tables
    init_db()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

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

    # Add Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    @app.get("/v1/health", tags=["health"], summary="Service healthcheck")
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    return app


app = create_app()
