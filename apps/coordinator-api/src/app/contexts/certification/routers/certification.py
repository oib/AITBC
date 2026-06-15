from sqlalchemy import desc
from sqlalchemy.orm import Session
from sqlmodel import select

"\nCertification and Partnership API Endpoints\nREST API for agent certification, partnership programs, and badge system\n"
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

logger = get_logger(__name__)
from ....domain.certification import (
    AchievementBadge,
    AgentBadge,
    AgentCertification,
    AgentPartnership,
    BadgeType,
    CertificationLevel,
    CertificationRequirement,
    CertificationStatus,
    PartnershipProgram,
    PartnershipType,
    VerificationRecord,
    VerificationType,
)
from ....storage import get_session
from ..services.certification import BadgeSystem, CertificationAndPartnershipService, CertificationSystem, PartnershipManager

router = APIRouter(prefix="/v1/certification", tags=["certification"])


class CertificationRequest(BaseModel):
    """Request model for agent certification"""

    agent_id: str
    level: CertificationLevel
    certification_type: str = Field(default="standard", description="Certification type")
    issued_by: str = Field(description="Who is issuing the certification")


class CertificationResponse(BaseModel):
    """Response model for agent certification"""

    certification_id: str
    agent_id: str
    certification_level: str
    certification_type: str
    status: str
    issued_by: str
    issued_at: str
    expires_at: str | None
    verification_hash: str
    requirements_met: list[str]
    granted_privileges: list[str]
    access_levels: list[str]


class PartnershipApplicationRequest(BaseModel):
    """Request model for partnership application"""

    agent_id: str
    program_id: str
    application_data: dict[str, Any] = Field(default_factory=dict, description="Application data")


class PartnershipProgramRequest(BaseModel):
    """Request model for partnership program creation"""

    program_name: str
    program_type: PartnershipType
    description: str
    created_by: str
    tier_levels: list[str] = Field(default_factory=lambda: ["basic", "premium"])
    max_participants: int | None = Field(default=None, description="Maximum participants")
    launch_immediately: bool = Field(default=False, description="Launch program immediately")


class PartnershipResponse(BaseModel):
    """Response model for partnership"""

    partnership_id: str
    agent_id: str
    program_id: str
    partnership_type: str
    current_tier: str
    status: str
    applied_at: str
    approved_at: str | None
    performance_score: float
    total_earnings: float
    earned_benefits: list[str]


class BadgeCreationRequest(BaseModel):
    """Request model for badge creation"""

    badge_name: str
    badge_type: BadgeType
    description: str
    criteria: dict[str, Any] = Field(description="Badge criteria and thresholds")
    created_by: str


class BadgeAwardRequest(BaseModel):
    """Request model for badge award"""

    agent_id: str
    badge_id: str
    awarded_by: str
    award_reason: str = Field(default="", description="Reason for awarding badge")
    context: dict[str, Any] = Field(default_factory=dict, description="Award context")


class BadgeResponse(BaseModel):
    """Response model for badge"""

    badge_id: str
    badge_name: str
    badge_type: str
    description: str
    rarity: str
    point_value: int
    category: str
    awarded_at: str
    is_featured: bool
    badge_icon: str


class AgentCertificationSummary(BaseModel):
    """Response model for agent certification summary"""

    agent_id: str
    certifications: dict[str, Any]
    partnerships: dict[str, Any]
    badges: dict[str, Any]
    verifications: dict[str, Any]


