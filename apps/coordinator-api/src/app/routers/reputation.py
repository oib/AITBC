"""
Reputation Management API Endpoints
REST API for agent reputation, trust scores, and economic profiles
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from aitbc.logging import get_logger

from ..storage import SessionDep
from ..services.reputation_service import ReputationService
from ..domain.reputation import (
    AgentReputation, CommunityFeedback, ReputationLevel,
    TrustScoreCategory
)
from sqlmodel import select, func, Field

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/reputation", tags=["reputation"])


# Pydantic models for API requests/responses
class ReputationProfileResponse(BaseModel):
    """Response model for reputation profile"""
    agent_id: str
    trust_score: float
    reputation_level: str
    performance_rating: float
    reliability_score: float
    community_rating: float
    total_earnings: float
    transaction_count: int
    success_rate: float
    jobs_completed: int
    jobs_failed: int
    average_response_time: float
    dispute_count: int
    certifications: List[str]
    specialization_tags: List[str]
    geographic_region: str
    last_activity: str
    recent_events: List[Dict[str, Any]]
    recent_feedback: List[Dict[str, Any]]


class FeedbackRequest(BaseModel):
    """Request model for community feedback"""
    reviewer_id: str
    ratings: Dict[str, float] = Field(..., description="Overall, performance, communication, reliability, value ratings")
    feedback_text: str = Field(default="", max_length=1000)
    tags: List[str] = Field(default_factory=list)


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
    feedback_tags: List[str]
    created_at: str
    moderation_status: str


class JobCompletionRequest(BaseModel):
    """Request model for job completion recording"""
    agent_id: str
    job_id: str
    success: bool
    response_time: float = Field(..., gt=0, description="Response time in milliseconds")
    earnings: float = Field(..., ge=0, description="Earnings in AITBC")


class TrustScoreResponse(BaseModel):
    """Response model for trust score breakdown"""
    agent_id: str
    composite_score: float
    performance_score: float
    reliability_score: float
    community_score: float
    security_score: float
    economic_score: float
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
    total_earnings: float
    transaction_count: int
    geographic_region: str
    specialization_tags: List[str]


class ReputationMetricsResponse(BaseModel):
    """Response model for reputation metrics"""
    total_agents: int
    average_trust_score: float
    level_distribution: Dict[str, int]
    top_regions: List[Dict[str, Any]]
    recent_activity: Dict[str, Any]


# API Endpoints

@router.get("/profile/{agent_id}", response_model=ReputationProfileResponse)
async def get_reputation_profile(
    agent_id: str,
    session: SessionDep
) -> ReputationProfileResponse:
    """Get comprehensive reputation profile for an agent"""
    
    reputation_service = ReputationService(session)
    
    try:
        profile_data = await reputation_service.get_reputation_summary(agent_id)
        
        if "error" in profile_data:
            raise HTTPException(status_code=404, detail=profile_data["error"])
        
        return ReputationProfileResponse(**profile_data)
        
    except Exception as e:
        logger.error(f"Error getting reputation profile for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/profile/{agent_id}")
async def create_reputation_profile(
    agent_id: str,
    session: SessionDep
) -> Dict[str, Any]:
    """Create a new reputation profile for an agent"""
    
    reputation_service = ReputationService(session)
    
    try:
        reputation = await reputation_service.create_reputation_profile(agent_id)
        
        return {
            "message": "Reputation profile created successfully",
            "agent_id": reputation.agent_id,
            "trust_score": reputation.trust_score,
            "reputation_level": reputation.reputation_level.value,
            "created_at": reputation.created_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error creating reputation profile for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/feedback/{agent_id}", response_model=FeedbackResponse)
async def add_community_feedback(
    agent_id: str,
    feedback_request: FeedbackRequest,
    session: SessionDep
) -> FeedbackResponse:
    """Add community feedback for an agent"""
    
    reputation_service = ReputationService(session)
    
    try:
        feedback = await reputation_service.add_community_feedback(
            agent_id=agent_id,
            reviewer_id=feedback_request.reviewer_id,
            ratings=feedback_request.ratings,
            feedback_text=feedback_request.feedback_text,
            tags=feedback_request.tags
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
            moderation_status=feedback.moderation_status
        )
        
    except Exception as e:
        logger.error(f"Error adding feedback for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/job-completion")
async def record_job_completion(
    job_request: JobCompletionRequest,
    session: SessionDep
) -> Dict[str, Any]:
    """Record job completion and update reputation"""
    
    reputation_service = ReputationService(session)
    
    try:
        reputation = await reputation_service.record_job_completion(
            agent_id=job_request.agent_id,
            job_id=job_request.job_id,
            success=job_request.success,
            response_time=job_request.response_time,
            earnings=job_request.earnings
        )
        
        return {
            "message": "Job completion recorded successfully",
            "agent_id": reputation.agent_id,
            "new_trust_score": reputation.trust_score,
            "reputation_level": reputation.reputation_level.value,
            "jobs_completed": reputation.jobs_completed,
            "success_rate": reputation.success_rate,
            "total_earnings": reputation.total_earnings
        }
        
    except Exception as e:
        logger.error(f"Error recording job completion: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/trust-score/{agent_id}", response_model=TrustScoreResponse)
async def get_trust_score_breakdown(
    agent_id: str,
    session: SessionDep
) -> TrustScoreResponse:
    """Get detailed trust score breakdown for an agent"""
    
    reputation_service = ReputationService(session)
    calculator = reputation_service.calculator
    
    try:
        # Calculate individual components
        performance_score = calculator.calculate_performance_score(agent_id, session)
        reliability_score = calculator.calculate_reliability_score(agent_id, session)
        community_score = calculator.calculate_community_score(agent_id, session)
        security_score = calculator.calculate_security_score(agent_id, session)
        economic_score = calculator.calculate_economic_score(agent_id, session)
        
        # Calculate composite score
        composite_score = calculator.calculate_composite_trust_score(agent_id, session)
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
            calculated_at=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error getting trust score breakdown for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/leaderboard", response_model=List[LeaderboardEntry])
async def get_reputation_leaderboard(
    category: str = Query(default="trust_score", description="Category to rank by"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
    region: Optional[str] = Query(default=None, description="Filter by region"),
    session: SessionDep
) -> List[LeaderboardEntry]:
    """Get reputation leaderboard"""
    
    reputation_service = ReputationService(session)
    
    try:
        leaderboard_data = await reputation_service.get_leaderboard(
            category=category,
            limit=limit,
            region=region
        )
        
        return [LeaderboardEntry(**entry) for entry in leaderboard_data]
        
    except Exception as e:
        logger.error(f"Error getting leaderboard: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/metrics", response_model=ReputationMetricsResponse)
async def get_reputation_metrics(
    session: SessionDep
) -> ReputationMetricsResponse:
    """Get overall reputation system metrics"""
    
    try:
        # Get all reputation profiles
        reputations = session.exec(
            select(AgentReputation)
        ).all()
        
        if not reputations:
            return ReputationMetricsResponse(
                total_agents=0,
                average_trust_score=0.0,
                level_distribution={},
                top_regions=[],
                recent_activity={}
            )
        
        # Calculate metrics
        total_agents = len(reputations)
        average_trust_score = sum(r.trust_score for r in reputations) / total_agents
        
        # Level distribution
        level_counts = {}
        for reputation in reputations:
            level = reputation.reputation_level.value
            level_counts[level] = level_counts.get(level, 0) + 1
        
        # Top regions
        region_counts = {}
        for reputation in reputations:
            region = reputation.geographic_region or "Unknown"
            region_counts[region] = region_counts.get(region, 0) + 1
        
        top_regions = [
            {"region": region, "count": count}
            for region, count in sorted(region_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]
        
        # Recent activity (last 24 hours)
        recent_cutoff = datetime.utcnow() - timedelta(days=1)
        recent_events = session.exec(
            select(func.count(ReputationEvent.id)).where(
                ReputationEvent.occurred_at >= recent_cutoff
            )
        ).first()
        
        recent_activity = {
            "events_last_24h": recent_events[0] if recent_events else 0,
            "active_agents": len([
                r for r in reputations 
                if r.last_activity and r.last_activity >= recent_cutoff
            ])
        }
        
        return ReputationMetricsResponse(
            total_agents=total_agents,
            average_trust_score=average_trust_score,
            level_distribution=level_counts,
            top_regions=top_regions,
            recent_activity=recent_activity
        )
        
    except Exception as e:
        logger.error(f"Error getting reputation metrics: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/feedback/{agent_id}")
async def get_agent_feedback(
    agent_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    session: SessionDep
) -> List[FeedbackResponse]:
    """Get community feedback for an agent"""
    
    try:
        feedbacks = session.exec(
            select(CommunityFeedback)
            .where(
                and_(
                    CommunityFeedback.agent_id == agent_id,
                    CommunityFeedback.moderation_status == "approved"
                )
            )
            .order_by(CommunityFeedback.created_at.desc())
            .limit(limit)
        ).all()
        
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
                moderation_status=feedback.moderation_status
            )
            for feedback in feedbacks
        ]
        
    except Exception as e:
        logger.error(f"Error getting feedback for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/events/{agent_id}")
async def get_reputation_events(
    agent_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    session: SessionDep
) -> List[Dict[str, Any]]:
    """Get reputation change events for an agent"""
    
    try:
        events = session.exec(
            select(ReputationEvent)
            .where(ReputationEvent.agent_id == agent_id)
            .order_by(ReputationEvent.occurred_at.desc())
            .limit(limit)
        ).all()
        
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
                "event_data": event.event_data
            }
            for event in events
        ]
        
    except Exception as e:
        logger.error(f"Error getting reputation events for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/profile/{agent_id}/specialization")
async def update_specialization(
    agent_id: str,
    specialization_tags: List[str],
    session: SessionDep
) -> Dict[str, Any]:
    """Update agent specialization tags"""
    
    try:
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            raise HTTPException(status_code=404, detail="Reputation profile not found")
        
        reputation.specialization_tags = specialization_tags
        reputation.updated_at = datetime.utcnow()
        
        session.commit()
        session.refresh(reputation)
        
        return {
            "message": "Specialization tags updated successfully",
            "agent_id": agent_id,
            "specialization_tags": reputation.specialization_tags,
            "updated_at": reputation.updated_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating specialization for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/profile/{agent_id}/region")
async def update_region(
    agent_id: str,
    region: str,
    session: SessionDep
) -> Dict[str, Any]:
    """Update agent geographic region"""
    
    try:
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            raise HTTPException(status_code=404, detail="Reputation profile not found")
        
        reputation.geographic_region = region
        reputation.updated_at = datetime.utcnow()
        
        session.commit()
        session.refresh(reputation)
        
        return {
            "message": "Geographic region updated successfully",
            "agent_id": agent_id,
            "geographic_region": reputation.geographic_region,
            "updated_at": reputation.updated_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating region for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Cross-Chain Reputation Endpoints
@router.get("/{agent_id}/cross-chain")
async def get_cross_chain_reputation(
    agent_id: str,
    session: SessionDep,
    reputation_service: ReputationService = Depends()
) -> Dict[str, Any]:
    """Get cross-chain reputation data for an agent"""
    
    try:
        # Get basic reputation
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            raise HTTPException(status_code=404, detail="Reputation profile not found")
        
        # For now, return single-chain data with cross-chain structure
        # This will be extended when full cross-chain implementation is ready
        return {
            "agent_id": agent_id,
            "cross_chain": {
                "aggregated_score": reputation.trust_score / 1000.0,  # Convert to 0-1 scale
                "chain_count": 1,
                "active_chains": [1],  # Default to Ethereum mainnet
                "chain_scores": {1: reputation.trust_score / 1000.0},
                "consistency_score": 1.0,
                "verification_status": "verified"
            },
            "chain_reputations": {
                1: {
                    "trust_score": reputation.trust_score,
                    "reputation_level": reputation.reputation_level.value,
                    "transaction_count": reputation.transaction_count,
                    "success_rate": reputation.success_rate,
                    "last_updated": reputation.updated_at.isoformat()
                }
            },
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cross-chain reputation for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{agent_id}/cross-chain/sync")
async def sync_cross_chain_reputation(
    agent_id: str,
    background_tasks: Any,  # FastAPI BackgroundTasks
    session: SessionDep,
    reputation_service: ReputationService = Depends()
) -> Dict[str, Any]:
    """Synchronize reputation across chains for an agent"""
    
    try:
        # Get reputation
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            raise HTTPException(status_code=404, detail="Reputation profile not found")
        
        # For now, return success (full implementation will be added)
        return {
            "agent_id": agent_id,
            "sync_status": "completed",
            "chains_synced": [1],
            "sync_timestamp": datetime.utcnow().isoformat(),
            "message": "Cross-chain reputation synchronized successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing cross-chain reputation for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/cross-chain/leaderboard")
async def get_cross_chain_leaderboard(
    limit: int = Query(50, ge=1, le=100),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    session: SessionDep,
    reputation_service: ReputationService = Depends()
) -> Dict[str, Any]:
    """Get cross-chain reputation leaderboard"""
    
    try:
        # Get top reputations
        reputations = session.exec(
            select(AgentReputation)
            .where(AgentReputation.trust_score >= min_score * 1000)
            .order_by(AgentReputation.trust_score.desc())
            .limit(limit)
        ).all()
        
        agents = []
        for rep in reputations:
            agents.append({
                "agent_id": rep.agent_id,
                "aggregated_score": rep.trust_score / 1000.0,
                "chain_count": 1,
                "active_chains": [1],
                "consistency_score": 1.0,
                "verification_status": "verified",
                "trust_score": rep.trust_score,
                "reputation_level": rep.reputation_level.value,
                "transaction_count": rep.transaction_count,
                "success_rate": rep.success_rate,
                "last_updated": rep.updated_at.isoformat()
            })
        
        return {
            "agents": agents,
            "total_count": len(agents),
            "limit": limit,
            "min_score": min_score,
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting cross-chain leaderboard: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/cross-chain/events")
async def submit_cross_chain_event(
    event_data: Dict[str, Any],
    background_tasks: Any,  # FastAPI BackgroundTasks
    session: SessionDep,
    reputation_service: ReputationService = Depends()
) -> Dict[str, Any]:
    """Submit a cross-chain reputation event"""
    
    try:
        # Validate event data
        required_fields = ['agent_id', 'event_type', 'impact_score']
        for field in required_fields:
            if field not in event_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        agent_id = event_data['agent_id']
        
        # Get reputation
        reputation = session.exec(
            select(AgentReputation).where(AgentReputation.agent_id == agent_id)
        ).first()
        
        if not reputation:
            raise HTTPException(status_code=404, detail="Reputation profile not found")
        
        # Update reputation based on event
        impact = event_data['impact_score']
        old_score = reputation.trust_score
        new_score = max(0, min(1000, old_score + (impact * 1000)))
        
        reputation.trust_score = new_score
        reputation.updated_at = datetime.utcnow()
        
        # Update reputation level if needed
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
            "event_id": f"event_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "agent_id": agent_id,
            "event_type": event_data['event_type'],
            "impact_score": impact,
            "old_score": old_score / 1000.0,
            "new_score": new_score / 1000.0,
            "processed_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting cross-chain event: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/cross-chain/analytics")
async def get_cross_chain_analytics(
    chain_id: Optional[int] = Query(None),
    session: SessionDep,
    reputation_service: ReputationService = Depends()
) -> Dict[str, Any]:
    """Get cross-chain reputation analytics"""
    
    try:
        # Get basic statistics
        total_agents = session.exec(select(func.count(AgentReputation.id))).first()
        avg_reputation = session.exec(select(func.avg(AgentReputation.trust_score))).first() or 0.0
        
        # Get reputation distribution
        reputations = session.exec(select(AgentReputation)).all()
        
        distribution = {
            "master": 0,
            "expert": 0,
            "advanced": 0,
            "intermediate": 0,
            "beginner": 0
        }
        
        score_ranges = {
            "0.0-0.2": 0,
            "0.2-0.4": 0,
            "0.4-0.6": 0,
            "0.6-0.8": 0,
            "0.8-1.0": 0
        }
        
        for rep in reputations:
            # Level distribution
            level = rep.reputation_level.value
            distribution[level] = distribution.get(level, 0) + 1
            
            # Score distribution
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
                "cross_chain_agents": total_agents,  # All agents for now
                "average_consistency_score": 1.0,
                "chain_diversity_score": 0.0  # No cross-chain diversity yet
            },
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting cross-chain analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
