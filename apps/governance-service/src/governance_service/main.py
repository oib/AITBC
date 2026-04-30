"""
Governance Service main application
Manages governance operations
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc import (
    configure_logging,
    get_logger,
    RequestIDMiddleware,
    PerformanceLoggingMiddleware,
    RequestValidationMiddleware,
    ErrorHandlerMiddleware,
)

from .storage import init_db, get_session
from .services.governance_service import GovernanceService

# Configure structured logging
configure_logging(level="INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle events for the Governance Service."""
    logger.info("Starting Governance Service")
    await init_db()
    yield
    logger.info("Shutting down Governance Service")


app = FastAPI(
    title="AITBC Governance Service",
    description="Manages governance operations",
    version="0.1.0",
    lifespan=lifespan,
)

# Add middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10*1024*1024)
app.add_middleware(ErrorHandlerMiddleware)


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str


@app.get("/health")
async def health() -> HealthResponse:
    """Health check endpoint"""
    return HealthResponse(status="healthy", service="governance-service")


@app.get("/governance/status")
async def governance_status() -> dict[str, str]:
    """Get governance status"""
    return {
        "status": "operational",
        "service": "governance-service",
        "message": "Governance service is running",
    }


async def get_governance_service(session: AsyncSession = Depends(get_session)) -> GovernanceService:
    """Get governance service instance"""
    return GovernanceService(session)


@app.get("/v1/governance/profiles")
async def get_profiles(
    role: str | None = None,
    user_id: str | None = None,
    svc: GovernanceService = Depends(get_governance_service),
):
    """Get governance profiles"""
    return svc.list_profiles(role=role, user_id=user_id)


@app.get("/v1/governance/profiles/{profile_id}")
async def get_profile(
    profile_id: str,
    svc: GovernanceService = Depends(get_governance_service),
):
    """Get a specific governance profile"""
    return svc.get_profile(profile_id)


@app.post("/v1/governance/profiles")
async def create_profile(
    profile_data: dict,
    svc: GovernanceService = Depends(get_governance_service),
):
    """Create a new governance profile"""
    return svc.create_profile(profile_data)


@app.get("/v1/governance/proposals")
async def get_proposals(
    status: str | None = None,
    category: str | None = None,
    proposer_id: str | None = None,
    svc: GovernanceService = Depends(get_governance_service),
):
    """Get governance proposals"""
    return svc.list_proposals(status=status, category=category, proposer_id=proposer_id)


@app.get("/v1/governance/proposals/{proposal_id}")
async def get_proposal(
    proposal_id: str,
    svc: GovernanceService = Depends(get_governance_service),
):
    """Get a specific proposal"""
    return svc.get_proposal(proposal_id)


@app.post("/v1/governance/proposals")
async def create_proposal(
    proposal_data: dict,
    svc: GovernanceService = Depends(get_governance_service),
):
    """Create a new proposal"""
    return svc.create_proposal(proposal_data)


@app.get("/v1/governance/votes")
async def get_votes(
    proposal_id: str | None = None,
    voter_id: str | None = None,
    svc: GovernanceService = Depends(get_governance_service),
):
    """Get votes"""
    return svc.list_votes(proposal_id=proposal_id, voter_id=voter_id)


@app.post("/v1/governance/votes")
async def create_vote(
    vote_data: dict,
    svc: GovernanceService = Depends(get_governance_service),
):
    """Create a new vote"""
    return svc.create_vote(vote_data)


@app.get("/v1/governance/treasury")
async def get_treasury(
    svc: GovernanceService = Depends(get_governance_service),
):
    """Get DAO treasury"""
    return svc.get_treasury()


@app.get("/v1/governance/analytics")
async def get_analytics(
    period: str = "monthly",
    svc: GovernanceService = Depends(get_governance_service),
):
    """Get governance analytics"""
    return await svc.get_analytics(period=period)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8105)
