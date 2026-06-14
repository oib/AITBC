"""
Badge System - Achievement and recognition badge system
"""
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4
from aitbc import get_logger
logger = get_logger(__name__)
from app.domain.certification import AchievementBadge, AgentBadge, BadgeType  # type: ignore[import-not-found]
from app.domain.reputation import AgentReputation  # type: ignore[import-not-found]
from sqlmodel import Session, and_, select

class BadgeSystem:
    """Achievement and recognition badge system"""

    def __init__(self) -> None:
        self.badge_categories = {'performance': {'early_adopter': {'threshold': 1, 'metric': 'jobs_completed'}, 'consistent_performer': {'threshold': 50, 'metric': 'jobs_completed'}, 'top_performer': {'threshold': 100, 'metric': 'jobs_completed'}, 'excellence_achiever': {'threshold': 500, 'metric': 'jobs_completed'}}, 'reliability': {'reliable_start': {'threshold': 10, 'metric': 'successful_transactions'}, 'dependable_partner': {'threshold': 50, 'metric': 'successful_transactions'}, 'trusted_provider': {'threshold': 100, 'metric': 'successful_transactions'}, 'rock_star': {'threshold': 500, 'metric': 'successful_transactions'}}, 'financial': {'first_earning': {'threshold': 0.01, 'metric': 'total_earnings'}, 'growing_income': {'threshold': 10, 'metric': 'total_earnings'}, 'successful_earner': {'threshold': 100, 'metric': 'total_earnings'}, 'top_earner': {'threshold': 1000, 'metric': 'total_earnings'}}, 'community': {'community_starter': {'threshold': 1, 'metric': 'community_contributions'}, 'active_contributor': {'threshold': 10, 'metric': 'community_contributions'}, 'community_leader': {'threshold': 50, 'metric': 'community_contributions'}, 'community_icon': {'threshold': 100, 'metric': 'community_contributions'}}}

    async def create_badge(self, session: Session, badge_name: str, badge_type: BadgeType, description: str, criteria: dict[str, Any], created_by: str) -> AchievementBadge:
        """Create a new achievement badge"""
        badge_id = f'badge_{uuid4().hex[:8]}'
        badge = AchievementBadge(badge_id=badge_id, badge_name=badge_name, badge_type=badge_type, description=description, achievement_criteria=criteria, required_metrics=criteria.get('required_metrics', []), threshold_values=criteria.get('threshold_values', {}), rarity=criteria.get('rarity', 'common'), point_value=criteria.get('point_value', 10), category=criteria.get('category', 'general'), color_scheme=criteria.get('color_scheme', {}), display_properties=criteria.get('display_properties', {}), is_limited=criteria.get('is_limited', False), max_awards=criteria.get('max_awards'), available_from=datetime.now(UTC), available_until=criteria.get('available_until'))
        session.add(badge)
        session.commit()
        session.refresh(badge)
        logger.info('Badge %s created: %s', badge_id, badge_name)
        return badge

    async def award_badge(self, session: Session, agent_id: str, badge_id: str, awarded_by: str, award_reason: str='', context: dict[str, Any] | None=None) -> tuple[bool, AgentBadge | None, str]:
        """Award a badge to an agent"""
        badge = session.execute(select(AchievementBadge).where(AchievementBadge.badge_id == badge_id)).first()
        if not badge:
            return (False, None, 'Badge not found')
        if not badge.is_active:
            return (False, None, 'Badge is not active')
        if badge.is_limited and badge.current_awards >= badge.max_awards:
            return (False, None, 'Badge has reached maximum awards')
        existing_badge = session.execute(select(AgentBadge).where(and_(AgentBadge.agent_id == agent_id, AgentBadge.badge_id == badge_id))).first()
        if existing_badge:
            return (False, None, 'Agent already has this badge')
        eligibility_result = await self.verify_badge_eligibility(session, agent_id, badge)
        if not eligibility_result['eligible']:
            return (False, None, f"Agent not eligible: {eligibility_result['reason']}")
        agent_badge = AgentBadge(agent_id=agent_id, badge_id=badge_id, awarded_by=awarded_by, award_reason=award_reason or f'Awarded for meeting {badge.badge_name} criteria', achievement_context=context or eligibility_result.get('context', {}), metrics_at_award=eligibility_result.get('metrics', {}), supporting_evidence=eligibility_result.get('evidence', []))
        session.add(agent_badge)
        session.commit()
        session.refresh(agent_badge)
        badge.current_awards += 1
        session.commit()
        logger.info('Badge %s awarded to agent %s', badge_id, agent_id)
        return (True, agent_badge, 'Badge awarded successfully')

    async def verify_badge_eligibility(self, session: Session, agent_id: str, badge: AchievementBadge) -> dict[str, Any]:
        """Verify if agent is eligible for a badge"""
        reputation = session.execute(select(AgentReputation).where(AgentReputation.agent_id == agent_id)).first()
        if not reputation:
            return {'eligible': False, 'reason': 'No agent data available', 'metrics': {}, 'evidence': []}
        required_metrics = badge.required_metrics
        threshold_values = badge.threshold_values
        eligibility_results = []
        metrics_data = {}
        evidence = []
        for metric in required_metrics:
            threshold = threshold_values.get(metric, 0)
            metric_value = self.get_metric_value(reputation, metric)
            metrics_data[metric] = metric_value
            if metric_value >= threshold:
                eligibility_results.append(True)
                evidence.append({'metric': metric, 'value': metric_value, 'threshold': threshold, 'met': True})
            else:
                eligibility_results.append(False)
                evidence.append({'metric': metric, 'value': metric_value, 'threshold': threshold, 'met': False})
        all_met = all(eligibility_results)
        return {'eligible': all_met, 'reason': 'All criteria met' if all_met else 'Some criteria not met', 'metrics': metrics_data, 'evidence': evidence, 'context': {'badge_name': badge.badge_name, 'badge_type': badge.badge_type.value, 'verification_date': datetime.now(UTC).isoformat()}}

    def get_metric_value(self, reputation: AgentReputation, metric: str) -> float:
        """Get metric value from reputation data"""
        metric_map = {'jobs_completed': float(reputation.jobs_completed), 'successful_transactions': float(reputation.jobs_completed * (reputation.success_rate / 100)), 'total_earnings': reputation.total_earnings, 'community_contributions': float(reputation.community_contributions or 0), 'trust_score': reputation.trust_score, 'reliability_score': reputation.reliability_score, 'performance_rating': reputation.performance_rating, 'transaction_count': float(reputation.transaction_count)}
        return float(metric_map.get(metric, 0.0))

    async def check_and_award_automatic_badges(self, session: Session, agent_id: str) -> list[dict[str, Any]]:
        """Check and award automatic badges for an agent"""
        awarded_badges = []
        automatic_badges = session.execute(select(AchievementBadge).where(and_(AchievementBadge.is_active, AchievementBadge.badge_type.in_([BadgeType.ACHIEVEMENT, BadgeType.MILESTONE])))).all()
        for badge in automatic_badges:
            eligibility_result = await self.verify_badge_eligibility(session, agent_id, badge)
            if eligibility_result['eligible']:
                existing = session.execute(select(AgentBadge).where(and_(AgentBadge.agent_id == agent_id, AgentBadge.badge_id == badge.badge_id))).first()
                if not existing:
                    success, agent_badge, message = await self.award_badge(session, agent_id, badge.badge_id, 'system', 'Automatic badge award', eligibility_result.get('context'))
                    if success and agent_badge is not None:
                        awarded_badges.append({'badge_id': badge.badge_id, 'badge_name': badge.badge_name, 'badge_type': badge.badge_type.value, 'awarded_at': agent_badge.awarded_at.isoformat(), 'reason': message})
        return awarded_badges