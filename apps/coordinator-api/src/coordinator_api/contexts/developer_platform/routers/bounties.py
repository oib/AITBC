"""Bounty management endpoints for the Developer Platform."""

from typing import Annotated, Any

from aitbc.rate_limiting import rate_limit
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from ....storage.db import get_session
from ..domain.developer_platform import BountyStatus, BountyTask, DeveloperProfile
from ..schemas.developer_platform import BountyCreate, BountySubmissionCreate
from ..services.developer_platform_service import DeveloperPlatformService
from .common import get_developer_platform_service

router = APIRouter(tags=["Developer Platform"])


@router.post("/bounties", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def create_bounty(
    request: BountyCreate,
    request_http: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Create a new bounty task."""

    try:
        bounty = await dev_service.create_bounty(request)

        return {
            "success": True,
            "bounty_id": bounty.id,
            "title": bounty.title,
            "reward_amount": bounty.reward_amount,
            "difficulty_level": bounty.difficulty_level.value,
            "status": bounty.status.value,
            "created_at": bounty.created_at.isoformat(),
            "deadline": bounty.deadline.isoformat() if bounty.deadline else None,
            "message": "Bounty created successfully",
        }

    except Exception:
        raise HTTPException(status_code=500, detail="Error creating bounty") from None


@router.get("/bounties", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def list_bounties(
    request: Request,
    status: BountyStatus | None,
    limit: int | None,
    offset: int | None,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> list[dict[str, Any]]:
    """List bounty tasks with optional status filter."""

    try:
        bounties = await dev_service.list_bounties(status, limit or 100, offset or 0)

        return [
            {
                "id": bounty.id,
                "title": bounty.title,
                "description": bounty.description[:200] + "..." if len(bounty.description) > 200 else bounty.description,
                "reward_amount": bounty.reward_amount,
                "difficulty_level": bounty.difficulty_level.value,
                "required_skills": bounty.required_skills,
                "status": bounty.status.value,
                "creator_address": bounty.creator_address,
                "created_at": bounty.created_at.isoformat(),
                "deadline": bounty.deadline.isoformat() if bounty.deadline else None,
            }
            for bounty in bounties
        ]

    except Exception:
        raise HTTPException(status_code=500, detail="Error listing bounties") from None


@router.get("/bounties/my-submissions", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_my_submissions(
    developer_id: str,
    request: Request,
    limit: int | None,
    offset: int | None,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> list[dict[str, Any]]:
    """Get all submissions by a developer."""

    try:
        submissions = await dev_service.get_my_submissions(developer_id)

        result = []
        for sub in submissions[(offset or 0) : (offset or 0) + (limit or 100)]:
            bounty = session.get(BountyTask, sub.bounty_id)
            result.append(
                {
                    "id": sub.id,
                    "bounty_id": sub.bounty_id,
                    "bounty_title": bounty.title if bounty else None,
                    "reward_amount": bounty.reward_amount if bounty else None,
                    "github_pr_url": sub.github_pr_url,
                    "submission_notes": sub.submission_notes,
                    "is_approved": sub.is_approved,
                    "review_notes": sub.review_notes,
                    "submitted_at": sub.submitted_at.isoformat(),
                    "reviewed_at": sub.reviewed_at.isoformat() if sub.reviewed_at else None,
                }
            )
        return result

    except Exception:
        raise HTTPException(status_code=500, detail="Error getting submissions") from None


@router.get("/bounties/stats", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_bounty_statistics(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Get comprehensive bounty statistics."""

    try:
        stats = await dev_service.get_bounty_statistics()
        return stats

    except Exception:
        raise HTTPException(status_code=500, detail="Error getting bounty statistics") from None


@router.get("/bounties/{bounty_id}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def get_bounty_details(
    bounty_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Get detailed bounty information."""

    try:
        bounty_details = await dev_service.get_bounty_details(bounty_id)
        return bounty_details  # type: ignore[return-value]

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting bounty details") from None


@router.post("/bounties/{bounty_id}/submit", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def submit_bounty_solution(
    bounty_id: str,
    request: BountySubmissionCreate,
    request_http: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Submit a solution for a bounty."""

    try:
        submission = await dev_service.submit_bounty(bounty_id, request)

        return {
            "success": True,
            "submission_id": submission.id,
            "bounty_id": bounty_id,
            "developer_id": request.developer_id,
            "github_pr_url": submission.github_pr_url,
            "submitted_at": submission.submitted_at.isoformat(),
            "status": "submitted",
            "message": "Bounty solution submitted successfully",
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error submitting bounty solution") from None


@router.post("/bounties/{bounty_id}/review", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def review_bounty_submission(
    bounty_id: str,
    submission_id: str,
    reviewer_address: str,
    review_notes: str,
    request: Request,
    approved: bool | None,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Review and approve/reject a bounty submission."""

    try:
        if approved:
            submission = await dev_service.approve_submission(submission_id, reviewer_address, review_notes)
            developer = session.get(DeveloperProfile, submission.developer_id)
            bounty = session.get(BountyTask, submission.bounty_id)
            return {
                "success": True,
                "submission_id": submission.id,
                "bounty_id": submission.bounty_id,
                "developer_address": developer.wallet_address if developer else None,
                "reward_amount": bounty.reward_amount if bounty else None,
                "is_approved": submission.is_approved,
                "tx_hash_reward": submission.tx_hash_reward,
                "reviewed_at": submission.reviewed_at.isoformat(),  # type: ignore[union-attr]
                "message": "Submission approved and reward distributed",
            }
        else:
            submission = await dev_service.reject_submission(submission_id, reviewer_address, review_notes)
            developer = session.get(DeveloperProfile, submission.developer_id)
            bounty = session.get(BountyTask, submission.bounty_id)
            return {
                "success": True,
                "submission_id": submission.id,
                "bounty_id": submission.bounty_id,
                "developer_address": developer.wallet_address if developer else None,
                "is_approved": submission.is_approved,
                "reviewed_at": submission.reviewed_at.isoformat(),  # type: ignore[union-attr]
                "message": "Submission rejected and bounty reopened",
            }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error reviewing submission") from None
