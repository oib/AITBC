"""OpenClaw DAO economic parameter proposal endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger

from ....metrics import governance_errors_total, governance_requests_total
from ....storage import get_session
from ....utils.cache import cached, get_cache_config
from ..domain.economic_proposal import EconomicParameterProposal
from ..schemas.economic_proposal import (
    EconomicProposalCreate,
    EconomicProposalResponse,
    EconomicProposalVoteRequest,
)
from ..services.economic_proposal_service import EconomicProposalService

logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(tags=["governance", "economics"], prefix="/economic-proposals")


def _get_service(session: Annotated[Session, Depends(get_session)]) -> EconomicProposalService:
    return EconomicProposalService(session)


@router.post("", response_model=EconomicProposalResponse, status_code=http_status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_proposal(
    request: Request,
    payload: EconomicProposalCreate,
    service: Annotated[EconomicProposalService, Depends(_get_service)],
) -> EconomicParameterProposal:
    """Create a new OpenClaw economic parameter proposal."""
    governance_requests_total.labels(endpoint="/economic-proposals", method="POST").inc()
    try:
        return await service.create_proposal(
            proposer_id=payload.proposer_id,
            parameter_name=payload.parameter_name,
            current_value=payload.current_value,
            proposed_value=payload.proposed_value,
            unit=payload.unit,
            voting_days=payload.voting_days,
        )
    except Exception as e:
        governance_errors_total.labels(endpoint="/economic-proposals", method="POST", error_type="internal").inc()
        logger.error("Error creating economic proposal: %s", e)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create proposal") from e


@router.get("/{proposal_id}", response_model=EconomicProposalResponse)
@limiter.limit("100/minute")
@cached(**get_cache_config("economic_proposals"))
async def get_proposal(
    request: Request,
    proposal_id: str,
    service: Annotated[EconomicProposalService, Depends(_get_service)],
) -> EconomicParameterProposal:
    """Get an economic parameter proposal by ID."""
    governance_requests_total.labels(endpoint="/economic-proposals/{proposal_id}", method="GET").inc()
    try:
        proposal = await service.get_proposal(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Proposal not found")
        return proposal
    except HTTPException:
        raise
    except Exception as e:
        governance_errors_total.labels(endpoint="/economic-proposals/{proposal_id}", method="GET", error_type="internal").inc()
        logger.error("Error fetching economic proposal %s: %s", proposal_id, e)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch proposal") from e


@router.get("", response_model=list[EconomicProposalResponse])
@limiter.limit("100/minute")
@cached(**get_cache_config("economic_proposals"))
async def list_proposals(
    request: Request,
    service: Annotated[EconomicProposalService, Depends(_get_service)],
    proposer_id: str | None = None,
    parameter_name: str | None = None,
    status: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[EconomicParameterProposal]:
    """List economic parameter proposals with optional filters."""
    governance_requests_total.labels(endpoint="/economic-proposals", method="GET").inc()
    try:
        return await service.list_proposals(
            proposer_id=proposer_id,
            parameter_name=parameter_name,
            status=status,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        governance_errors_total.labels(endpoint="/economic-proposals", method="GET", error_type="internal").inc()
        logger.error("Error listing economic proposals: %s", e)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list proposals") from e


@router.post("/{proposal_id}/votes", response_model=EconomicProposalResponse)
@limiter.limit("60/minute")
async def vote_on_proposal(
    request: Request,
    proposal_id: str,
    payload: EconomicProposalVoteRequest,
    service: Annotated[EconomicProposalService, Depends(_get_service)],
) -> EconomicParameterProposal:
    """Cast a vote on an economic parameter proposal."""
    governance_requests_total.labels(endpoint="/economic-proposals/{proposal_id}/votes", method="POST").inc()
    try:
        return await service.vote(proposal_id, payload.vote, payload.voting_power)
    except ValueError as e:
        governance_errors_total.labels(
            endpoint="/economic-proposals/{proposal_id}/votes", method="POST", error_type="invalid_request"
        ).inc()
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        governance_errors_total.labels(
            endpoint="/economic-proposals/{proposal_id}/votes", method="POST", error_type="internal"
        ).inc()
        logger.error("Error voting on economic proposal %s: %s", proposal_id, e)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to record vote") from e


@router.post("/{proposal_id}/execute", response_model=EconomicProposalResponse)
@limiter.limit("30/minute")
async def execute_proposal(
    request: Request,
    proposal_id: str,
    service: Annotated[EconomicProposalService, Depends(_get_service)],
) -> EconomicParameterProposal:
    """Execute an economic parameter proposal after voting closes."""
    governance_requests_total.labels(endpoint="/economic-proposals/{proposal_id}/execute", method="POST").inc()
    try:
        return await service.execute_proposal(proposal_id)
    except ValueError as e:
        governance_errors_total.labels(
            endpoint="/economic-proposals/{proposal_id}/execute", method="POST", error_type="invalid_request"
        ).inc()
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        governance_errors_total.labels(
            endpoint="/economic-proposals/{proposal_id}/execute", method="POST", error_type="internal"
        ).inc()
        logger.error("Error executing economic proposal %s: %s", proposal_id, e)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to execute proposal") from e