@router.post("/certify", response_model=CertificationResponse)
@rate_limit(rate=20, per=60)
async def certify_agent(
    request: Request, certification_request: CertificationRequest, session: Session = Depends(get_session)
) -> CertificationResponse:
    """Certify an agent at a specific level"""
    certification_service = CertificationAndPartnershipService(session)  # type: ignore[arg-type]
    try:
        success, certification, errors = await certification_service.certification_system.certify_agent(
            session=session,
            agent_id=certification_request.agent_id,
            level=certification_request.level,
            issued_by=certification_request.issued_by,
            certification_type=certification_request.certification_type,
        )  # type: ignore[arg-type]
        if not success:
            raise HTTPException(status_code=400, detail=f"Certification failed: {'; '.join(errors)}")
        return CertificationResponse(
            certification_id=certification.certification_id,
            agent_id=certification.agent_id,
            certification_level=certification.certification_level.value,
            certification_type=certification.certification_type,
            status=certification.status.value,
            issued_by=certification.issued_by,
            issued_at=certification.issued_at.isoformat(),
            expires_at=certification.expires_at.isoformat() if certification.expires_at else None,
            verification_hash=certification.verification_hash,
            requirements_met=certification.requirements_met,
            granted_privileges=certification.granted_privileges,
            access_levels=certification.access_levels,
        )  # type: ignore[union-attr]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error certifying agent: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/certifications/{certification_id}/renew")
