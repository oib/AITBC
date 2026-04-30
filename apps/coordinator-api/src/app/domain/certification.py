"""
Agent Certification and Partnership Domain Models
Implements SQLModel definitions for certification, verification, and partnership programs
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, SQLModel


class CertificationLevel(StrEnum):
    """Certification level enumeration"""

    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    ENTERPRISE = "enterprise"
    PREMIUM = "premium"


class CertificationStatus(StrEnum):
    """Certification status enumeration"""

    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPENDED = "suspended"


class VerificationType(StrEnum):
    """Verification type enumeration"""

    IDENTITY = "identity"
    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    CAPABILITY = "capability"


class PartnershipType(StrEnum):
    """Partnership type enumeration"""

    TECHNOLOGY = "technology"
    SERVICE = "service"
    RESELLER = "reseller"
    INTEGRATION = "integration"
    STRATEGIC = "strategic"
    AFFILIATE = "affiliate"


class BadgeType(StrEnum):
    """Badge type enumeration"""

    ACHIEVEMENT = "achievement"
    MILESTONE = "milestone"
    RECOGNITION = "recognition"
    SPECIALIZATION = "specialization"
    EXCELLENCE = "excellence"
    CONTRIBUTION = "contribution"


class AgentCertification(SQLModel, table=True):
    """Agent certification records"""

    __tablename__ = "agent_certifications"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"cert_{uuid4().hex[:8]}", primary_key=True)
    certification_id: str = Field(unique=True, index=True)

    # Certification details
    agent_id: str = Field(index=True)
    certification_level: CertificationLevel
    certification_type: str = Field(default="standard")  # standard, specialized, enterprise

    # Issuance information
    issued_by: str = Field(index=True)  # Who issued the certification
    issued_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    expires_at: datetime | None = None
    verification_hash: str = Field(max_length=64)  # Blockchain verification hash

    # Status and metadata
    status: CertificationStatus = Field(default=CertificationStatus.ACTIVE)
    renewal_count: int = Field(default=0)
    last_renewed_at: datetime | None = None

    # Requirements and verification
    requirements_met: list[str] = Field(default=[], sa_column=Column(JSON))
    verification_results: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    supporting_documents: list[str] = Field(default=[], sa_column=Column(JSON))

    # Benefits and privileges
    granted_privileges: list[str] = Field(default=[], sa_column=Column(JSON))
    access_levels: list[str] = Field(default=[], sa_column=Column(JSON))
    special_capabilities: list[str] = Field(default=[], sa_column=Column(JSON))

    # Audit trail
    audit_log: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    last_verified_at: datetime | None = None

    # Additional data
    cert_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    notes: str = Field(default="", max_length=1000)


class CertificationRequirement(SQLModel, table=True):
    """Certification requirements and criteria"""

    __tablename__ = "certification_requirements"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:8]}", primary_key=True)

    # Requirement details
    certification_level: CertificationLevel
    requirement_type: VerificationType
    requirement_name: str = Field(max_length=100)
    description: str = Field(default="", max_length=500)

    # Criteria and thresholds
    criteria: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    minimum_threshold: float | None = None
    maximum_threshold: float | None = None
    required_values: list[str] = Field(default=[], sa_column=Column(JSON))

    # Verification method
    verification_method: str = Field(default="automated")  # automated, manual, hybrid
    verification_frequency: str = Field(default="once")  # once, monthly, quarterly, annually

    # Dependencies and prerequisites
    prerequisites: list[str] = Field(default=[], sa_column=Column(JSON))
    depends_on: list[str] = Field(default=[], sa_column=Column(JSON))

    # Status and configuration
    is_active: bool = Field(default=True)
    is_mandatory: bool = Field(default=True)
    weight: float = Field(default=1.0)  # Importance weight

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    effective_date: datetime = Field(default_factory=datetime.now(datetime.UTC))
    expiry_date: datetime | None = None

    # Additional data
    cert_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class VerificationRecord(SQLModel, table=True):
    """Agent verification records and results"""

    __tablename__ = "verification_records"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"verify_{uuid4().hex[:8]}", primary_key=True)
    verification_id: str = Field(unique=True, index=True)

    # Verification details
    agent_id: str = Field(index=True)
    verification_type: VerificationType
    verification_method: str = Field(default="automated")

    # Request information
    requested_by: str = Field(index=True)
    requested_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    priority: str = Field(default="normal")  # low, normal, high, urgent

    # Verification process
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processing_time: float | None = None  # seconds

    # Results and outcomes
    status: str = Field(default="pending")  # pending, in_progress, passed, failed, cancelled
    result_score: float | None = None
    result_details: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    failure_reasons: list[str] = Field(default=[], sa_column=Column(JSON))

    # Verification data
    input_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    output_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    evidence: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))

    # Review and approval
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None

    # Audit and compliance
    compliance_score: float | None = None
    risk_assessment: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    audit_trail: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))

    # Additional data
    cert_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    notes: str = Field(default="", max_length=1000)


class PartnershipProgram(SQLModel, table=True):
    """Partnership programs and alliances"""

    __tablename__ = "partnership_programs"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"partner_{uuid4().hex[:8]}", primary_key=True)
    program_id: str = Field(unique=True, index=True)

    # Program details
    program_name: str = Field(max_length=200)
    program_type: PartnershipType
    description: str = Field(default="", max_length=1000)

    # Program configuration
    tier_levels: list[str] = Field(default=[], sa_column=Column(JSON))
    benefits_by_tier: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    requirements_by_tier: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    # Eligibility criteria
    eligibility_requirements: list[str] = Field(default=[], sa_column=Column(JSON))
    minimum_criteria: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    exclusion_criteria: list[str] = Field(default=[], sa_column=Column(JSON))

    # Program benefits
    financial_benefits: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    non_financial_benefits: list[str] = Field(default=[], sa_column=Column(JSON))
    exclusive_access: list[str] = Field(default=[], sa_column=Column(JSON))

    # Partnership terms
    agreement_terms: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    commission_structure: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    performance_metrics: list[str] = Field(default=[], sa_column=Column(JSON))

    # Status and management
    status: str = Field(default="active")  # active, inactive, suspended, terminated
    max_participants: int | None = None
    current_participants: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    launched_at: datetime | None = None
    expires_at: datetime | None = None

    # Additional data
    program_cert_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    contact_info: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class AgentPartnership(SQLModel, table=True):
    """Agent participation in partnership programs"""

    __tablename__ = "agent_partnerships"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"agent_partner_{uuid4().hex[:8]}", primary_key=True)
    partnership_id: str = Field(unique=True, index=True)

    # Partnership details
    agent_id: str = Field(index=True)
    program_id: str = Field(index=True)
    partnership_type: PartnershipType
    current_tier: str = Field(default="basic")

    # Application and approval
    applied_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reasons: list[str] = Field(default=[], sa_column=Column(JSON))

    # Performance and metrics
    performance_score: float = Field(default=0.0)
    performance_metrics: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    contribution_value: float = Field(default=0.0)

    # Benefits and compensation
    earned_benefits: list[str] = Field(default=[], sa_column=Column(JSON))
    total_earnings: float = Field(default=0.0)
    pending_payments: float = Field(default=0.0)

    # Status and lifecycle
    status: str = Field(default="active")  # active, inactive, suspended, terminated
    tier_progress: float = Field(default=0.0, ge=0, le=100.0)
    next_tier_eligible: bool = Field(default=False)

    # Agreement details
    agreement_signed: bool = Field(default=False)
    agreement_signed_at: datetime | None = None
    agreement_expires_at: datetime | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    last_activity: datetime | None = None

    # Additional data
    partnership_cert_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    notes: str = Field(default="", max_length=1000)


class AchievementBadge(SQLModel, table=True):
    """Achievement and recognition badges"""

    __tablename__ = "achievement_badges"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"badge_{uuid4().hex[:8]}", primary_key=True)
    badge_id: str = Field(unique=True, index=True)

    # Badge details
    badge_name: str = Field(max_length=100)
    badge_type: BadgeType
    description: str = Field(default="", max_length=500)
    badge_icon: str = Field(default="", max_length=200)  # Icon identifier or URL

    # Badge criteria
    achievement_criteria: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    required_metrics: list[str] = Field(default=[], sa_column=Column(JSON))
    threshold_values: dict[str, float] = Field(default={}, sa_column=Column(JSON))

    # Badge properties
    rarity: str = Field(default="common")  # common, uncommon, rare, epic, legendary
    point_value: int = Field(default=0)
    category: str = Field(default="general")  # performance, contribution, specialization, excellence

    # Visual design
    color_scheme: dict[str, str] = Field(default={}, sa_column=Column(JSON))
    display_properties: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    # Status and availability
    is_active: bool = Field(default=True)
    is_limited: bool = Field(default=False)
    max_awards: int | None = None
    current_awards: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    available_from: datetime = Field(default_factory=datetime.now(datetime.UTC))
    available_until: datetime | None = None

    # Additional data
    badge_cert_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    requirements_text: str = Field(default="", max_length=1000)


class AgentBadge(SQLModel, table=True):
    """Agent earned badges and achievements"""

    __tablename__ = "agent_badges"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"agent_badge_{uuid4().hex[:8]}", primary_key=True)

    # Badge relationship
    agent_id: str = Field(index=True)
    badge_id: str = Field(index=True)

    # Award details
    awarded_by: str = Field(index=True)  # System or user who awarded the badge
    awarded_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    award_reason: str = Field(default="", max_length=500)

    # Achievement context
    achievement_context: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    metrics_at_award: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    supporting_evidence: list[str] = Field(default=[], sa_column=Column(JSON))

    # Badge status
    is_displayed: bool = Field(default=True)
    is_featured: bool = Field(default=False)
    display_order: int = Field(default=0)

    # Progress tracking (for progressive badges)
    current_progress: float = Field(default=0.0, ge=0, le=100.0)
    next_milestone: str | None = None

    # Expiration and renewal
    expires_at: datetime | None = None
    is_permanent: bool = Field(default=True)
    renewal_criteria: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    # Social features
    share_count: int = Field(default=0)
    view_count: int = Field(default=0)
    congratulation_count: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    last_viewed_at: datetime | None = None

    # Additional data
    badge_cert_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    notes: str = Field(default="", max_length=1000)


class CertificationAudit(SQLModel, table=True):
    """Certification audit and compliance records"""

    __tablename__ = "certification_audits"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"audit_{uuid4().hex[:8]}", primary_key=True)
    audit_id: str = Field(unique=True, index=True)

    # Audit details
    audit_type: str = Field(max_length=50)  # routine, investigation, compliance, security
    audit_scope: str = Field(max_length=100)  # individual, program, system
    target_entity_id: str = Field(index=True)  # agent_id, certification_id, etc.

    # Audit scheduling
    scheduled_by: str = Field(index=True)
    scheduled_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Audit execution
    auditor_id: str = Field(index=True)
    audit_methodology: str = Field(default="", max_length=500)
    checklists: list[str] = Field(default=[], sa_column=Column(JSON))

    # Findings and results
    overall_score: float | None = None
    compliance_score: float | None = None
    risk_score: float | None = None

    findings: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    violations: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    recommendations: list[str] = Field(default=[], sa_column=Column(JSON))

    # Actions and resolutions
    corrective_actions: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    follow_up_required: bool = Field(default=False)
    follow_up_date: datetime | None = None

    # Status and outcome
    status: str = Field(default="scheduled")  # scheduled, in_progress, completed, failed, cancelled
    outcome: str = Field(default="pending")  # pass, fail, conditional, pending_review

    # Reporting and documentation
    report_generated: bool = Field(default=False)
    report_url: str | None = None
    evidence_documents: list[str] = Field(default=[], sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))

    # Additional data
    audit_cert_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    notes: str = Field(default="", max_length=2000)
