"""
Agent Reputation and Trust Service
Implements reputation management, trust score calculations, and economic profiling
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Session, and_, desc, func, select

from aitbc.aitbc_logging import get_logger
from aitbc_shared.models import ReputationDTO

from ..domain.reputation import (
    AgentReputation,
    CommunityFeedback,
    ReputationEvent,
    ReputationLevel,
    TrustScoreCategory,
)

logger = get_logger(__name__)


class TrustScoreCalculator:
    """Advanced trust score calculation algorithms"""

    def __init__(self) -> None:
        self.weights = {
            TrustScoreCategory.PERFORMANCE: 0.35,
            TrustScoreCategory.RELIABILITY: 0.25,
            TrustScoreCategory.COMMUNITY: 0.2,
            TrustScoreCategory.SECURITY: 0.1,
            TrustScoreCategory.ECONOMIC: 0.1,
        }
        self.decay_factors = {"daily": 0.95, "weekly": 0.9, "monthly": 0.8, "yearly": 0.6}

    def calculate_performance_score(
        self, agent_id: str, session: Session, time_window: timedelta = timedelta(days=30)
    ) -> float:
        """Calculate performance-based trust score component"""
        cutoff_date = datetime.now(UTC) - time_window
        select(func.count()).where(and_(AgentReputation.agent_id == agent_id, AgentReputation.updated_at >= cutoff_date))
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if not reputation:
            return 500.0
        base_score = reputation.performance_rating / 5.0 * 1000
        if reputation.transaction_count > 0:
            success_modifier = reputation.success_rate / 100.0
            base_score *= success_modifier
        if reputation.average_response_time > 0:
            response_modifier = max(0.5, 1.0 - reputation.average_response_time / 10000.0)
            base_score *= response_modifier
        return min(1000.0, max(0.0, base_score))  # type: ignore[no-any-return]

    def calculate_reliability_score(
        self, agent_id: str, session: Session, time_window: timedelta = timedelta(days=30)
    ) -> float:
        """Calculate reliability-based trust score component"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if not reputation:
            return 500.0
        base_score = reputation.reliability_score * 10
        if reputation.uptime_percentage > 0:
            uptime_modifier = reputation.uptime_percentage / 100.0
            base_score *= uptime_modifier
        total_jobs = reputation.jobs_completed + reputation.jobs_failed
        if total_jobs > 0:
            completion_ratio = reputation.jobs_completed / total_jobs
            base_score *= completion_ratio
        return min(1000.0, max(0.0, base_score))  # type: ignore[no-any-return]

    def calculate_community_score(self, agent_id: str, session: Session, time_window: timedelta = timedelta(days=90)) -> float:
        """Calculate community-based trust score component"""
        cutoff_date = datetime.now(UTC) - time_window
        feedback_query = select(CommunityFeedback).where(
            and_(
                CommunityFeedback.agent_id == agent_id,
                CommunityFeedback.created_at >= cutoff_date,
                CommunityFeedback.moderation_status == "approved",
            )
        )
        feedbacks = session.execute(feedback_query).all()
        if not feedbacks:
            return 500.0
        total_weight = 0.0
        weighted_sum = 0.0
        for feedback in feedbacks:
            weight = feedback.verification_weight
            rating = feedback.overall_rating
            weighted_sum += rating * weight
            total_weight += weight
        if total_weight > 0:
            avg_rating = weighted_sum / total_weight
            base_score = avg_rating / 5.0 * 1000
        else:
            base_score = 500.0
        feedback_count = len(feedbacks)
        if feedback_count > 0:
            volume_modifier = min(1.2, 1.0 + feedback_count / 100.0)
            base_score *= volume_modifier
        return min(1000.0, max(0.0, base_score))

    def calculate_security_score(self, agent_id: str, session: Session, time_window: timedelta = timedelta(days=180)) -> float:
        """Calculate security-based trust score component"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if not reputation:
            return 500.0
        base_score = 800.0
        if reputation.transaction_count > 0:
            dispute_ratio = reputation.dispute_count / reputation.transaction_count
            dispute_penalty = dispute_ratio * 500
            base_score -= dispute_penalty
        if reputation.certifications:
            certification_boost = min(200.0, len(reputation.certifications) * 50.0)
            base_score += certification_boost
        return min(1000.0, max(0.0, base_score))

    def calculate_economic_score(self, agent_id: str, session: Session, time_window: timedelta = timedelta(days=30)) -> float:
        """Calculate economic-based trust score component"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if not reputation:
            return 500.0
        if reputation.total_earnings > 0 and reputation.transaction_count > 0:
            avg_earning_per_transaction = reputation.total_earnings / reputation.transaction_count
            earning_modifier = min(2.0, avg_earning_per_transaction / 0.1)
            base_score = 500.0 * earning_modifier
        else:
            base_score = 500.0
        if reputation.success_rate > 0:
            success_modifier = reputation.success_rate / 100.0
            base_score *= success_modifier
        return min(1000.0, max(0.0, base_score))  # type: ignore[no-any-return]

    def calculate_composite_trust_score(
        self, agent_id: str, session: Session, time_window: timedelta = timedelta(days=30)
    ) -> float:
        """Calculate composite trust score using weighted components"""
        performance_score = self.calculate_performance_score(agent_id, session, time_window)
        reliability_score = self.calculate_reliability_score(agent_id, session, time_window)
        community_score = self.calculate_community_score(agent_id, session, time_window)
        security_score = self.calculate_security_score(agent_id, session, time_window)
        economic_score = self.calculate_economic_score(agent_id, session, time_window)
        weighted_score = (
            performance_score * self.weights[TrustScoreCategory.PERFORMANCE]
            + reliability_score * self.weights[TrustScoreCategory.RELIABILITY]
            + community_score * self.weights[TrustScoreCategory.COMMUNITY]
            + security_score * self.weights[TrustScoreCategory.SECURITY]
            + economic_score * self.weights[TrustScoreCategory.ECONOMIC]
        )
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if reputation and reputation.trust_score > 0:
            final_score = weighted_score * 0.7 + reputation.trust_score * 0.3
        else:
            final_score = weighted_score
        return min(1000.0, max(0.0, final_score))  # type: ignore[no-any-return]

    def determine_reputation_level(self, trust_score: float) -> ReputationLevel:
        """Determine reputation level based on trust score"""
        if trust_score >= 900:
            return ReputationLevel.MASTER
        elif trust_score >= 750:
            return ReputationLevel.EXPERT
        elif trust_score >= 600:
            return ReputationLevel.ADVANCED
        elif trust_score >= 400:
            return ReputationLevel.INTERMEDIATE
        else:
            return ReputationLevel.BEGINNER


