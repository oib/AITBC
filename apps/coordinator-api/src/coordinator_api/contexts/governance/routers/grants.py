"""Grant proposal API endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from aitbc.rate_limiting import rate_limit

from ....storage.db import get_session
from ..domain.grant import GrantMilestone, GrantProposal
from ..schemas.grant import (
    GrantDisburseRequest,
    GrantMilestoneCreate,
    GrantMilestoneResponse,
    GrantProposalCreate,
    GrantProposalResponse,
    GrantVoteRequest,
)
from ....auth import AdminDep, AuthDep
from ..services.governance_service import GovernanceService
from ..services.grant_service import GrantService

router = APIRouter(prefix="/grants", tags=["grants"])


def get_grant_service(session: Annotated[Session, Depends(get_session)]) -> GrantService:
    """Inject the grant service."""
    return GrantService(session)


@router.post("", response_model=GrantProposalResponse, status_code=201)
@rate_limit(rate=20, per=60)
async def create_grant(
    request: Request,
    body: GrantProposalCreate,
    service: Annotated[GrantService, Depends(get_grant_service)],
    user: AuthDep,
) -> GrantProposal:
    """Create a new grant proposal."""
    developer_id = user["sub"]  # the applicant is the caller (#1071)
    try:
        return await run_in_threadpool(
            service.create_grant,
            developer_id=developer_id,
            title=body.title,
            description=body.description,
            requested_amount=body.requested_amount,
            voting_days=body.voting_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("", response_model=list[GrantProposalResponse])
@rate_limit(rate=200, per=60)
async def list_grants(
    request: Request,
    service: Annotated[GrantService, Depends(get_grant_service)],
    developer_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[GrantProposal]:
    """List grant proposals."""
    try:
        return await run_in_threadpool(
            service.list_grants, developer_id=developer_id, status=status, limit=limit, offset=offset
        )
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{grant_id}", response_model=GrantProposalResponse)
@rate_limit(rate=200, per=60)
async def get_grant(
    request: Request,
    grant_id: str,
    service: Annotated[GrantService, Depends(get_grant_service)],
) -> GrantProposal:
    """Get a grant proposal by ID."""
    try:
        grant = await run_in_threadpool(service.get_grant, grant_id)
        if not grant:
            raise HTTPException(status_code=404, detail="Grant not found")
        return grant
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/{grant_id}/milestones", response_model=GrantMilestoneResponse, status_code=201)
@rate_limit(rate=20, per=60)
async def create_milestone(
    request: Request,
    grant_id: str,
    body: GrantMilestoneCreate,
    service: Annotated[GrantService, Depends(get_grant_service)],
) -> GrantMilestone:
    """Add a milestone to a grant proposal."""
    try:
        return await run_in_threadpool(
            service.create_milestone,
            grant_id=grant_id,
            title=body.title,
            description=body.description,
            amount=body.amount,
            due_date=body.due_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{grant_id}/milestones", response_model=list[GrantMilestoneResponse])
@rate_limit(rate=200, per=60)
async def list_milestones(
    request: Request,
    grant_id: str,
    service: Annotated[GrantService, Depends(get_grant_service)],
) -> list[GrantMilestone]:
    """List milestones for a grant proposal."""
    try:
        return await run_in_threadpool(service.get_milestones, grant_id)
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/{grant_id}/process", response_model=GrantProposalResponse)
@rate_limit(rate=20, per=60)
async def process_grant(
    request: Request,
    grant_id: str,
    service: Annotated[GrantService, Depends(get_grant_service)],
) -> GrantProposal:
    """Resolve a grant proposal after the voting period ends."""
    try:
        return await run_in_threadpool(service.process_grant, grant_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/{grant_id}/vote", response_model=GrantProposalResponse)
@rate_limit(rate=50, per=60)
async def vote_grant(
    request: Request,
    grant_id: str,
    body: GrantVoteRequest,
    service: Annotated[GrantService, Depends(get_grant_service)],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> GrantProposal:
    """Vote on a grant proposal."""
    # Identity and weight come from the caller and its governance profile —
    # never the body (#1071). A client used to mint 1e9 voting power per call.
    voter_id = user["sub"]
    profile = await run_in_threadpool(GovernanceService(session).get_or_create_profile, voter_id, 0.0)
    voting_power = (profile.voting_power or 0.0) + (profile.delegated_power or 0.0)
    try:
        return await run_in_threadpool(
            service.vote, grant_id=grant_id, vote=body.vote, voting_power=voting_power, voter_id=voter_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/{grant_id}/disburse", response_model=GrantProposalResponse)
@rate_limit(rate=20, per=60)
async def disburse_grant(
    request: Request,
    grant_id: str,
    body: GrantDisburseRequest,
    service: Annotated[GrantService, Depends(get_grant_service)],
    user: AdminDep,
) -> GrantProposal:
    """Disburse funds for a grant or milestone."""
    try:
        return await run_in_threadpool(service.disburse, grant_id=grant_id, milestone_id=body.milestone_id, amount=body.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
