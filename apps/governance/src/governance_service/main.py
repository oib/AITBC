"""
Governance Service main application
Manages governance operations
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.middleware import (
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
)

from .services.governance_service import GovernanceService
from .storage import get_session, init_db

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
    title="AITBC Governance Service", description="Manages governance operations", version="0.1.0", lifespan=lifespan
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_request_size=10 * 1024 * 1024)
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
            await session.execute("SELECT 1")
        return {"status": "ready", "service": "governance-service"}
    except Exception as e:
        logger.error("Readiness check failed: %s", e)
        return JSONResponse(status_code=503, content={"status": "not_ready", "service": "governance-service", "error": str(e)})


@app.get("/live")
async def live() -> dict[str, str]:
    """Liveness check - verifies service is not stuck"""
    return {"status": "alive", "service": "governance-service"}


@app.get("/v1/governance/status")
async def governance_status() -> dict[str, Any]:
    """Get governance status"""
    from .config import settings

    return {
        "status": "operational",
        "service": "governance-service",
        "message": "Governance service is running",
        "chain_id": settings.default_chain_id,
        "blockchain_rpc_url": settings.blockchain_rpc_url,
        "onchain_submission_enabled": settings.enable_onchain_submission,
        "voting_period_blocks": settings.voting_period_blocks,
        "quorum_percent": settings.quorum_percent,
        "approval_percent": settings.approval_percent,
        "timelock_blocks": settings.timelock_blocks,
    }


async def get_governance_service(session: Annotated[AsyncSession, Depends(get_session_dep)]) -> GovernanceService:
    """Get governance service instance"""
    from .clients.blockchain import BlockchainClient
    from .config import settings

    blockchain_client = BlockchainClient(rpc_url=settings.blockchain_rpc_url)
    return GovernanceService(session, blockchain_client=blockchain_client)


@app.get("/v1/governance/profiles")
async def get_profiles(
    role: str | None, user_id: str | None, svc: Annotated[GovernanceService, Depends(get_governance_service)]
):
    """Get governance profiles"""
    return await svc.list_profiles(role=role, user_id=user_id)


@app.get("/v1/governance/profiles/{profile_id}")
async def get_profile(profile_id: str, svc: Annotated[GovernanceService, Depends(get_governance_service)]):
    """Get a specific governance profile"""
    return await svc.get_profile(profile_id)


@app.post("/v1/governance/profiles")
async def create_profile(profile_data: dict[str, Any], svc: Annotated[GovernanceService, Depends(get_governance_service)]):
    """Create a new governance profile"""
    return await svc.create_profile(profile_data)


@app.get("/v1/governance/proposals")
async def get_proposals(
    status: str | None,
    category: str | None,
    proposer_id: str | None,
    svc: Annotated[GovernanceService, Depends(get_governance_service)],
):
    """Get governance proposals"""
    return await svc.list_proposals(status=status, category=category, proposer_id=proposer_id)


@app.get("/v1/governance/proposals/{proposal_id}")
async def get_proposal(proposal_id: str, svc: Annotated[GovernanceService, Depends(get_governance_service)]):
    """Get a specific proposal"""
    return await svc.get_proposal(proposal_id)


@app.post("/v1/governance/proposals")
async def create_proposal(proposal_data: dict[str, Any], svc: Annotated[GovernanceService, Depends(get_governance_service)]):
    """Create a new proposal"""
    return await svc.create_proposal(proposal_data)


@app.get("/v1/governance/votes")
async def get_votes(
    proposal_id: str | None,
    voter_id: str | None,
    svc: Annotated[GovernanceService, Depends(get_governance_service)],
):
    """Get votes"""
    return await svc.list_votes(proposal_id=proposal_id, voter_id=voter_id)


@app.post("/v1/governance/votes")
async def create_vote(vote_data: dict[str, Any], svc: Annotated[GovernanceService, Depends(get_governance_service)]):
    """Create a new vote"""
    return await svc.create_vote(vote_data)


@app.get("/v1/governance/treasury")
async def get_treasury(svc: Annotated[GovernanceService, Depends(get_governance_service)]):
    """Get DAO treasury"""
    return await svc.get_treasury()


@app.get("/v1/governance/analytics")
async def get_analytics(period: str | None, svc: Annotated[GovernanceService, Depends(get_governance_service)]):
    """Get governance analytics"""
    return await svc.get_analytics(period=period)


@app.post("/v1/governance/execute")
async def execute_proposal(
    proposal_id: str, executor_id: str, svc: Annotated[GovernanceService, Depends(get_governance_service)]
):
    """Execute a passed proposal (migrated from Coordinator API)"""
    logger.info("Executing proposal %s by executor %s", proposal_id, executor_id)
    proposal = await svc.get_proposal(proposal_id)
    if not proposal:
        return ({"error": "Proposal not found"}, 404)
    if proposal.get("status") != "passed":
        return ({"error": "Proposal must be in 'passed' status to execute"}, 400)
    try:
        execution_result = {
            "proposal_id": proposal_id,
            "executor_id": executor_id,
            "status": "executed",
            "executed_at": svc.get_current_timestamp(),
            "tx_hash": None,
        }
        await svc.update_proposal_status(proposal_id, "executed")
        logger.info("Successfully executed proposal %s", proposal_id)
        return execution_result
    except Exception as e:
        logger.error("Error executing proposal %s: %s", proposal_id, e)
        return ({"error": str(e)}, 500)


@app.get("/v1/governance/params")
async def get_governance_params():
    """Get governance parameters (migrated from Coordinator API)"""
    params = {
        "voting_period": 604800,
        "execution_delay": 86400,
        "quorum_threshold": 0.5,
        "approval_threshold": 0.6,
        "min_proposal_deposit": 1000,
        "max_proposals_per_period": 10,
        "emergency_quorum_threshold": 0.8,
        "voting_power_calculation": "token_weighted",
        "proposal_categories": ["parameter_change", "spending", "contract_upgrade", "emergency", "other"],
        "last_updated": "2026-06-02",
    }
    return params


@app.get("/v1/governance/voting-power/{address}")
async def get_voting_power(
    address: str, proposal_id: str | None, svc: Annotated[GovernanceService, Depends(get_governance_service)]
):
    """Get voting power for an address (migrated from Coordinator API)"""
    logger.info("Getting voting power for address %s", address)
    base_voting_power = 1000
    staking_bonus = 500
    participation_bonus = 100
    total_voting_power = base_voting_power + staking_bonus + participation_bonus
    has_voted = False
    if proposal_id:
        votes = await svc.list_votes(proposal_id=proposal_id, voter_id=address)
        has_voted = len(votes) > 0
    return {
        "address": address,
        "voting_power": total_voting_power,
        "breakdown": {
            "token_holdings": base_voting_power,
            "staking_bonus": staking_bonus,
            "participation_bonus": participation_bonus,
        },
        "has_voted": has_voted,
        "proposal_id": proposal_id,
        "calculated_at": svc.get_current_timestamp(),
    }


@app.post("/v1/transactions")
async def submit_transaction(transaction_data: dict[str, Any], session: Annotated[AsyncSession, Depends(get_session_dep)]):
    """Submit governance transaction"""
    from .domain.governance import Proposal, Vote

    transaction_type = transaction_data.get("type")
    action = transaction_data.get("action")
    if transaction_type != "governance":
        return ({"error": "Invalid transaction type for governance service"}, 400)
    try:
        if action == "propose":
            proposal = Proposal(**transaction_data)
            session.add(proposal)
        elif action == "vote":
            vote = Vote(**transaction_data)
            session.add(vote)
        else:
            return ({"error": f"Invalid action: {action}. Only 'propose' and 'vote' are currently supported"}, 400)
        await session.commit()
        return {"status": "success", "transaction_id": transaction_data.get("proposal_id") or transaction_data.get("vote_id")}
    except Exception as e:
        await session.rollback()
        logger.error("Transaction submission error: %s", e)
        return ({"error": str(e)}, 500)


@app.get("/v1/transactions")
async def get_transactions(
    transaction_type: str | None,
    action: str | None,
    status: str | None,
    island_id: str | None,
    session: Annotated[AsyncSession, Depends(get_session_dep)],
):
    """Query governance transactions"""
    from sqlalchemy import select

    from .domain.governance import Proposal, Vote

    try:
        transactions = []
        if action == "propose" or not action:
            result = await session.execute(select(Proposal))
            proposals = result.scalars().all()
            transactions.extend(
                [
                    {
                        "id": p.proposal_id,
                        "action": "propose",
                        "title": p.title,
                        "status": p.status,
                        "created_at": p.created_at.isoformat() if p.created_at else None,
                    }
                    for p in proposals
                ]
            )
        if action == "vote" or not action:
            result = await session.execute(select(Vote))
            votes = result.scalars().all()
            transactions.extend(
                [
                    {
                        "id": v.vote_id,
                        "action": "vote",
                        "proposal_id": v.proposal_id,
                        "vote_type": v.vote_type,
                        "created_at": v.created_at.isoformat() if v.created_at else None,
                    }
                    for v in votes
                ]
            )
        if status:
            transactions = [t for t in transactions if t.get("status") == status]
        if island_id:
            transactions = [t for t in transactions if t.get("island_id") == island_id]
        return transactions
    except Exception as e:
        logger.error("Transaction query error: %s", e)
        return ({"error": str(e)}, 500)


@app.post("/v1/governance/stake")
async def stake_tokens(
    staker_address: str, amount: int, lock_period_days: int, svc: Annotated[GovernanceService, Depends(get_governance_service)]
):
    """Stake tokens for enhanced voting power"""
    try:
        stake = await svc.stake_tokens(staker_address, amount, lock_period_days)
        return {
            "stake_id": stake.stake_id,
            "staker_address": staker_address,
            "amount_staked": amount,
            "lock_period_days": lock_period_days,
            "unstakes_at": stake.unstakes_at.isoformat() if stake.unstakes_at else None,
            "voting_power": await svc.calculate_voting_power(staker_address),
        }
    except Exception as e:
        logger.error("Staking error: %s", e)
        return ({"error": str(e)}, 500)


@app.get("/v1/governance/voting-power/{address}")
async def get_voting_power_v2(address: str, svc: Annotated[GovernanceService, Depends(get_governance_service)]):
    """Get voting power for an address (v0.4.12 enhanced)"""
    try:
        voting_power = await svc.calculate_voting_power(address)
        return {"address": address, "voting_power": voting_power, "calculated_at": svc.get_current_timestamp()}
    except Exception as e:
        logger.error("Voting power calculation error: %s", e)
        return ({"error": str(e)}, 500)


@app.post("/v1/governance/delegate")
async def delegate_voting_power(
    delegator_address: str,
    delegate_address: str,
    amount: int,
    svc: Annotated[GovernanceService, Depends(get_governance_service)],
):
    """Delegate voting power to another address"""
    try:
        delegation = await svc.delegate_voting_power(delegator_address, delegate_address, amount)
        return {
            "delegation_id": delegation.delegation_id,
            "delegator_address": delegator_address,
            "delegate_address": delegate_address,
            "voting_power": amount,
            "created_at": delegation.created_at.isoformat() if delegation.created_at else None,
        }
    except Exception as e:
        logger.error("Delegation error: %s", e)
        return ({"error": str(e)}, 500)


@app.post("/v1/governance/proposals/{proposal_id}/execute")
async def execute_proposal_v2(
    proposal_id: str,
    svc: Annotated[GovernanceService, Depends(get_governance_service)],
    executor_address: str = "",
):
    """Execute a passed proposal (v0.4.12 enhanced with logging + v0.7.3 on-chain submission)"""
    try:
        proposal = await svc.execute_proposal(proposal_id, executor_address=executor_address)
        if not proposal:
            return ({"error": "Proposal not found"}, 404)
        return {
            "proposal_id": proposal_id,
            "status": proposal.status,
            "executed_at": proposal.executed_at.isoformat() if proposal.executed_at else None,
            "tx_hash": proposal.execution_tx_hash,
        }
    except ValueError as e:
        return ({"error": str(e)}, 400)
    except Exception as e:
        logger.error("Proposal execution error: %s", e)
        return ({"error": str(e)}, 500)


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    from fastapi.responses import PlainTextResponse
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return PlainTextResponse(content=generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import os

    import uvicorn

    host = os.getenv("GOVERNANCE_BIND_HOST", "0.0.0.0")
    port = int(os.getenv("GOVERNANCE_BIND_PORT", "8105"))

    uvicorn.run(app, host=host, port=port)
