"""
Governance Service main application
Manages governance operations
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
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


async def get_session_dep() -> AsyncIterator[AsyncSession]:
    """Get database session dependency"""
    async with get_session() as session:
        yield session


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str


@app.get("/health")
async def health() -> HealthResponse:
    """Health check endpoint"""
    return HealthResponse(status="healthy", service="governance-service")


@app.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness check - verifies database connectivity"""
    try:
        async with get_session() as session:
            # Test database connection
            await session.execute("SELECT 1")
        return {"status": "ready", "service": "governance-service"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": "governance-service", "error": str(e)},
        )


@app.get("/live")
async def live() -> dict[str, str]:
    """Liveness check - verifies service is not stuck"""
    return {"status": "alive", "service": "governance-service"}


@app.get("/governance/status")
async def governance_status() -> dict[str, str]:
    """Get governance status"""
    return {
        "status": "operational",
        "service": "governance-service",
        "message": "Governance service is running",
    }


async def get_governance_service(session: AsyncSession = Depends(get_session_dep)) -> GovernanceService:
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


@app.post("/v1/transactions")
async def submit_transaction(transaction_data: dict, session: AsyncSession = Depends(get_session_dep)):
    """Submit governance transaction"""
    from .domain.governance import Proposal, Vote
    
    # Validate transaction type
    transaction_type = transaction_data.get('type')
    action = transaction_data.get('action')
    
    if transaction_type != 'governance':
        return {"error": "Invalid transaction type for governance service"}, 400
    
    try:
        if action == 'propose':
            proposal = Proposal(**transaction_data)
            session.add(proposal)
        elif action == 'vote':
            vote = Vote(**transaction_data)
            session.add(vote)
        else:
            return {"error": f"Invalid action: {action}. Only 'propose' and 'vote' are currently supported"}, 400
        
        await session.commit()
        return {"status": "success", "transaction_id": transaction_data.get('proposal_id') or transaction_data.get('vote_id')}
    except Exception as e:
        await session.rollback()
        logger.error(f"Transaction submission error: {e}")
        return {"error": str(e)}, 500


@app.get("/v1/transactions")
async def get_transactions(
    transaction_type: str | None = None,
    action: str | None = None,
    status: str | None = None,
    island_id: str | None = None,
    session: AsyncSession = Depends(get_session_dep),
):
    """Query governance transactions"""
    from .domain.governance import Proposal, Vote
    from sqlalchemy import select
    
    try:
        transactions = []
        
        # Query proposals
        if action == 'propose' or not action:
            result = await session.execute(select(Proposal))
            proposals = result.scalars().all()
            transactions.extend([{
                "id": p.proposal_id,
                "action": "propose",
                "title": p.title,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None
            } for p in proposals])
        
        # Query votes
        if action == 'vote' or not action:
            result = await session.execute(select(Vote))
            votes = result.scalars().all()
            transactions.extend([{
                "id": v.vote_id,
                "action": "vote",
                "proposal_id": v.proposal_id,
                "vote_type": v.vote_type,
                "created_at": v.created_at.isoformat() if v.created_at else None
            } for v in votes])
        
        # Apply filters
        if status:
            transactions = [t for t in transactions if t.get('status') == status]
        if island_id:
            transactions = [t for t in transactions if t.get('island_id') == island_id]
        
        return transactions
    except Exception as e:
        logger.error(f"Transaction query error: {e}")
        return {"error": str(e)}, 500


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8105)
