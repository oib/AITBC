"""Router for Hermes distributed decision making API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger

from ....auth import AdminDep
from ....schemas.hermes_decision import (
    DecisionListResponse,
    DecisionProposal,
    DecisionProposalResponse,
    DecisionResult,
    DecisionStatus,
    DecisionType,
    Vote,
    VoteResponse,
)
from ....storage import get_session
from ..services.decision_service_db import decision_service

logger = get_logger(__name__)

router = APIRouter(prefix="/hermes/decision", tags=["hermes Decision Making"])


@router.post("/propose", response_model=DecisionProposalResponse)
async def propose_decision(
    proposal: DecisionProposal,
    session: Annotated[Session, Depends(get_session)],
    user: AdminDep,
) -> DecisionProposalResponse:
    """Create a new decision proposal for agent voting."""
    try:
        return decision_service.propose_decision(proposal, session)
    except Exception as e:
        logger.error("Error proposing decision: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/vote", response_model=VoteResponse)
async def submit_vote(
    vote: Vote,
    session: Annotated[Session, Depends(get_session)],
    user: AdminDep,
) -> VoteResponse:
    """Submit an agent vote on a decision."""
    try:
        return decision_service.submit_vote(vote, session)
    except Exception as e:
        logger.error("Error submitting vote: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{decision_id}", response_model=DecisionResult)
async def get_decision(
    decision_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: AdminDep,
) -> DecisionResult:
    """Get the current result of a decision."""
    try:
        result = decision_service.get_decision_result(decision_id, session)
        if not result:
            raise HTTPException(status_code=404, detail="Decision not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting decision: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/", response_model=DecisionListResponse)
async def list_decisions(
    session: Annotated[Session, Depends(get_session)],
    user: AdminDep,
    decision_type: DecisionType | None = None,
    status: DecisionStatus | None = None,
) -> DecisionListResponse:
    """List all decisions with optional filtering."""
    try:
        decisions = decision_service.list_decisions(session, decision_type, status)
        return DecisionListResponse(decisions=decisions, total=len(decisions))
    except Exception as e:
        logger.error("Error listing decisions: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