@rate_limit(rate=20, per=60)
async def renew_certification(
    request: Request, certification_id: str, renewed_by: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Renew an existing certification"""
    certification_service = CertificationAndPartnershipService(session)  # type: ignore[arg-type]
    try:
        success, message = await certification_service.certification_system.renew_certification(
            session=session, certification_id=certification_id, renewed_by=renewed_by
        )  # type: ignore[arg-type]
        if not success:
            raise HTTPException(status_code=400, detail=message)
        return {"success": True, "message": message, "certification_id": certification_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error renewing certification: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/certifications/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_agent_certifications(
    request: Request,
    agent_id: str,
    status: str | None = Query(default=None, description="Filter by status"),
    session: Session = Depends(get_session),
) -> list[CertificationResponse]:
    """Get certifications for an agent"""
    try:
        query = select(AgentCertification).where(AgentCertification.agent_id == agent_id)
        if status:
            query = query.where(AgentCertification.status == CertificationStatus(status))
        certifications = session.execute(query.order_by(desc(AgentCertification.issued_at))).all()  # type: ignore[arg-type]
        return [
            CertificationResponse(
                certification_id=cert.certification_id,
                agent_id=cert.agent_id,
                certification_level=cert.certification_level.value,
                certification_type=cert.certification_type,
                status=cert.status.value,
                issued_by=cert.issued_by,
                issued_at=cert.issued_at.isoformat(),
                expires_at=cert.expires_at.isoformat() if cert.expires_at else None,
                verification_hash=cert.verification_hash,
                requirements_met=cert.requirements_met,
                granted_privileges=cert.granted_privileges,
                access_levels=cert.access_levels,
            )
            for cert in certifications
        ]
    except Exception as e:
        logger.error("Error getting certifications for agent %s: %s", agent_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/partnerships/programs")
@rate_limit(rate=20, per=60)
async def create_partnership_program(
    request: Request, program_request: PartnershipProgramRequest, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Create a new partnership program"""
    partnership_manager = PartnershipManager()
    try:
        program = await partnership_manager.create_partnership_program(
            session=session,
            program_name=request.program_name,
            program_type=request.program_type,
            description=request.description,
            created_by=request.created_by,
            tier_levels=request.tier_levels,
            max_participants=request.max_participants,
            launch_immediately=request.launch_immediately,
        )  # type: ignore[attr-defined, arg-type]
        return {
            "program_id": program.program_id,
            "program_name": program.program_name,
            "program_type": program.program_type.value,
            "status": program.status,
            "tier_levels": program.tier_levels,
            "max_participants": program.max_participants,
            "current_participants": program.current_participants,
            "created_at": program.created_at.isoformat(),
            "launched_at": program.launched_at.isoformat() if program.launched_at else None,
        }
    except Exception as e:
        logger.error("Error creating partnership program: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/partnerships/apply", response_model=PartnershipResponse)
@rate_limit(rate=20, per=60)
async def apply_for_partnership(
    request: Request, application: PartnershipApplicationRequest, session: Session = Depends(get_session)
) -> PartnershipResponse:
    """Apply for a partnership program"""
    partnership_manager = PartnershipManager()
    try:
        success, partnership, errors = await partnership_manager.apply_for_partnership(
            session=session,
            agent_id=application.agent_id,
            program_id=application.program_id,
            application_data=application.application_data,
        )  # type: ignore[arg-type]
        if not success:
            raise HTTPException(status_code=400, detail=f"Application failed: {'; '.join(errors)}")
        return PartnershipResponse(
            partnership_id=partnership.partnership_id,
            agent_id=partnership.agent_id,
            program_id=partnership.program_id,
            partnership_type=partnership.partnership_type.value,
            current_tier=partnership.current_tier,
            status=partnership.status,
            applied_at=partnership.applied_at.isoformat(),
            approved_at=partnership.approved_at.isoformat() if partnership.approved_at else None,
            performance_score=partnership.performance_score,
            total_earnings=partnership.total_earnings,
            earned_benefits=partnership.earned_benefits,
        )  # type: ignore[union-attr]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error applying for partnership: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/partnerships/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_agent_partnerships(
    request: Request,
    agent_id: str,
    status: str | None = Query(default=None, description="Filter by status"),
    partnership_type: str | None = Query(default=None, description="Filter by partnership type"),
    session: Session = Depends(get_session),
) -> list[PartnershipResponse]:
    """Get partnerships for an agent"""
    try:
        query = select(AgentPartnership).where(AgentPartnership.agent_id == agent_id)
        if status:
            query = query.where(AgentPartnership.status == status)
        if partnership_type:
            query = query.where(AgentPartnership.partnership_type == PartnershipType(partnership_type))
        partnerships = session.execute(query.order_by(desc(AgentPartnership.applied_at))).all()  # type: ignore[arg-type]
        return [
            PartnershipResponse(
                partnership_id=partner.partnership_id,
                agent_id=partner.agent_id,
                program_id=partner.program_id,
                partnership_type=partner.partnership_type.value,
                current_tier=partner.current_tier,
                status=partner.status,
                applied_at=partner.applied_at.isoformat(),
                approved_at=partner.approved_at.isoformat() if partner.approved_at else None,
                performance_score=partner.performance_score,
                total_earnings=partner.total_earnings,
                earned_benefits=partner.earned_benefits,
            )
            for partner in partnerships
        ]
    except Exception as e:
        logger.error("Error getting partnerships for agent %s: %s", agent_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/partnerships/programs")
@rate_limit(rate=200, per=60)
async def list_partnership_programs(
    request: Request,
    partnership_type: str | None = Query(default=None, description="Filter by partnership type"),
    status: str | None = Query(default="active", description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """List available partnership programs"""
    try:
        query = select(PartnershipProgram)
        if partnership_type:
            query = query.where(PartnershipProgram.program_type == PartnershipType(partnership_type))
        if status:
            query = query.where(PartnershipProgram.status == status)
        programs = session.execute(query.order_by(desc(PartnershipProgram.created_at)).limit(limit)).all()  # type: ignore[arg-type]
        return [
            {
                "program_id": program.program_id,
                "program_name": program.program_name,
                "program_type": program.program_type.value,
                "description": program.description,
                "status": program.status,
                "tier_levels": program.tier_levels,
                "max_participants": program.max_participants,
                "current_participants": program.current_participants,
                "created_at": program.created_at.isoformat(),
                "launched_at": program.launched_at.isoformat() if program.launched_at else None,
                "expires_at": program.expires_at.isoformat() if program.expires_at else None,
            }
            for program in programs
        ]
    except Exception as e:
        logger.error("Error listing partnership programs: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/badges")
@rate_limit(rate=20, per=60)
async def create_badge(
    request: Request, badge_request: BadgeCreationRequest, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Create a new achievement badge"""
    badge_system = BadgeSystem()
    try:
        badge = await badge_system.create_badge(
            session=session,
            badge_name=badge_request.badge_name,
            badge_type=badge_request.badge_type,
            description=badge_request.description,
            criteria=badge_request.criteria,
            created_by=badge_request.created_by,
        )  # type: ignore[arg-type]
        return {
            "badge_id": badge.badge_id,
            "badge_name": badge.badge_name,
            "badge_type": badge.badge_type.value,
            "description": badge.description,
            "rarity": badge.rarity,
            "point_value": badge.point_value,
            "category": badge.category,
            "is_active": badge.is_active,
            "created_at": badge.created_at.isoformat(),
            "available_from": badge.available_from.isoformat(),
            "available_until": badge.available_until.isoformat() if badge.available_until else None,
        }
    except Exception as e:
        logger.error("Error creating badge: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/badges/award", response_model=BadgeResponse)
@rate_limit(rate=20, per=60)
async def award_badge(
    request: Request, badge_request: BadgeAwardRequest, session: Session = Depends(get_session)
) -> BadgeResponse:
    """Award a badge to an agent"""
    badge_system = BadgeSystem()
    try:
        success, agent_badge, message = await badge_system.award_badge(
            session=session,
            agent_id=badge_request.agent_id,
            badge_id=badge_request.badge_id,
            awarded_by=badge_request.awarded_by,
            award_reason=badge_request.award_reason,
            context=badge_request.context,
        )  # type: ignore[arg-type]
        if not success:
            raise HTTPException(status_code=400, detail=message)
        badge = session.execute(select(AchievementBadge).where(AchievementBadge.badge_id == badge_request.badge_id)).first()
        return BadgeResponse(
            badge_id=badge.badge_id,
            badge_name=badge.badge_name,
            badge_type=badge.badge_type.value,
            description=badge.description,
            rarity=badge.rarity,
            point_value=badge.point_value,
            category=badge.category,
            awarded_at=agent_badge.awarded_at.isoformat(),
            is_featured=agent_badge.is_featured,
            badge_icon=badge.badge_icon,
        )  # type: ignore[union-attr]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error awarding badge: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/badges/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_agent_badges(
    request: Request,
    agent_id: str,
    badge_type: str | None = Query(default=None, description="Filter by badge type"),
    category: str | None = Query(default=None, description="Filter by category"),
    featured_only: bool = Query(default=False, description="Only featured badges"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
    session: Session = Depends(get_session),
) -> list[BadgeResponse]:
    """Get badges for an agent"""
    try:
        query = select(AgentBadge).where(AgentBadge.agent_id == agent_id)
        if badge_type:
            query = query.join(AchievementBadge).where(AchievementBadge.badge_type == BadgeType(badge_type))
        if category:
            query = query.join(AchievementBadge).where(AchievementBadge.category == category)
        if featured_only:
            query = query.where(AgentBadge.is_featured)
        agent_badges = session.execute(query.order_by(desc(AgentBadge.awarded_at)).limit(limit)).all()  # type: ignore[arg-type]
        badge_ids = [ab.badge_id for ab in agent_badges]
        badges = session.execute(select(AchievementBadge).where(AchievementBadge.badge_id.in_(badge_ids))).all()  # type: ignore[attr-defined]
        badge_map = {badge.badge_id: badge for badge in badges}
        return [
            BadgeResponse(
                badge_id=ab.badge_id,
                badge_name=badge_map[ab.badge_id].badge_name,
                badge_type=badge_map[ab.badge_id].badge_type.value,
                description=badge_map[ab.badge_id].description,
                rarity=badge_map[ab.badge_id].rarity,
                point_value=badge_map[ab.badge_id].point_value,
                category=badge_map[ab.badge_id].category,
                awarded_at=ab.awarded_at.isoformat(),
                is_featured=ab.is_featured,
                badge_icon=badge_map[ab.badge_id].badge_icon,
            )
            for ab in agent_badges
            if ab.badge_id in badge_map
        ]
    except Exception as e:
        logger.error("Error getting badges for agent %s: %s", agent_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/badges")
@rate_limit(rate=500, per=60)
async def list_available_badges(
    request: Request,
    badge_type: str | None = Query(default=None, description="Filter by badge type"),
    category: str | None = Query(default=None, description="Filter by category"),
    rarity: str | None = Query(default=None, description="Filter by rarity"),
    active_only: bool = Query(default=True, description="Only active badges"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """List available badges"""
    try:
        query = select(AchievementBadge)
        if badge_type:
            query = query.where(AchievementBadge.badge_type == BadgeType(badge_type))
        if category:
            query = query.where(AchievementBadge.category == category)
        if rarity:
            query = query.where(AchievementBadge.rarity == rarity)
        if active_only:
            query = query.where(AchievementBadge.is_active)
        badges = session.execute(query.order_by(desc(AchievementBadge.created_at)).limit(limit)).all()  # type: ignore[arg-type]
        return [
            {
                "badge_id": badge.badge_id,
                "badge_name": badge.badge_name,
                "badge_type": badge.badge_type.value,
                "description": badge.description,
                "rarity": badge.rarity,
                "point_value": badge.point_value,
                "category": badge.category,
                "is_active": badge.is_active,
                "is_limited": badge.is_limited,
                "max_awards": badge.max_awards,
                "current_awards": badge.current_awards,
                "created_at": badge.created_at.isoformat(),
                "available_from": badge.available_from.isoformat(),
                "available_until": badge.available_until.isoformat() if badge.available_until else None,
            }
            for badge in badges
        ]
    except Exception as e:
        logger.error("Error listing available badges: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/badges/{agent_id}/check-automatic")
@rate_limit(rate=20, per=60)
async def check_automatic_badges(request: Request, agent_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Check and award automatic badges for an agent"""
    badge_system = BadgeSystem()
    try:
        awarded_badges = await badge_system.check_and_award_automatic_badges(session, agent_id)  # type: ignore[arg-type]
        return {
            "agent_id": agent_id,
            "badges_awarded": awarded_badges,
            "total_awarded": len(awarded_badges),
            "checked_at": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        logger.error("Error checking automatic badges for agent %s: %s", agent_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/summary/{agent_id}", response_model=AgentCertificationSummary)
@rate_limit(rate=200, per=60)
async def get_agent_summary(
    request: Request, agent_id: str, session: Session = Depends(get_session)
) -> AgentCertificationSummary:
    """Get comprehensive certification and partnership summary for an agent"""
    certification_service = CertificationAndPartnershipService(session)  # type: ignore[arg-type]
    try:
        summary = await certification_service.get_agent_certification_summary(agent_id)
        return AgentCertificationSummary(**summary)
    except Exception as e:
        logger.error("Error getting certification summary for agent %s: %s", agent_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/verification/{agent_id}")
@rate_limit(rate=200, per=60)
async def get_verification_records(
    request: Request,
    agent_id: str,
    verification_type: str | None = Query(default=None, description="Filter by verification type"),
    status: str | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of results"),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Get verification records for an agent"""
    try:
        query = select(VerificationRecord).where(VerificationRecord.agent_id == agent_id)
        if verification_type:
            query = query.where(VerificationRecord.verification_type == VerificationType(verification_type))
        if status:
            query = query.where(VerificationRecord.status == status)
        verifications = session.execute(query.order_by(VerificationRecord.requested_at.desc()).limit(limit)).all()  # type: ignore[attr-defined]
        return [
            {
                "verification_id": verification.verification_id,
                "verification_type": verification.verification_type.value,
                "verification_method": verification.verification_method,
                "status": verification.status,
                "requested_by": verification.requested_by,
                "requested_at": verification.requested_at.isoformat(),
                "started_at": verification.started_at.isoformat() if verification.started_at else None,
                "completed_at": verification.completed_at.isoformat() if verification.completed_at else None,
                "result_score": verification.result_score,
                "failure_reasons": verification.failure_reasons,
                "processing_time": verification.processing_time,
            }
            for verification in verifications
        ]
    except Exception as e:
        logger.error("Error getting verification records for agent %s: %s", agent_id, str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/levels")
@rate_limit(rate=500, per=60)
async def get_certification_levels(request: Request, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Get available certification levels and requirements"""
    try:
        certification_system = CertificationSystem()
        levels = []
        for level, config in certification_system.certification_levels.items():
            levels.append(
                {
                    "level": level.value,
                    "requirements": config["requirements"],
                    "privileges": config["privileges"],
                    "validity_days": config["validity_days"],
                    "renewal_requirements": config["renewal_requirements"],
                }
            )
        return sorted(levels, key=lambda x: ["basic", "intermediate", "advanced", "enterprise", "premium"].index(x["level"]))
    except Exception as e:
        logger.error("Error getting certification levels: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/requirements")
@rate_limit(rate=500, per=60)
async def get_certification_requirements(
    request: Request,
    level: str | None = Query(default=None, description="Filter by certification level"),
    verification_type: str | None = Query(default=None, description="Filter by verification type"),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Get certification requirements"""
    try:
        query = select(CertificationRequirement)
        if level:
            query = query.where(CertificationRequirement.certification_level == CertificationLevel(level))
        if verification_type:
            query = query.where(CertificationRequirement.verification_type == VerificationType(verification_type))  # type: ignore[attr-defined]
        requirements = session.execute(
            query.order_by(CertificationRequirement.certification_level, CertificationRequirement.requirement_name)
        ).all()
        return [
            {
                "id": requirement.id,
                "certification_level": requirement.certification_level.value,
                "verification_type": requirement.verification_type.value,
                "requirement_name": requirement.requirement_name,
                "description": requirement.description,
                "criteria": requirement.criteria,
                "minimum_threshold": requirement.minimum_threshold,
                "maximum_threshold": requirement.maximum_threshold,
                "required_values": requirement.required_values,
                "verification_method": requirement.verification_method,
                "is_mandatory": requirement.is_mandatory,
                "weight": requirement.weight,
                "is_active": requirement.is_active,
            }
            for requirement in requirements
        ]
    except Exception as e:
        logger.error("Error getting certification requirements: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/leaderboard")
@rate_limit(rate=200, per=60)
async def get_certification_leaderboard(
    request: Request,
    category: str = Query(default="highest_level", description="Leaderboard category"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Get certification leaderboard"""
    try:
        if category == "highest_level":
            query = select(AgentCertification).where(AgentCertification.status == CertificationStatus.ACTIVE)
        elif category == "most_certifications":
            query = select(AgentCertification).where(AgentCertification.status == CertificationStatus.ACTIVE)
        else:
            query = select(AgentCertification).where(AgentCertification.status == CertificationStatus.ACTIVE)
        certifications = session.execute(query.order_by(desc(AgentCertification.issued_at)).limit(limit * 2)).all()  # type: ignore[arg-type]
        agent_scores = {}
        for cert in certifications:
            if cert.agent_id not in agent_scores:
                agent_scores[cert.agent_id] = {
                    "agent_id": cert.agent_id,
                    "highest_level": cert.certification_level.value,
                    "certification_count": 0,
                    "total_privileges": 0,
                    "latest_certification": cert.issued_at,
                }
            agent_scores[cert.agent_id]["certification_count"] += 1
            agent_scores[cert.agent_id]["total_privileges"] += len(cert.granted_privileges)
            level_order = ["basic", "intermediate", "advanced", "enterprise", "premium"]
            current_level_index = level_order.index(agent_scores[cert.agent_id]["highest_level"])
            new_level_index = level_order.index(cert.certification_level.value)
            if new_level_index > current_level_index:
                agent_scores[cert.agent_id]["highest_level"] = cert.certification_level.value
            if cert.issued_at > agent_scores[cert.agent_id]["latest_certification"]:
                agent_scores[cert.agent_id]["latest_certification"] = cert.issued_at
        if category == "highest_level":
            sorted_agents = sorted(
                agent_scores.values(),
                key=lambda x: ["basic", "intermediate", "advanced", "enterprise", "premium"].index(x["highest_level"]),
                reverse=True,
            )
        elif category == "most_certifications":
            sorted_agents = sorted(agent_scores.values(), key=lambda x: x["certification_count"], reverse=True)
        else:
            sorted_agents = sorted(agent_scores.values(), key=lambda x: x["total_privileges"], reverse=True)
        return [
            {
                "rank": rank + 1,
                "agent_id": agent["agent_id"],
                "highest_level": agent["highest_level"],
                "certification_count": agent["certification_count"],
                "total_privileges": agent["total_privileges"],
                "latest_certification": agent["latest_certification"].isoformat(),
            }
            for rank, agent in enumerate(sorted_agents[:limit])
        ]
    except Exception as e:
        logger.error("Error getting certification leaderboard: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
