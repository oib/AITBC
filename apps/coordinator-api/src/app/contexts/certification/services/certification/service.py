"""
Certification and Partnership Service - Main service facade
Combines certification, partnership, and badge systems
"""

from typing import Any

from app.domain.certification import (  # type: ignore[import-not-found]
    AchievementBadge,
    AgentBadge,
    AgentCertification,
    AgentPartnership,
    CertificationStatus,
    VerificationRecord,
)
from sqlmodel import Session, select

from .badge_system import BadgeSystem
from .certification_system import CertificationSystem
from .partnership_manager import PartnershipManager


class CertificationAndPartnershipService:
    """Main service for certification and partnership management"""

    def __init__(self, session: Session):
        self.session = session
        self.certification_system = CertificationSystem()
        self.partnership_manager = PartnershipManager()
        self.badge_system = BadgeSystem()

    async def get_agent_certification_summary(self, agent_id: str) -> dict[str, Any]:
        """Get comprehensive certification summary for an agent"""

        # Get certifications
        certifications = self.session.execute(select(AgentCertification).where(AgentCertification.agent_id == agent_id)).all()

        # Get partnerships
        partnerships = self.session.execute(select(AgentPartnership).where(AgentPartnership.agent_id == agent_id)).all()

        # Get badges
        badges = self.session.execute(select(AgentBadge).where(AgentBadge.agent_id == agent_id)).all()

        # Get verification records
        verifications = self.session.execute(select(VerificationRecord).where(VerificationRecord.agent_id == agent_id)).all()

        return {
            "agent_id": agent_id,
            "certifications": {
                "total": len(certifications),
                "active": len([c for c in certifications if c.status == CertificationStatus.ACTIVE]),
                "highest_level": max([c.certification_level.value for c in certifications]) if certifications else None,
                "details": [
                    {
                        "certification_id": c.certification_id,
                        "level": c.certification_level.value,
                        "status": c.status.value,
                        "issued_at": c.issued_at.isoformat(),
                        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
                        "privileges": c.granted_privileges,
                    }
                    for c in certifications
                ],
            },
            "partnerships": {
                "total": len(partnerships),
                "active": len([p for p in partnerships if p.status == "active"]),
                "programs": [p.program_id for p in partnerships],
                "details": [
                    {
                        "partnership_id": p.partnership_id,
                        "program_type": p.partnership_type.value,
                        "current_tier": p.current_tier,
                        "status": p.status,
                        "performance_score": p.performance_score,
                        "total_earnings": p.total_earnings,
                    }
                    for p in partnerships
                ],
            },
            "badges": {
                "total": len(badges),
                "featured": len([b for b in badges if b.is_featured]),
                "categories": {},
                "details": [
                    {
                        "badge_id": b.badge_id,
                        "badge_name": b.badge_name,
                        "badge_type": b.badge_type.value,
                        "awarded_at": b.awarded_at.isoformat(),
                        "is_featured": b.is_featured,
                        "point_value": self.get_badge_point_value(b.badge_id),
                    }
                    for b in badges
                ],
            },
            "verifications": {
                "total": len(verifications),
                "passed": len([v for v in verifications if v.status == "passed"]),
                "failed": len([v for v in verifications if v.status == "failed"]),
                "pending": len([v for v in verifications if v.status == "pending"]),
            },
        }

    def get_badge_point_value(self, badge_id: str) -> int:
        """Get point value for a badge"""

        badge = self.session.execute(select(AchievementBadge).where(AchievementBadge.badge_id == badge_id)).first()

        return badge.point_value if badge else 0
