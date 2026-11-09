"""
Bounty Router - Decentralized task market API

Provides endpoints for:
- Creating bounties
- Listing available bounties
- Claiming bounties
- Submitting solutions
- Verifying and releasing payments

#1337: reads are wired to the real BountyService + DB session. The
mutation endpoints are honest 501s — the flat request contract cannot
express what BountyService.create_bounty requires (tier, performance
criteria, ZK-proof flags, deadline semantics), the service has no
claim step and no payment/escrow integration, and the previous
implementation returned fabricated success for any bounty_id (claim and
verify "succeeded" on nonexistent bounties with no auth at all).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, col, select

from aitbc.rate_limiting import rate_limit

from ....storage import get_session
from ..domain.bounty import Bounty, BountyStatus
from ..services.bounty_service import BountyService

router = APIRouter(prefix="/bounty", tags=["bounty"])


class CreateBountyRequest(BaseModel):
    """Request to create a bounty"""

    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=10)
    creator: str
    reward: int = Field(..., gt=0)
    deadline: str | None = None
    requirements: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ClaimBountyRequest(BaseModel):
    """Request to claim a bounty"""

    bounty_id: str
    hunter: str


class SubmitSolutionRequest(BaseModel):
    """Request to submit a solution"""

    bounty_id: str
    hunter: str
    solution_url: str
    notes: str | None = None


class VerifySolutionRequest(BaseModel):
    """Request to verify a solution"""

    bounty_id: str
    verifier: str
    approved: bool
    feedback: str | None = None


def _not_implemented() -> HTTPException:
    return HTTPException(
        status_code=501,
        detail=(
            "Bounty mutations are not implemented on this surface: the flat contract "
            "cannot express BountyService requirements (tier, performance criteria, "
            "zk-proof flags) and the service has no claim step or payment integration. "
            "See issue #1337."
        ),
    )


@router.post("/create", summary="Create a new bounty")
@rate_limit(rate=20, per=60)
def create_bounty(request: Request, req: CreateBountyRequest) -> dict[str, Any]:
    """Create a new bounty task — honest 501 (see module docstring / #1337)"""
    raise _not_implemented()


@router.get("/list", summary="List available bounties")
@rate_limit(rate=100, per=60)
async def list_bounties(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    status: str | None = None,
    tag: str | None = None,
) -> dict[str, Any]:
    """List bounties with optional status/tag filtering (real DB reads)"""
    bounty_status: BountyStatus | None = None
    if status is not None:
        try:
            bounty_status = BountyStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown bounty status: {status}") from None
    bounties = await BountyService(session).get_bounties(
        status=bounty_status,
        tags=[tag] if tag else None,
    )
    return {
        "bounties": [b.model_dump(mode="json") for b in bounties],
        "count": len(bounties),
        "filters": {"status": status, "tag": tag},
    }


# Declared above the parameterized routes below on purpose. Starlette matches in
# declaration order, so moving this back down makes it unreachable -- the request
# binds the literal segment as the path parameter instead, and the caller gets a
# plausible-looking answer from the wrong handler rather than a routing error.
# Pinned by tests/security/test_no_unreachable_routes.py.
@router.get("/stats", summary="Get bounty statistics")
@rate_limit(rate=50, per=60)
async def get_stats(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get platform-wide bounty statistics (real aggregates)"""
    stats = await BountyService(session).get_bounty_stats()
    return {
        "total_bounties": stats.total_bounties,
        "open_bounties": stats.active_bounties,
        "completed_bounties": stats.completed_bounties,
        "expired_bounties": stats.expired_bounties,
        "disputed_bounties": stats.disputed_bounties,
        "total_reward": str(stats.total_rewards_paid),
        "total_value_locked": str(stats.total_value_locked),
        "total_fees_collected": str(stats.total_fees_collected),
        "success_rate": stats.success_rate,
        "tier_distribution": stats.tier_distribution,
        "period": {"start": stats.period_start.isoformat(), "end": stats.period_end.isoformat(), "type": stats.period_type},
    }


@router.get("/health", summary="Health check for bounty service")
def bounty_health(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Check bounty service health (real row count)"""
    total = session.execute(select(func.count(col(Bounty.bounty_id)))).scalar_one()
    return {"status": "healthy", "total_bounties": total, "service": "bounty"}


@router.get("/{bounty_id}", summary="Get bounty details")
@rate_limit(rate=100, per=60)
async def get_bounty(
    request: Request,
    bounty_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get detailed information about a specific bounty (real lookup, 404 on miss)"""
    bounty = await BountyService(session).get_bounty(bounty_id)
    if bounty is None:
        raise HTTPException(status_code=404, detail="Bounty not found")
    return bounty.model_dump(mode="json")


@router.post("/claim", summary="Claim a bounty")
@rate_limit(rate=20, per=60)
def claim_bounty(request: Request, req: ClaimBountyRequest) -> dict[str, Any]:
    """Claim an open bounty — honest 501 (BountyService has no claim step; see #1337)"""
    raise _not_implemented()


@router.post("/submit", summary="Submit solution")
@rate_limit(rate=30, per=60)
def submit_solution(request: Request, req: SubmitSolutionRequest) -> dict[str, Any]:
    """Submit a solution — honest 501 (see #1337)"""
    raise _not_implemented()


@router.post("/verify", summary="Verify solution")
@rate_limit(rate=20, per=60)
def verify_solution(request: Request, req: VerifySolutionRequest) -> dict[str, Any]:
    """Verify a solution — honest 501 (payout-affecting; see #1337)"""
    raise _not_implemented()
