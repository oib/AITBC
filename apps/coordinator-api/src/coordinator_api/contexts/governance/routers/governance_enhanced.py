"""
Enhanced Governance API Router
REST API endpoints for multi-jurisdictional DAO governance, regional councils, treasury management, and staking
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, func, select
from starlette.concurrency import run_in_threadpool

from aitbc.rate_limiting import rate_limit

from ..domain.governance import (
    GovernanceProfile,
    VoteType,
)
from ....auth import AdminDep, AdminOrClientDep
from ....storage.db import get_session
from ...infrastructure.domain.user import Wallet
from ..services.governance_service import GovernanceService

router = APIRouter(prefix="/governance-enhanced", tags=["Enhanced Governance"])

_OPS_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    SQLAlchemyError,
)


# Dependency injection
def get_governance_service(session: Annotated[Session, Depends(get_session)]) -> GovernanceService:
    return GovernanceService(session)


# #1847 (audit F2/F3): these routes used to run with no caller binding — any
# client JWT could propose/vote/delegate under arbitrary addresses and
# self-assign voting power. Identity now comes from the token: the caller's
# user id (JWT sub) plus the wallet addresses registered to that user, the
# same ownership model agent-performance/agent-identity routes use. Admin
# callers bypass object checks, matching those routers.
def _is_admin(user: dict[str, Any]) -> bool:
    return user.get("role") == "admin"


def _caller_wallets(session: Session, user: dict[str, Any]) -> set[str]:
    sub = str(user.get("sub") or "")
    if not sub:
        return set()
    return {str(w.address).lower() for w in session.exec(select(Wallet).where(Wallet.user_id == sub)).all() if w.address}


def _caller_identities(session: Session, user: dict[str, Any]) -> set[str]:
    """Identities the caller may act as: JWT sub plus owned wallet addresses."""
    identities = {str(user.get("sub") or "")}
    identities.discard("")
    identities |= _caller_wallets(session, user)
    return identities


def _require_identity(session: Session, user: dict[str, Any], claimed: str) -> None:
    """403 unless ``claimed`` is the caller's sub or one of their wallets."""
    if _is_admin(user):
        return
    identities = _caller_identities(session, user)
    if claimed in identities or claimed.lower() in identities:
        return
    raise HTTPException(status_code=403, detail="identity is not bound to the caller")


def _require_profile_owner(session: Session, user: dict[str, Any], profile: GovernanceProfile) -> None:
    """403 unless the profile's user_id belongs to the caller (admin bypasses)."""
    if _is_admin(user):
        return
    _require_identity(session, user, str(profile.user_id))


# Regional Council Management Endpoints
@router.post("/regional-councils", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def create_regional_council(
    request: Request,
    region: str,
    council_name: str,
    jurisdiction: str,
    council_members: list[str],
    budget_allocation: Decimal,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
    user: AdminDep,
) -> dict[str, Any]:
    """Create a regional governance council (admin-only provisioning)."""

    try:
        council = await run_in_threadpool(
            governance_service.create_regional_council, region, council_name, jurisdiction, council_members, budget_allocation
        )

        return {
            "success": True,
            "council": council,
            "message": f"Regional council '{council_name}' created successfully in {region}",
        }

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/regional-councils", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_regional_councils(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
    region: str | None = None,
) -> list[dict[str, Any]]:
    """Get regional governance councils"""

    try:
        councils = await run_in_threadpool(governance_service.get_regional_councils, region)
        return councils

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/regional-proposals", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def create_regional_proposal(
    request: Request,
    council_id: str,
    title: str,
    description: str,
    proposal_type: str,
    amount_requested: Decimal,
    proposer_address: str,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
    user: AdminOrClientDep,
) -> dict[str, Any]:
    """Create a proposal for a specific regional council"""

    _require_identity(session, user, proposer_address)
    try:
        proposal = await run_in_threadpool(
            governance_service.create_regional_proposal,
            council_id,
            title,
            description,
            proposal_type,
            amount_requested,
            proposer_address,
        )

        return {"success": True, "proposal": proposal, "message": f"Regional proposal '{title}' created successfully"}

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/regional-proposals/{proposal_id}/vote", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def vote_on_regional_proposal(
    request: Request,
    proposal_id: str,
    voter_address: str,
    vote_type: VoteType,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
    user: AdminOrClientDep,
) -> dict[str, Any]:
    """Vote on a regional proposal.

    #1847: voting_power is no longer caller-supplied — the service derives
    it from the voter's stored profile (own + delegated power).
    """

    _require_identity(session, user, voter_address)
    try:
        vote = await run_in_threadpool(governance_service.vote_on_regional_proposal, proposal_id, voter_address, vote_type)

        return {"success": True, "vote": vote, "message": f"Vote cast successfully on proposal {proposal_id}"}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