class ReputationService:
    """Main reputation management service — public API for the reputation context.

    Cross-context consumers should import ``AgentReputation`` from this module
    (the service layer) rather than from ``reputation.domain.reputation``.
    """

    def __init__(self, session: Session):
        self.session = session
        self.calculator = TrustScoreCalculator()

    def get_reputation_by_agent(self, agent_id: str) -> AgentReputation | None:
        """Look up an agent's reputation profile by agent_id.

        This is the canonical read path for cross-context consumers that need
        reputation data (certification, rewards, etc.).
        """
        return self.session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()  # type: ignore[return-value]

    def get_reputation_dto(self, agent_id: str) -> ReputationDTO | None:
        """Return a :class:`ReputationDTO` projection for ``agent_id``.

        Cross-context consumers (certification, partnership, badge) should
        prefer this over :meth:`get_reputation_by_agent` so they depend only
        on the shared DTO and not on the reputation context's ORM model.
        Returns ``None`` when the agent has no reputation profile yet.
        """
        reputation = self.get_reputation_by_agent(agent_id)
        if reputation is None:
            return None
        return reputation.to_dto()

    async def create_reputation_profile(self, agent_id: str) -> AgentReputation:
        """Create a new reputation profile for an agent"""
        existing = self.session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if existing:
            return existing  # type: ignore[return-value]
        reputation = AgentReputation(
            agent_id=agent_id,
            trust_score=500.0,
            reputation_level=ReputationLevel.BEGINNER,
            performance_rating=3.0,
            reliability_score=50.0,
            community_rating=3.0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.session.add(reputation)
        self.session.commit()
        self.session.refresh(reputation)
        logger.info("Created reputation profile for agent %s", agent_id)
        return reputation

    async def update_trust_score(self, agent_id: str, event_type: str, impact_data: dict[str, Any]) -> AgentReputation:
        """Update agent trust score based on an event"""
        reputation = await self.create_reputation_profile(agent_id)
        old_trust_score = reputation.trust_score
        old_reputation_level = reputation.reputation_level
        new_trust_score = self.calculator.calculate_composite_trust_score(agent_id, self.session)
        new_reputation_level = self.calculator.determine_reputation_level(new_trust_score)
        event = ReputationEvent(
            agent_id=agent_id,
            event_type=event_type,
            impact_score=new_trust_score - old_trust_score,
            trust_score_before=old_trust_score,
            trust_score_after=new_trust_score,
            reputation_level_before=old_reputation_level,
            reputation_level_after=new_reputation_level,
            event_data=impact_data,
            occurred_at=datetime.now(UTC),
            processed_at=datetime.now(UTC),
        )
        self.session.add(event)
        reputation.trust_score = new_trust_score
        reputation.reputation_level = new_reputation_level
        reputation.updated_at = datetime.now(UTC)
        reputation.last_activity = datetime.now(UTC)
        history_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "trust_score_change": new_trust_score - old_trust_score,
            "new_trust_score": new_trust_score,
            "reputation_level": new_reputation_level.value,
        }
        reputation.reputation_history.append(history_entry)
        self.session.commit()
        self.session.refresh(reputation)
        logger.info("Updated trust score for agent %s: %s -> %s", agent_id, old_trust_score, new_trust_score)
        return reputation

    async def record_job_completion(
        self, agent_id: str, job_id: str, success: bool, response_time: float, earnings: float
    ) -> AgentReputation:
        """Record job completion and update reputation"""
        reputation = await self.create_reputation_profile(agent_id)
        if success:
            reputation.jobs_completed += 1
        else:
            reputation.jobs_failed += 1
        if reputation.average_response_time == 0:
            reputation.average_response_time = response_time
        else:
            reputation.average_response_time = (
                reputation.average_response_time * reputation.jobs_completed + response_time
            ) / (reputation.jobs_completed + 1)
        reputation.total_earnings += earnings
        reputation.transaction_count += 1
        total_jobs = reputation.jobs_completed + reputation.jobs_failed
        reputation.success_rate = reputation.jobs_completed / total_jobs * 100.0 if total_jobs > 0 else 0.0
        reputation.reliability_score = reputation.success_rate
        if success and response_time < 5000:
            reputation.performance_rating = min(5.0, reputation.performance_rating + 0.1)
        elif not success or response_time > 10000:
            reputation.performance_rating = max(1.0, reputation.performance_rating - 0.1)
        reputation.updated_at = datetime.now(UTC)
        reputation.last_activity = datetime.now(UTC)
        impact_data = {
            "job_id": job_id,
            "success": success,
            "response_time": response_time,
            "earnings": earnings,
            "total_jobs": total_jobs,
            "success_rate": reputation.success_rate,
        }
        await self.update_trust_score(agent_id, "job_completed", impact_data)
        logger.info("Recorded job completion for agent %s: success=%s, earnings=%s", agent_id, success, earnings)
        return reputation

    async def add_community_feedback(
        self,
        agent_id: str,
        reviewer_id: str,
        ratings: dict[str, float],
        feedback_text: str = "",
        tags: list[str] | None = None,
    ) -> CommunityFeedback:
        """Add community feedback for an agent"""
        feedback = CommunityFeedback(
            agent_id=agent_id,
            reviewer_id=reviewer_id,
            overall_rating=ratings.get("overall", 3.0),
            performance_rating=ratings.get("performance", 3.0),
            communication_rating=ratings.get("communication", 3.0),
            reliability_rating=ratings.get("reliability", 3.0),
            value_rating=ratings.get("value", 3.0),
            feedback_text=feedback_text,
            feedback_tags=tags or [],
            created_at=datetime.now(UTC),
        )
        self.session.add(feedback)
        self.session.commit()
        self.session.refresh(feedback)
        await self._update_community_rating(agent_id)
        logger.info("Added community feedback for agent %s from reviewer %s", agent_id, reviewer_id)
        return feedback

    async def _update_community_rating(self, agent_id: str) -> None:
        """Update agent's community rating based on feedback"""
        feedbacks = self.session.execute(
            select(CommunityFeedback).where(
                and_(CommunityFeedback.agent_id == agent_id, CommunityFeedback.moderation_status == "approved")
            )
        ).all()
        if not feedbacks:
            return
        total_weight = 0.0
        weighted_sum = 0.0
        for feedback in feedbacks:
            weight = feedback.verification_weight
            rating = feedback.overall_rating
            weighted_sum += rating * weight
            total_weight += weight
        if total_weight > 0:
            avg_rating = weighted_sum / total_weight
            reputation = self.session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
            if reputation:
                reputation.community_rating = avg_rating
                reputation.updated_at = datetime.now(UTC)
                self.session.commit()

    async def get_reputation_summary(self, agent_id: str) -> dict[str, Any]:
        """Get comprehensive reputation summary for an agent"""
        reputation = self.session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if not reputation:
            return {"error": "Reputation profile not found"}
        recent_events = self.session.execute(
            select(ReputationEvent)
            .where(
                and_(
                    ReputationEvent.agent_id == agent_id, ReputationEvent.occurred_at >= datetime.now(UTC) - timedelta(days=30)
                )
            )
            .order_by(desc(ReputationEvent.occurred_at))
            .limit(10)
        ).all()
        recent_feedback = self.session.execute(
            select(CommunityFeedback)
            .where(and_(CommunityFeedback.agent_id == agent_id, CommunityFeedback.moderation_status == "approved"))
            .order_by(desc(CommunityFeedback.created_at))
            .limit(5)
        ).all()
        return {
            "agent_id": agent_id,
            "trust_score": reputation.trust_score,
            "reputation_level": reputation.reputation_level.value,
            "performance_rating": reputation.performance_rating,
            "reliability_score": reputation.reliability_score,
            "community_rating": reputation.community_rating,
            "total_earnings": reputation.total_earnings,
            "transaction_count": reputation.transaction_count,
            "success_rate": reputation.success_rate,
            "jobs_completed": reputation.jobs_completed,
            "jobs_failed": reputation.jobs_failed,
            "average_response_time": reputation.average_response_time,
            "dispute_count": reputation.dispute_count,
            "certifications": reputation.certifications,
            "specialization_tags": reputation.specialization_tags,
            "geographic_region": reputation.geographic_region,
            "last_activity": reputation.last_activity.isoformat(),
            "recent_events": [
                {
                    "event_type": event.event_type,
                    "impact_score": event.impact_score,
                    "occurred_at": event.occurred_at.isoformat(),
                }
                for event in recent_events
            ],
            "recent_feedback": [
                {
                    "overall_rating": feedback.overall_rating,
                    "feedback_text": feedback.feedback_text,
                    "created_at": feedback.created_at.isoformat(),
                }
                for feedback in recent_feedback
            ],
        }

    async def get_leaderboard(
        self, category: str = "trust_score", limit: int = 50, region: str | None = None
    ) -> list[dict[str, Any]]:
        """Get reputation leaderboard"""
        query = select(AgentReputation).order_by(getattr(AgentReputation, category).desc()).limit(limit)
        if region:
            query = query.where(AgentReputation.geographic_region == region)
        reputations = self.session.execute(query).all()
        leaderboard = []
        for rank, reputation in enumerate(reputations, 1):
            leaderboard.append(
                {
                    "rank": rank,
                    "agent_id": reputation.agent_id,
                    "trust_score": reputation.trust_score,
                    "reputation_level": reputation.reputation_level.value,
                    "performance_rating": reputation.performance_rating,
                    "reliability_score": reputation.reliability_score,
                    "community_rating": reputation.community_rating,
                    "total_earnings": reputation.total_earnings,
                    "transaction_count": reputation.transaction_count,
                    "geographic_region": reputation.geographic_region,
                    "specialization_tags": reputation.specialization_tags,
                }
            )
        return leaderboard
