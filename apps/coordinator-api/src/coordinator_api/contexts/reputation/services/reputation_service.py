"""
Agent Reputation and Trust Service
Implements reputation management, trust score calculations, and economic profiling
"""

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from aitbc_shared.models import ReputationDTO
from sqlmodel import Session, and_, col, desc, select

from aitbc.aitbc_logging import get_logger

from ..domain.reputation import (
    AgentReputation,
    CommunityFeedback,
    ReputationEvent,
    ReputationLevel,
    TrustScoreCategory,
)
from starlette.concurrency import run_in_threadpool

logger = get_logger(__name__)

# Upper bound on reputation rows the leaderboard live-scores per request.
# The batched computation is ~2 statements regardless of candidate count, so
# this only guards against a pathological table; it comfortably exceeds the
# route's limit=500 and any realistic agent population.
_LEADERBOARD_MAX_CANDIDATES = 5000


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

    @staticmethod
    def _performance_score_from(reputation: AgentReputation) -> float:
        """Performance component from an already-fetched reputation row."""
        base_score = reputation.performance_rating / 5.0 * 1000
        if reputation.transaction_count > 0:
            success_modifier = reputation.success_rate / 100.0
            base_score *= success_modifier
        if reputation.average_response_time > 0:
            response_modifier = max(0.5, 1.0 - reputation.average_response_time / 10000.0)
            base_score *= response_modifier
        return min(1000.0, max(0.0, base_score))

    def calculate_performance_score(
        self, agent_id: str, session: Session, time_window: timedelta = timedelta(days=30)
    ) -> float:
        """Calculate performance-based trust score component"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()
        if not reputation:
            return 500.0
        return self._performance_score_from(reputation)

    @staticmethod
    def _reliability_score_from(reputation: AgentReputation) -> float:
        """Reliability component from an already-fetched reputation row."""
        base_score = reputation.reliability_score * 10
        if reputation.uptime_percentage > 0:
            uptime_modifier = reputation.uptime_percentage / 100.0
            base_score *= uptime_modifier
        total_jobs = reputation.jobs_completed + reputation.jobs_failed
        if total_jobs > 0:
            completion_ratio = reputation.jobs_completed / total_jobs
            base_score *= completion_ratio
        return min(1000.0, max(0.0, base_score))

    def calculate_reliability_score(
        self, agent_id: str, session: Session, time_window: timedelta = timedelta(days=30)
    ) -> float:
        """Calculate reliability-based trust score component"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()
        if not reputation:
            return 500.0
        return self._reliability_score_from(reputation)

    @staticmethod
    def _community_score_from_feedbacks(feedbacks: Sequence[CommunityFeedback]) -> float:
        """Community component from already-fetched feedback rows."""
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
        feedbacks = session.execute(feedback_query).scalars().all()
        return self._community_score_from_feedbacks(feedbacks)

    @staticmethod
    def _security_score_from(reputation: AgentReputation) -> float:
        """Security component from an already-fetched reputation row."""
        base_score = 800.0
        if reputation.transaction_count > 0:
            dispute_ratio = reputation.dispute_count / reputation.transaction_count
            dispute_penalty = dispute_ratio * 500
            base_score -= dispute_penalty
        if reputation.certifications:
            certification_boost = min(200.0, len(reputation.certifications) * 50.0)
            base_score += certification_boost
        return min(1000.0, max(0.0, base_score))

    def calculate_security_score(self, agent_id: str, session: Session, time_window: timedelta = timedelta(days=180)) -> float:
        """Calculate security-based trust score component"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()
        if not reputation:
            return 500.0
        return self._security_score_from(reputation)

    @staticmethod
    def _economic_score_from(reputation: AgentReputation) -> float:
        """Economic component from an already-fetched reputation row."""
        if reputation.total_earnings > 0 and reputation.transaction_count > 0:
            avg_earning_per_transaction = reputation.total_earnings / reputation.transaction_count
            earning_modifier = min(2.0, float(avg_earning_per_transaction / Decimal("0.1")))
            base_score = 500.0 * earning_modifier
        else:
            base_score = 500.0
        if reputation.success_rate > 0:
            success_modifier = reputation.success_rate / 100.0
            base_score *= success_modifier
        return min(1000.0, max(0.0, base_score))

    def calculate_economic_score(self, agent_id: str, session: Session, time_window: timedelta = timedelta(days=30)) -> float:
        """Calculate economic-based trust score component"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()
        if not reputation:
            return 500.0
        return self._economic_score_from(reputation)

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
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()
        if reputation and reputation.trust_score > 0:
            final_score = weighted_score * 0.7 + reputation.trust_score * 0.3
        else:
            final_score = weighted_score
        return min(1000.0, max(0.0, final_score))  # type: ignore[no-any-return]

    def calculate_composite_trust_scores(
        self, reputations: Sequence[AgentReputation], session: Session, time_window: timedelta = timedelta(days=30)
    ) -> dict[str, float]:
        """Batched live composite for already-fetched reputation rows (#2475).

        Identical math to ``calculate_composite_trust_score`` per agent, but
        the five per-agent ``AgentReputation`` selects collapse into the rows
        in hand and ``CommunityFeedback`` is read in a single query — a fixed
        ~2 statements for the whole set instead of ~6 per agent. Used by the
        unauthenticated leaderboard, which may request up to 500 rows.
        """
        feedback_by_agent: dict[str, list[CommunityFeedback]] = {}
        agent_ids = [reputation.agent_id for reputation in reputations]
        if agent_ids:
            cutoff_date = datetime.now(UTC) - time_window
            feedback_rows = (
                session.execute(
                    select(CommunityFeedback).where(
                        and_(
                            col(CommunityFeedback.agent_id).in_(agent_ids),
                            CommunityFeedback.created_at >= cutoff_date,
                            CommunityFeedback.moderation_status == "approved",
                        )
                    )
                )
                .scalars()
                .all()
            )
            for feedback in feedback_rows:
                feedback_by_agent.setdefault(feedback.agent_id, []).append(feedback)

        scores: dict[str, float] = {}
        for reputation in reputations:
            weighted_score = (
                self._performance_score_from(reputation) * self.weights[TrustScoreCategory.PERFORMANCE]
                + self._reliability_score_from(reputation) * self.weights[TrustScoreCategory.RELIABILITY]
                + self._community_score_from_feedbacks(feedback_by_agent.get(reputation.agent_id, ()))
                * self.weights[TrustScoreCategory.COMMUNITY]
                + self._security_score_from(reputation) * self.weights[TrustScoreCategory.SECURITY]
                + self._economic_score_from(reputation) * self.weights[TrustScoreCategory.ECONOMIC]
            )
            if reputation.trust_score > 0:
                final_score = weighted_score * 0.7 + reputation.trust_score * 0.3
            else:
                final_score = weighted_score
            scores[reputation.agent_id] = min(1000.0, max(0.0, final_score))
        return scores

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
        return self.session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()

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

    def create_reputation_profile(self, agent_id: str) -> AgentReputation:
        """Create a new reputation profile for an agent"""
        existing = self.session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()
        if existing:
            return existing  # type: ignore[no-any-return]
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
        reputation = self.create_reputation_profile(agent_id)
        old_trust_score = reputation.trust_score
        old_reputation_level = reputation.reputation_level
        new_trust_score = await run_in_threadpool(self.calculator.calculate_composite_trust_score, agent_id, self.session)
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
        (await run_in_threadpool(self.session.commit))
        (await run_in_threadpool(self.session.refresh, reputation))
        logger.info("Updated trust score for agent %s: %s -> %s", agent_id, old_trust_score, new_trust_score)
        return reputation

    async def record_job_completion(
        self, agent_id: str, job_id: str, success: bool, response_time: float, earnings: Decimal
    ) -> AgentReputation:
        """Record job completion and update reputation"""
        reputation = self.create_reputation_profile(agent_id)
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
            "earnings": str(earnings),
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
        job_id: str | None = None,
    ) -> CommunityFeedback:
        """Add community feedback for an agent"""
        # #2693: CommunityFeedback is table=True — its Field(ge/le) is never
        # enforced — so bound the values here too; the HTTP layer validates
        # first, this guards any other caller.
        for key in ("overall", "performance", "communication", "reliability", "value"):
            value = ratings.get(key, 3.0)
            if not math.isfinite(value) or not 1.0 <= value <= 5.0:
                raise ValueError(f"rating '{key}' must be finite and within 1..5")
        feedback = CommunityFeedback(
            agent_id=agent_id,
            reviewer_id=reviewer_id,
            job_id=job_id,
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
        (await run_in_threadpool(self.session.commit))
        (await run_in_threadpool(self.session.refresh, feedback))
        await self._update_community_rating(agent_id)
        logger.info("Added community feedback for agent %s from reviewer %s", agent_id, reviewer_id)
        return feedback

    async def _update_community_rating(self, agent_id: str) -> None:
        """Update agent's community rating based on feedback"""
        feedbacks = (
            (
                await run_in_threadpool(
                    self.session.execute,
                    select(CommunityFeedback).where(
                        and_(CommunityFeedback.agent_id == agent_id, CommunityFeedback.moderation_status == "approved")
                    ),
                )
            )
            .scalars()
            .all()
        )
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
            reputation = (
                (
                    await run_in_threadpool(
                        self.session.execute, select(AgentReputation).where(AgentReputation.agent_id == agent_id)
                    )
                )
                .scalars()
                .first()
            )
            if reputation:
                reputation.community_rating = avg_rating
                reputation.updated_at = datetime.now(UTC)
                (await run_in_threadpool(self.session.commit))

    def get_reputation_summary(self, agent_id: str) -> dict[str, Any]:
        """Get comprehensive reputation summary for an agent"""
        reputation = (
            self.session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).scalars().first()
        )
        if not reputation:
            return {"error": "Reputation profile not found"}
        # #2406: the headline trust_score/level are the live composite, not the
        # stored columns — the stored values are only a cache written by
        # update_trust_score and drift between events. All reputation reads
        # (profile, trust-score, leaderboard) report this same composite so the
        # three commands can never disagree.
        trust_score = self.calculator.calculate_composite_trust_score(agent_id, self.session)
        reputation_level = self.calculator.determine_reputation_level(trust_score).value
        recent_events = (
            self.session.execute(
                select(ReputationEvent)
                .where(
                    and_(
                        ReputationEvent.agent_id == agent_id,
                        ReputationEvent.occurred_at >= datetime.now(UTC) - timedelta(days=30),
                    )
                )
                .order_by(desc(ReputationEvent.occurred_at))
                .limit(10)
            )
            .scalars()
            .all()
        )
        recent_feedback = (
            self.session.execute(
                select(CommunityFeedback)
                .where(and_(CommunityFeedback.agent_id == agent_id, CommunityFeedback.moderation_status == "approved"))
                .order_by(desc(CommunityFeedback.created_at))
                .limit(5)
            )
            .scalars()
            .all()
        )
        return {
            "agent_id": agent_id,
            "trust_score": trust_score,
            "reputation_level": reputation_level,
            "performance_rating": reputation.performance_rating,
            "reliability_score": reputation.reliability_score,
            "community_rating": reputation.community_rating,
            "total_earnings": reputation.total_earnings,
            "transaction_count": reputation.transaction_count,
            "success_rate": reputation.success_rate,
            "jobs_completed": reputation.jobs_completed,
            "jobs_failed": reputation.jobs_failed,
            "average_response_time": reputation.average_response_time,
            # Stored in milliseconds (see record_job_completion callers passing
            # duration_ms) — surfaced explicitly so clients need not guess (#2406).
            "average_response_time_unit": "ms",
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
        if not hasattr(AgentReputation, category):
            category = "trust_score"
        if category == "trust_score":
            # #2475: entries report the live composite, so the ranking must use
            # it too — pre-selecting the page by the stored cache column (which
            # drifts between events) could exclude the true live leaders. The
            # batched computation costs a fixed ~2 statements for the whole
            # candidate set, so fetch every matching row (bounded by
            # _LEADERBOARD_MAX_CANDIDATES) instead of a stored-score page.
            query = (
                select(AgentReputation).order_by(getattr(AgentReputation, category).desc()).limit(_LEADERBOARD_MAX_CANDIDATES)
            )
        else:
            query = select(AgentReputation).order_by(getattr(AgentReputation, category).desc()).limit(limit)
        if region:
            query = query.where(AgentReputation.geographic_region == region)
        result = await run_in_threadpool(self.session.execute, query)
        reputations = result.scalars().all()
        scores = await run_in_threadpool(self.calculator.calculate_composite_trust_scores, reputations, self.session)
        entries = self._leaderboard_entries(reputations, scores)
        if category == "trust_score":
            entries.sort(key=lambda e: (-float(e["trust_score"]), str(e["agent_id"])))
            entries = entries[:limit]
        for rank, entry in enumerate(entries, 1):
            entry["rank"] = rank
        return entries

    def _leaderboard_entries(self, reputations: Sequence[AgentReputation], scores: dict[str, float]) -> list[dict[str, Any]]:
        """Build leaderboard rows reporting the live composite trust score.

        ``scores`` comes from ``calculate_composite_trust_scores`` — the same
        ``TrustScoreCalculator`` math the profile and trust-score endpoints
        use, so all three reputation reads agree for a given agent (#2406).
        Pure Python now that the batched computation runs ahead of it (#2475).
        """
        leaderboard = []
        for reputation in reputations:
            trust_score = scores[reputation.agent_id]
            leaderboard.append(
                {
                    "rank": 0,  # assigned by the caller after any re-sort
                    "agent_id": reputation.agent_id,
                    "trust_score": trust_score,
                    "reputation_level": self.calculator.determine_reputation_level(trust_score).value,
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
