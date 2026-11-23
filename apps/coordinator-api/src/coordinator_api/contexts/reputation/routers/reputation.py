"""
Reputation Management API Endpoints
REST API for agent reputation, trust scores, and economic profiles
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlmodel import select
from starlette.concurrency import run_in_threadpool

from aitbc.aitbc_logging import get_logger
from aitbc.auth import AdminDep, AdminOrClientDep, AuthDep
from aitbc.rate_limiting import rate_limit

from ....custom_types import JobState
from ....storage import get_session
from ....utils.client_resolver import resolve_client
from ...infrastructure.domain.job import Job
from ..domain.cross_chain_reputation import CrossChainReputationAggregation
from ..domain.reputation import (
    AgentReputation,
    CommunityFeedback,
    ReputationEvent,
    ReputationLevel,
)
from ..services.reputation_engine import CrossChainReputationEngine
from ..services.reputation_service import ReputationService

logger = get_logger(__name__)

router = APIRouter(prefix="/reputation", tags=["reputation"])


def get_reputation_service(session: Annotated[Session, Depends(get_session)]) -> ReputationService:
    return ReputationService(session)  # type: ignore[arg-type]


def _require_self_or_admin(user: dict[str, Any], agent_id: str) -> None:
    """Writes to a reputation profile belong to that agent (or an admin)."""
    if user.get("role") != "admin" and user.get("sub") != agent_id:
        raise HTTPException(status_code=403, detail="can only modify your own reputation profile")


class ReputationProfileResponse(BaseModel):
    """Response model for reputation profile.

    ``trust_score`` is the live weighted composite on a **0–1000** scale — the
    same value ``GET /reputation/trust-score/{agent_id}`` reports as
    ``composite_score`` and ``GET /reputation/leaderboard`` reports as
    ``trust_score`` (#2406).
    """

    agent_id: str
    trust_score: float = Field(description="Composite trust score, 0-1000")
    reputation_level: str
    performance_rating: float
    reliability_score: float
    community_rating: float
    total_earnings: Decimal
    transaction_count: int
    success_rate: float
    jobs_completed: int
    jobs_failed: int
    average_response_time: float = Field(description="Mean job response time")
    average_response_time_unit: str = Field(default="ms", description="Unit of average_response_time (milliseconds)")
    dispute_count: int
    certifications: list[str]
    specialization_tags: list[str]
    geographic_region: str
    last_activity: str
    recent_events: list[dict[str, Any]]
    recent_feedback: list[dict[str, Any]]


class FeedbackRequest(BaseModel):
    """Request model for community feedback.

    There is deliberately no reviewer_id field — the reviewer is the
    authenticated caller, so a body-supplied identity is never consulted.
    """

    job_id: str | None = Field(
        default=None,
        description="Completed job this review is anchored to (required for non-admin callers)",
    )
    # #2693: CommunityFeedback is a table=True model — Field(ge/le) on it is
    # never enforced — so the bounds must live here. ge/le also reject
    # inf/nan (every comparison fails), which used to reach SQLite as
    # Infinity/NULL and surface as a 500/409.
    ratings: dict[str, Annotated[float, Field(ge=1.0, le=5.0, allow_inf_nan=False)]] = Field(
        ..., description="Overall, performance, communication, reliability, value ratings"
    )
    feedback_text: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list)


class FeedbackResponse(BaseModel):
    """Response model for feedback submission"""

    id: str
    agent_id: str
    reviewer_id: str
    overall_rating: float
    performance_rating: float
    communication_rating: float
    reliability_rating: float
    value_rating: float
    feedback_text: str
    feedback_tags: list[str]
    created_at: str
    moderation_status: str


class TrustScoreResponse(BaseModel):
    """Response model for trust score breakdown.

    All component scores and ``composite_score`` are on a **0–1000** scale;
    ``composite_score`` is the weighted sum the profile and leaderboard reads
    also report (#2406).
    """

    agent_id: str
    composite_score: float = Field(description="Weighted composite trust score, 0-1000")
    performance_score: float = Field(description="Performance component, 0-1000")
    reliability_score: float = Field(description="Reliability component, 0-1000")
    community_score: float = Field(description="Community component, 0-1000")
    security_score: float = Field(description="Security component, 0-1000")
    economic_score: float = Field(description="Economic component, 0-1000")
    reputation_level: str
    calculated_at: str


class LeaderboardEntry(BaseModel):
    """Leaderboard entry model"""

    rank: int
    agent_id: str
    trust_score: float
    reputation_level: str
    performance_rating: float
    reliability_score: float
    community_rating: float
    total_earnings: Decimal
    transaction_count: int
    geographic_region: str
    specialization_tags: list[str]


class ReputationMetricsResponse(BaseModel):
    """Response model for reputation metrics"""

    total_agents: int
    average_trust_score: float
    level_distribution: dict[str, int]
    top_regions: list[dict[str, Any]]
    recent_activity: dict[str, Any]


@router.get("/profile/{agent_id}", response_model=ReputationProfileResponse)
@rate_limit(rate=200, per=60)
async def get_reputation_profile(
    request: Request, agent_id: str, session: Annotated[Session, Depends(get_session)]
) -> ReputationProfileResponse:
    """Get comprehensive reputation profile for an agent"""
    reputation_service = ReputationService(session)  # type: ignore[arg-type]
    try:
        profile_data = await run_in_threadpool(reputation_service.get_reputation_summary, agent_id)
        if "error" in profile_data:
            raise HTTPException(status_code=404, detail=profile_data["error"])
        return ReputationProfileResponse(**profile_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting reputation profile for %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/profile/{agent_id}")
@rate_limit(rate=20, per=60)
async def create_reputation_profile(
    request: Request, agent_id: str, session: Annotated[Session, Depends(get_session)], user: AuthDep
) -> dict[str, Any]:
    """Create a new reputation profile for an agent"""
    _require_self_or_admin(user, agent_id)
    reputation_service = ReputationService(session)  # type: ignore[arg-type]
    try:
        reputation = await run_in_threadpool(reputation_service.create_reputation_profile, agent_id)
        # Report the same live composite the read endpoints return (#2406) —
        # the stored columns are only the event-sourced cache.
        calculator = reputation_service.calculator
        trust_score = calculator.calculate_composite_trust_score(agent_id, session)  # type: ignore[arg-type]
        return {
            "message": "Reputation profile created successfully",
            "agent_id": reputation.agent_id,
            "trust_score": trust_score,
            "reputation_level": calculator.determine_reputation_level(trust_score).value,
            "created_at": reputation.created_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating reputation profile for %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


async def _require_feedback_eligibility(
    session: Session, user: dict[str, Any], agent_id: str, feedback_request: FeedbackRequest
) -> None:
    """Anchor feedback to delivered work and enforce the one-review-per-job rule."""
    if user.get("role") != "admin":
        if not feedback_request.job_id:
            raise HTTPException(status_code=422, detail="feedback requires a job_id anchoring it to completed work")
        try:
            caller_client_id, _ = await run_in_threadpool(resolve_client, session, user["sub"])  # type: ignore[arg-type]
        except ValueError:
            raise HTTPException(status_code=403, detail="feedback requires a client account") from None
        completed_link = (
            (
                await run_in_threadpool(
                    session.execute,
                    select(Job).where(
                        Job.id == feedback_request.job_id,
                        Job.client_id == caller_client_id,
                        Job.assigned_miner_id == agent_id,
                        Job.state == JobState.completed,
                    ),
                )
            )
            .scalars()
            .first()
        )
        if completed_link is None:
            raise HTTPException(
                status_code=403,
                detail="feedback requires a completed job between you and this agent",
            )
    if feedback_request.job_id is not None:
        existing = (
            (
                await run_in_threadpool(
                    session.execute,
                    select(CommunityFeedback).where(
                        CommunityFeedback.reviewer_id == user["sub"],
                        CommunityFeedback.job_id == feedback_request.job_id,
                    ),
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="you have already reviewed this job")


@router.post("/feedback/{agent_id}", response_model=FeedbackResponse)
@rate_limit(rate=20, per=60)
async def add_community_feedback(
    request: Request,
    agent_id: str,
    feedback_request: FeedbackRequest,
    session: Annotated[Session, Depends(get_session)],
    user: AdminOrClientDep,
) -> FeedbackResponse:
    """Add community feedback for an agent.

    The reviewer is always the authenticated caller — never the request body —
    and a non-admin caller must name a completed job they paid this agent for,
    so a rating is anchored to delivered work rather than free-floating — and
    the unique (reviewer, job_id) constraint makes one job good for exactly one
    review.
    """
    await _require_feedback_eligibility(session, user, agent_id, feedback_request)
    reputation_service = ReputationService(session)  # type: ignore[arg-type]
    try:
        feedback = await run_in_threadpool(
            asyncio.run,
            reputation_service.add_community_feedback(
                agent_id=agent_id,
                reviewer_id=user["sub"],
                job_id=feedback_request.job_id,
                ratings=feedback_request.ratings,
                feedback_text=feedback_request.feedback_text,
                tags=feedback_request.tags,
            ),
        )
        return FeedbackResponse(
            id=feedback.id,
            agent_id=feedback.agent_id,
            reviewer_id=feedback.reviewer_id,
            overall_rating=feedback.overall_rating,
            performance_rating=feedback.performance_rating,
            communication_rating=feedback.communication_rating,
            reliability_rating=feedback.reliability_rating,
            value_rating=feedback.value_rating,
            feedback_text=feedback.feedback_text,
            feedback_tags=feedback.feedback_tags,
            created_at=feedback.created_at.isoformat(),
            moderation_status=feedback.moderation_status,
        )
    except HTTPException:
        raise
    except IntegrityError:
        # Backstop for the pre-check above: a concurrent duplicate submission
        # hits the (reviewer_id, job_id) unique index.
        raise HTTPException(status_code=409, detail="you have already reviewed this job") from None
    except ValueError as e:
        # Service-layer validation (e.g. rating bounds for non-API callers)
        # is a client error, not a server fault (#2725).
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error adding feedback for agent %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


# No HTTP job-completion route: reputation changes come from the coordinator's
# own settlement/miner code (miner.py calls the service with server-verified
# values). The removed public route let any caller set agent_id, success and
# earnings — all three feed trust_score, which dispatch ranks miners by.


@router.get("/trust-score/{agent_id}", response_model=TrustScoreResponse)
@rate_limit(rate=200, per=60)
def get_trust_score_breakdown(
    request: Request, agent_id: str, session: Annotated[Session, Depends(get_session)]
) -> TrustScoreResponse:
    """Get detailed trust score breakdown for an agent.

    Returns 404 when the agent has no reputation profile — the same honest
    default ``GET /reputation/profile/{agent_id}`` gives — rather than a
    fabricated mid-scale composite for an agent with no data (#2406).
    """
    reputation_service = ReputationService(session)  # type: ignore[arg-type]
    if reputation_service.get_reputation_by_agent(agent_id) is None:
        raise HTTPException(status_code=404, detail="Reputation profile not found")
    calculator = reputation_service.calculator
    try:
        performance_score = calculator.calculate_performance_score(agent_id, session)  # type: ignore[arg-type]
        reliability_score = calculator.calculate_reliability_score(agent_id, session)  # type: ignore[arg-type]
        community_score = calculator.calculate_community_score(agent_id, session)  # type: ignore[arg-type]
        security_score = calculator.calculate_security_score(agent_id, session)  # type: ignore[arg-type]
        economic_score = calculator.calculate_economic_score(agent_id, session)  # type: ignore[arg-type]
        composite_score = calculator.calculate_composite_trust_score(agent_id, session)  # type: ignore[arg-type]
        reputation_level = calculator.determine_reputation_level(composite_score)
        return TrustScoreResponse(
            agent_id=agent_id,
            composite_score=composite_score,
            performance_score=performance_score,
            reliability_score=reliability_score,
            community_score=community_score,
            security_score=security_score,
            economic_score=economic_score,
            reputation_level=reputation_level.value,
            calculated_at=datetime.now(UTC).isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting trust score breakdown for %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
@rate_limit(rate=200, per=60)
async def get_reputation_leaderboard(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    category: str = "trust_score",
    limit: int = Query(default=100, ge=1, le=500),
    region: str = "",
) -> list[LeaderboardEntry]:
    """Get reputation leaderboard"""
    reputation_service = ReputationService(session)  # type: ignore[arg-type]
    try:
        leaderboard_data = await run_in_threadpool(
            asyncio.run,
            reputation_service.get_leaderboard(category=category or "trust_score", limit=limit or 100, region=region),
        )
        return [LeaderboardEntry(**entry) for entry in leaderboard_data]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting leaderboard: %s", str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/metrics", response_model=ReputationMetricsResponse)
@rate_limit(rate=200, per=60)
def get_reputation_metrics(request: Request, session: Annotated[Session, Depends(get_session)]) -> ReputationMetricsResponse:
    """Get overall reputation system metrics"""
    try:
        # Use SQL aggregation instead of loading all data into memory
        total_agents = session.execute(select(func.count(AgentReputation.id))).scalar() or 0  # type: ignore[arg-type]
        if total_agents == 0:
            return ReputationMetricsResponse(
                total_agents=0, average_trust_score=0.0, level_distribution={}, top_regions=[], recent_activity={}
            )
        average_trust_score = session.execute(select(func.avg(AgentReputation.trust_score))).scalar() or 0.0

        # Get level distribution using SQL GROUP BY
        level_results = session.execute(
            select(AgentReputation.reputation_level, func.count(AgentReputation.id)).group_by(AgentReputation.reputation_level)  # type: ignore[arg-type]
        ).all()
        level_counts = {level.value: count for level, count in level_results}

        # Get top regions with a limit
        region_results = session.execute(
            select(func.coalesce(AgentReputation.geographic_region, "Unknown"), func.count(AgentReputation.id))  # type: ignore[arg-type]
            .group_by(func.coalesce(AgentReputation.geographic_region, "Unknown"))
            .order_by(func.count(AgentReputation.id).desc())  # type: ignore[arg-type]
            .limit(10)
        ).all()
        top_regions = [{"region": region, "count": count} for region, count in region_results]
        recent_cutoff = datetime.now(UTC) - timedelta(days=1)
        recent_events = (
            session.execute(
                select(func.count(ReputationEvent.id)).where(ReputationEvent.occurred_at >= recent_cutoff)  # type: ignore[arg-type]
            )
            .scalars()
            .first()
        )
        active_agents = (
            session.execute(select(func.count(AgentReputation.id)).where(AgentReputation.last_activity >= recent_cutoff))  # type: ignore[arg-type]
            .scalars()
            .first()
        )
        recent_activity = {
            "events_last_24h": recent_events if recent_events else 0,
            "active_agents": active_agents if active_agents else 0,
        }
        return ReputationMetricsResponse(
            total_agents=total_agents,
            average_trust_score=average_trust_score,
            level_distribution=level_counts,
            top_regions=top_regions,
            recent_activity=recent_activity,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting reputation metrics: %s", str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/feedback/{agent_id}")
@rate_limit(rate=200, per=60)
def get_agent_feedback(
    request: Request,
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[FeedbackResponse]:
    """Get community feedback for an agent"""
    try:
        feedbacks = (
            session.execute(
                select(CommunityFeedback)
                .where(and_(CommunityFeedback.agent_id == agent_id, CommunityFeedback.moderation_status == "approved"))  # type: ignore[arg-type]
                .order_by(desc(CommunityFeedback.created_at))  # type: ignore[arg-type]
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            FeedbackResponse(
                id=feedback.id,
                agent_id=feedback.agent_id,
                reviewer_id=feedback.reviewer_id,
                overall_rating=feedback.overall_rating,
                performance_rating=feedback.performance_rating,
                communication_rating=feedback.communication_rating,
                reliability_rating=feedback.reliability_rating,
                value_rating=feedback.value_rating,
                feedback_text=feedback.feedback_text,
                feedback_tags=feedback.feedback_tags,
                created_at=feedback.created_at.isoformat(),
                moderation_status=feedback.moderation_status,
            )
            for feedback in feedbacks
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting feedback for agent %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/events/{agent_id}")
@rate_limit(rate=200, per=60)
def get_reputation_events(
    request: Request,
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Get reputation change events for an agent"""
    try:
        events = (
            session.execute(
                select(ReputationEvent)
                .where(ReputationEvent.agent_id == agent_id)
                .order_by(desc(ReputationEvent.occurred_at))  # type: ignore[arg-type]
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": event.id,
                "event_type": event.event_type,
                "event_subtype": event.event_subtype,
                "impact_score": event.impact_score,
                "trust_score_before": event.trust_score_before,
                "trust_score_after": event.trust_score_after,
                "reputation_level_before": event.reputation_level_before.value if event.reputation_level_before else None,
                "reputation_level_after": event.reputation_level_after.value if event.reputation_level_after else None,
                "occurred_at": event.occurred_at.isoformat(),
                "event_data": event.event_data,
            }
            for event in events
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting reputation events for %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put("/profile/{agent_id}/specialization")
@rate_limit(rate=20, per=60)
def update_specialization(
    request: Request,
    agent_id: str,
    specialization_tags: list[str],
    session: Annotated[Session, Depends(get_session)],
    user: AuthDep,
) -> dict[str, Any]:
    """Update agent specialization tags"""
    _require_self_or_admin(user, agent_id)
    try:
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()
        if not reputation:
            raise HTTPException(status_code=404, detail="Reputation profile not found")
        reputation.specialization_tags = specialization_tags
        reputation.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(reputation)
        return {
            "message": "Specialization tags updated successfully",
            "agent_id": agent_id,
            "specialization_tags": reputation.specialization_tags,
            "updated_at": reputation.updated_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating specialization for %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.put("/profile/{agent_id}/region")
@rate_limit(rate=20, per=60)
def update_region(
    request: Request, agent_id: str, region: str, session: Annotated[Session, Depends(get_session)], user: AuthDep
) -> dict[str, Any]:
    """Update agent geographic region"""
    _require_self_or_admin(user, agent_id)
    try:
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()
        if not reputation:
            raise HTTPException(status_code=404, detail="Reputation profile not found")
        reputation.geographic_region = region
        reputation.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(reputation)
        return {
            "message": "Geographic region updated successfully",
            "agent_id": agent_id,
            "geographic_region": reputation.geographic_region,
            "updated_at": reputation.updated_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating region for %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


def _cross_chain_aggregation(session: Session, agent_id: str) -> CrossChainReputationAggregation | None:
    return (
        session.execute(select(CrossChainReputationAggregation).where(CrossChainReputationAggregation.agent_id == agent_id))
        .scalars()
        .first()
    )


def _cross_chain_view(aggregation: CrossChainReputationAggregation | None) -> dict[str, Any]:
    """Real stored aggregation values — never fabricated constants (#2722)."""
    active_chains = list(aggregation.active_chains) if aggregation and aggregation.active_chains else []
    chain_scores = dict(aggregation.chain_scores) if aggregation and aggregation.chain_scores else {}
    return {
        "aggregated_score": aggregation.aggregated_score if aggregation else 0.0,
        "chain_count": (aggregation.chain_count or len(active_chains)) if aggregation else len(active_chains),
        "active_chains": active_chains or sorted(chain_scores, key=lambda c: int(c)),
        "chain_scores": chain_scores,
        "consistency_score": aggregation.consistency_score if aggregation else 0.0,
        "verification_status": aggregation.verification_status if aggregation else "pending",
    }


@router.get("/{agent_id}/cross-chain")
@rate_limit(rate=200, per=60)
async def get_cross_chain_reputation(
    request: Request,
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    reputation_service: Annotated[ReputationService, Depends(get_reputation_service)],
) -> dict[str, Any]:
    """Get cross-chain reputation data for an agent"""
    try:
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()
        if not reputation:
            raise HTTPException(status_code=404, detail="Reputation profile not found")
        # #2722: refresh through the real engine, then report the stored
        # aggregation — the previous literals (chain_count 1, consistency
        # 1.0, "verified") were fabricated for every agent.
        engine = CrossChainReputationEngine(session)  # type: ignore[arg-type]
        await engine.aggregate_cross_chain_reputation(agent_id)
        aggregation = _cross_chain_aggregation(session, agent_id)
        cross_chain = _cross_chain_view(aggregation)
        return {
            "agent_id": agent_id,
            "cross_chain": cross_chain,
            "chain_reputations": {
                chain_id: {
                    "trust_score": reputation.trust_score,
                    "reputation_level": reputation.reputation_level.value,
                    "transaction_count": reputation.transaction_count,
                    "success_rate": reputation.success_rate,
                    "last_updated": reputation.updated_at.isoformat(),
                }
                for chain_id in cross_chain["active_chains"]
            },
            "last_updated": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting cross-chain reputation for %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/{agent_id}/cross-chain/sync")
@rate_limit(rate=20, per=60)
async def sync_cross_chain_reputation(
    request: Request,
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    reputation_service: Annotated[ReputationService, Depends(get_reputation_service)],
    user: AdminDep,
) -> dict[str, Any]:
    """Synchronize reputation across chains for an agent"""
    try:
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()
        if not reputation:
            raise HTTPException(status_code=404, detail="Reputation profile not found")
        # #2722: actually recompute — the previous "completed" reply synced
        # nothing.
        engine = CrossChainReputationEngine(session)  # type: ignore[arg-type]
        await engine.aggregate_cross_chain_reputation(agent_id)
        aggregation = _cross_chain_aggregation(session, agent_id)
        cross_chain = _cross_chain_view(aggregation)
        return {
            "agent_id": agent_id,
            "sync_status": "completed",
            "chains_synced": cross_chain["active_chains"],
            "chain_count": cross_chain["chain_count"],
            "aggregated_score": cross_chain["aggregated_score"],
            "chain_scores": cross_chain["chain_scores"],
            "sync_timestamp": datetime.now(UTC).isoformat(),
            "message": "Cross-chain reputation synchronized",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error syncing cross-chain reputation for %s: %s", agent_id, str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/cross-chain/leaderboard")
@rate_limit(rate=200, per=60)
def get_cross_chain_leaderboard(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    reputation_service: Annotated[ReputationService, Depends(get_reputation_service)],
    limit: int = Query(default=100, ge=1, le=500),
    min_score: float = 0.0,
) -> dict[str, Any]:
    """Get cross-chain reputation leaderboard"""
    try:
        effective_min_score = (min_score or 0.0) * 1000
        reputations = (
            session.execute(
                select(AgentReputation)
                .where(AgentReputation.trust_score >= effective_min_score)
                .order_by(desc(AgentReputation.trust_score))  # type: ignore[arg-type]
                .limit(limit)
            )
            .scalars()
            .all()
        )
        # #2722: per-agent cross-chain fields come from the stored
        # aggregations, not literals — agents without one report empty.
        agent_ids = [rep.agent_id for rep in reputations]
        aggregations: dict[str, CrossChainReputationAggregation] = {}
        if agent_ids:
            for agg in (
                session.execute(
                    select(CrossChainReputationAggregation).where(
                        CrossChainReputationAggregation.agent_id.in_(agent_ids)  # type: ignore[attr-defined]
                    )
                )
                .scalars()
                .all()
            ):
                aggregations[agg.agent_id] = agg
        agents = []
        for rep in reputations:
            cross_chain = _cross_chain_view(aggregations.get(rep.agent_id))
            agents.append(
                {
                    "agent_id": rep.agent_id,
                    "aggregated_score": cross_chain["aggregated_score"],
                    "chain_count": cross_chain["chain_count"],
                    "active_chains": cross_chain["active_chains"],
                    "consistency_score": cross_chain["consistency_score"],
                    "verification_status": cross_chain["verification_status"],
                    "trust_score": rep.trust_score,
                    "reputation_level": rep.reputation_level.value,
                    "transaction_count": rep.transaction_count,
                    "success_rate": rep.success_rate,
                    "last_updated": rep.updated_at.isoformat(),
                }
            )
        return {
            "agents": agents,
            "total_count": len(agents),
            "limit": limit,
            "min_score": min_score,
            "last_updated": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting cross-chain leaderboard: %s", str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/cross-chain/events")
@rate_limit(rate=20, per=60)
def submit_cross_chain_event(
    request: Request,
    event_data: dict[str, Any],
    session: Annotated[Session, Depends(get_session)],
    reputation_service: Annotated[ReputationService, Depends(get_reputation_service)],
    user: AdminDep,
) -> dict[str, Any]:
    """Submit a cross-chain reputation event"""
    try:
        required_fields = ["agent_id", "event_type", "impact_score"]
        for field in required_fields:
            if field not in event_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        agent_id = event_data["agent_id"]
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()
        if not reputation:
            raise HTTPException(status_code=404, detail="Reputation profile not found")
        impact = event_data["impact_score"]
        old_score = reputation.trust_score
        new_score = max(0, min(1000, old_score + impact * 1000))
        reputation.trust_score = new_score
        reputation.updated_at = datetime.now(UTC)
        if new_score >= 900:
            reputation.reputation_level = ReputationLevel.MASTER
        elif new_score >= 800:
            reputation.reputation_level = ReputationLevel.EXPERT
        elif new_score >= 600:
            reputation.reputation_level = ReputationLevel.ADVANCED
        elif new_score >= 400:
            reputation.reputation_level = ReputationLevel.INTERMEDIATE
        else:
            reputation.reputation_level = ReputationLevel.BEGINNER
        session.commit()
        return {
            "event_id": f"event_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            "agent_id": agent_id,
            "event_type": event_data["event_type"],
            "impact_score": impact,
            "old_score": old_score / 1000.0,
            "new_score": new_score / 1000.0,
            "processed_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error submitting cross-chain event: %s", str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/cross-chain/analytics")
@rate_limit(rate=200, per=60)
def get_cross_chain_analytics(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    reputation_service: Annotated[ReputationService, Depends(get_reputation_service)],
    chain_id: int = 1,
) -> dict[str, Any]:
    """Get cross-chain reputation analytics"""
    try:
        total_agents = session.execute(select(func.count(AgentReputation.id))).scalar() or 0  # type: ignore[arg-type]
        avg_reputation = session.execute(select(func.avg(AgentReputation.trust_score))).scalar() or 0.0
        reputations = session.execute(select(AgentReputation)).scalars().all()
        distribution = {"master": 0, "expert": 0, "advanced": 0, "intermediate": 0, "beginner": 0}
        score_ranges = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        for rep in reputations:
            level = rep.reputation_level.value
            distribution[level] = distribution.get(level, 0) + 1
            score = rep.trust_score / 1000.0
            if score < 0.2:
                score_ranges["0.0-0.2"] += 1
            elif score < 0.4:
                score_ranges["0.2-0.4"] += 1
            elif score < 0.6:
                score_ranges["0.4-0.6"] += 1
            elif score < 0.8:
                score_ranges["0.6-0.8"] += 1
            else:
                score_ranges["0.8-1.0"] += 1
        return {
            "chain_id": chain_id or 1,
            "total_agents": total_agents,
            "average_reputation": avg_reputation / 1000.0,
            "reputation_distribution": distribution,
            "score_distribution": score_ranges,
            "cross_chain_metrics": {
                "cross_chain_agents": total_agents,
                # #2722: real average over stored aggregations, not a literal.
                "average_consistency_score": (
                    session.execute(select(func.avg(CrossChainReputationAggregation.consistency_score))).scalar() or 0.0
                ),
                "chain_diversity_score": 0.0,
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting cross-chain analytics: %s", str(e))
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error") from e