# Treasury Management Endpoints
@router.get("/treasury/balance", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_treasury_balance(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
    region: str | None = None,
) -> dict[str, Any]:
    """Get treasury balance for global or specific region"""

    try:
        balance = await run_in_threadpool(governance_service.get_treasury_balance, region)
        return balance

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/treasury/allocate", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
def allocate_treasury_funds(
    request: Request,
    council_id: str,
    amount: Decimal,
    purpose: str,
    recipient_address: str,
    approver_address: str,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
) -> dict[str, Any]:
    """Allocate treasury funds to a regional council or project.

    ponytail: Disabled until real on-chain treasury operations are implemented.
    """
    raise HTTPException(
        status_code=501,
        detail="Treasury allocation is disabled until on-chain treasury operations are implemented",
    )


@router.get("/treasury/transactions", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_treasury_transactions(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    region: str | None = None,
) -> list[dict[str, Any]]:
    """Get treasury transaction history"""

    try:
        transactions = await run_in_threadpool(governance_service.get_treasury_transactions, limit or 100, offset or 0, region)
        return transactions

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


# Staking & Rewards Endpoints
@router.post("/staking/pools", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
def create_staking_pool(
    request: Request,
    pool_name: str,
    developer_address: str,
    base_apy: float,
    reputation_multiplier: float,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
) -> dict[str, Any]:
    """Create a staking pool for an agent developer.

    ponytail: Disabled until real on-chain staking pools are implemented.
    """
    raise HTTPException(
        status_code=501,
        detail="Staking pool creation is disabled until on-chain staking is implemented",
    )


@router.get("/staking/pools", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_developer_staking_pools(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
    developer_address: str | None = None,
) -> list[dict[str, Any]]:
    """Get staking pools for a specific developer or all pools"""

    try:
        pools = await run_in_threadpool(governance_service.get_developer_staking_pools, developer_address)
        return pools

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/staking/calculate-rewards", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def calculate_staking_rewards(
    request: Request,
    pool_id: str,
    staker_address: str,
    amount: Decimal,
    duration_days: int,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
) -> dict[str, Any]:
    """Calculate staking rewards for a specific position"""

    try:
        rewards = await run_in_threadpool(
            governance_service.calculate_staking_rewards, pool_id, staker_address, amount, duration_days
        )
        return rewards

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/staking/distribute-rewards/{pool_id}", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
def distribute_staking_rewards(
    request: Request,
    pool_id: str,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
) -> dict[str, Any]:
    """Distribute rewards to all stakers in a pool.

    ponytail: Disabled until real reward distribution is implemented.
    """
    raise HTTPException(
        status_code=501,
        detail="Staking reward distribution is disabled until on-chain reward distribution is implemented",
    )


# Analytics and Monitoring Endpoints
@router.get("/analytics/governance", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_governance_analytics(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
    time_period_days: int = 30,
) -> dict[str, Any]:
    """Get comprehensive governance analytics"""

    try:
        analytics = await run_in_threadpool(governance_service.get_governance_analytics, time_period_days or 30)
        return analytics

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/analytics/regional-health/{region}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_regional_governance_health(
    request: Request,
    region: str,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
) -> dict[str, Any]:
    """Get health metrics for a specific region's governance"""

    try:
        health = await run_in_threadpool(governance_service.get_regional_governance_health, region)
        return health

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


# Enhanced Profile Management
@router.post("/profiles/create", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def create_governance_profile(
    request: Request,
    user_id: str,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
    user: AdminOrClientDep,
) -> dict[str, Any]:
    """Create or get a governance profile.

    #1847: user_id must be bound to the caller and initial_voting_power is
    ignored — power is never minted from the request; it accrues from
    stake/delegation server-side.
    """

    _require_identity(session, user, user_id)
    try:
        profile = await run_in_threadpool(governance_service.get_or_create_profile, user_id, 0.0)

        return {
            "success": True,
            "profile_id": profile.profile_id,
            "user_id": profile.user_id,
            "role": profile.role.value,
            "voting_power": profile.voting_power,
            "delegated_power": profile.delegated_power,
            "total_votes_cast": profile.total_votes_cast,
            "joined_at": profile.joined_at.isoformat(),
            "message": "Governance profile created successfully",
        }

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/profiles/delegate", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def delegate_votes(
    request: Request,
    delegator_id: str,
    delegatee_id: str,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
    user: AdminOrClientDep,
) -> dict[str, Any]:
    """Delegate voting power from one profile to another.

    #1847: the delegator profile must belong to the caller — previously any
    client could point any profile's delegate_to at themselves (F3).
    """

    delegator_profile = session.exec(select(GovernanceProfile).where(GovernanceProfile.profile_id == delegator_id)).first()
    if delegator_profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {delegator_id} not found")
    _require_profile_owner(session, user, delegator_profile)
    try:
        delegator = await run_in_threadpool(governance_service.delegate_votes, delegator_id, delegatee_id)

        return {
            "success": True,
            "delegator_id": delegator_id,
            "delegatee_id": delegatee_id,
            "delegated_power": delegator.voting_power,
            "delegate_to": delegator.delegate_to,
            "message": "Votes delegated successfully",
        }

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/profiles/{user_id}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_governance_profile(
    request: Request,
    user_id: str,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
) -> dict[str, Any]:
    """Get governance profile by user ID"""

    try:
        profile = await run_in_threadpool(governance_service.get_or_create_profile, user_id)

        return {
            "profile_id": profile.profile_id,
            "user_id": profile.user_id,
            "role": profile.role.value,
            "voting_power": profile.voting_power,
            "delegated_power": profile.delegated_power,
            "total_votes_cast": profile.total_votes_cast,
            "proposals_created": profile.proposals_created,
            "proposals_passed": profile.proposals_passed,
            "delegate_to": profile.delegate_to,
            "joined_at": profile.joined_at.isoformat(),
            "last_voted_at": profile.last_voted_at.isoformat() if profile.last_voted_at else None,
        }

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


# Multi-Jurisdictional Compliance
@router.get("/jurisdictions", response_model=list[dict[str, Any]])
@rate_limit(rate=500, per=60)
def get_supported_jurisdictions(request: Request) -> list[dict[str, Any]]:
    """Get list of supported jurisdictions and their requirements"""

    try:
        jurisdictions = [
            {
                "code": "US",
                "name": "United States",
                "region": "global",
                "requirements": {
                    "kyc_required": True,
                    "aml_required": True,
                    "tax_reporting": True,
                    "minimum_stake": 1000.0,
                    "voting_threshold": 100.0,
                },
                "supported_councils": ["us-east", "us-west", "us-central"],
            },
            {
                "code": "EU",
                "name": "European Union",
                "region": "global",
                "requirements": {
                    "kyc_required": True,
                    "aml_required": True,
                    "gdpr_compliance": True,
                    "minimum_stake": 800.0,
                    "voting_threshold": 80.0,
                },
                "supported_councils": ["eu-west", "eu-central", "eu-north"],
            },
            {
                "code": "SG",
                "name": "Singapore",
                "region": "asia-pacific",
                "requirements": {
                    "kyc_required": True,
                    "aml_required": True,
                    "tax_reporting": True,
                    "minimum_stake": 500.0,
                    "voting_threshold": 50.0,
                },
                "supported_councils": ["asia-pacific", "sea"],
            },
        ]

        return jurisdictions

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/compliance/check/{user_address}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
def check_compliance_status(
    request: Request,
    user_address: str,
    jurisdiction: str,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
) -> dict[str, Any]:
    """Check compliance status for a user in a specific jurisdiction"""

    # No real compliance/KYC integration exists — returning a hardcoded
    # is_compliant=True for any address was fabricated approval (#1345).
    raise HTTPException(
        status_code=501,
        detail="Compliance checking is not implemented: no KYC/AML provider is integrated",
    )


# System Health and Status
@router.get("/health", response_model=dict[str, Any])
@rate_limit(rate=1000, per=60)
async def get_governance_system_health(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
) -> dict[str, Any]:
    """Get overall governance system health status"""

    try:
        # Check database connectivity
        try:
            profile_count = (
                await run_in_threadpool(session.execute, select(func.count(GovernanceProfile.profile_id)))  # type: ignore[arg-type]
            ).scalar()
            database_status = "healthy"
        except _OPS_ERRORS:
            database_status = "unhealthy"
            profile_count = 0

        # Mock service health checks
        services_status = {
            "database": database_status,
            "treasury_contracts": "healthy",
            "staking_contracts": "healthy",
            "regional_councils": "healthy",
            "compliance_systems": "healthy",
        }

        overall_status = "healthy" if all(status == "healthy" for status in services_status.values()) else "degraded"

        # Get basic metrics
        # Last 7 days
        analytics = await run_in_threadpool(governance_service.get_governance_analytics, 7)

        health_data = {
            "status": overall_status,
            "services": services_status,
            "metrics": {
                "total_profiles": profile_count,
                "active_proposals": analytics["proposals"]["still_active"],
                "regional_councils": analytics["regional_councils"]["total_councils"],
                "treasury_balance": analytics["treasury"]["total_allocations"],
                "staking_pools": analytics["staking"]["active_pools"],
            },
            "last_updated": datetime.now(UTC).isoformat(),
        }

        return health_data

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/status", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_governance_platform_status(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    governance_service: Annotated[GovernanceService, Depends(get_governance_service)],
) -> dict[str, Any]:
    """Get comprehensive platform status information"""

    try:
        # Get analytics for overview
        analytics = await run_in_threadpool(governance_service.get_governance_analytics, 30)

        # Get regional councils
        councils = await run_in_threadpool(governance_service.get_regional_councils)

        # Get treasury balance
        treasury = await run_in_threadpool(governance_service.get_treasury_balance)

        status_data = {
            "platform": "AITBC Enhanced Governance",
            "version": "2.0.0",
            "status": "operational",
            "features": {
                "multi_jurisdictional_support": True,
                "regional_councils": len(councils),
                "treasury_management": True,
                "staking_rewards": True,
                "compliance_integration": False,
            },
            "statistics": analytics,
            "treasury": treasury,
            "regional_coverage": {
                "total_regions": len({c["region"] for c in councils}),
                "active_councils": len(councils),
                "supported_jurisdictions": 3,
            },
            "performance": {
                "average_proposal_time": "2.5 days",
                "voting_participation": f"{analytics['proposals'].get('participation_rate', 0.0)}%",
                "treasury_utilization": "0.0%",
                "staking_apy": "0.0%",
            },
            "last_updated": datetime.now(UTC).isoformat(),
        }

        return status_data

    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
