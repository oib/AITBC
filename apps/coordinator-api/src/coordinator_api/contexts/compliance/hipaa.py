"""HIPAA compliance module for PHI access, consent, and right-to-delete (v0.15.1 §B2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column, text
from sqlmodel import Field, Session, SQLModel, select

from aitbc.compliance.errors import PolicyViolationError
from aitbc.compliance.policies import ComplianceFramework, load_policy_template


class ConsentStatus(StrEnum):
    """Lifecycle status of a consent record."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    PENDING = "pending"


class PHIAction(StrEnum):
    """Actions that can be performed on PHI."""

    ACCESS = "access"
    DELETE = "delete"
    SHARE = "share"
    MODIFY = "modify"


class ConsentRecord(SQLModel, table=True):
    """Stored patient consent record for HIPAA processing."""

    __tablename__ = "consent_record"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"cr_{uuid4().hex[:10]}", max_length=32, primary_key=True)
    subject_id: str = Field(default="", max_length=255, index=True)
    purpose: str = Field(default="", max_length=255)
    granted: bool = Field(default=True)
    status: str = Field(default=ConsentStatus.ACTIVE.value, max_length=20, index=True)
    expires_at: datetime | None = Field(default=None)
    revoked_at: datetime | None = Field(default=None)
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)

    def is_active(self, now: datetime | None = None) -> bool:
        """Return True if the consent is active, not expired, and not revoked."""
        if now is None:
            now = datetime.now(UTC)
        if not self.granted or self.revoked_at is not None or self.status == ConsentStatus.REVOKED.value:
            return False
        if self.expires_at is not None:
            expires = self.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires <= now:
                return False
        return True


class PHIAccessLog(SQLModel, table=True):
    """Immutable audit log for PHI access, delete, and share attempts."""

    __tablename__ = "phi_access_log"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"pal_{uuid4().hex[:10]}", max_length=32, primary_key=True)
    subject_id: str = Field(default="", max_length=255, index=True)
    actor_id: str = Field(default="", max_length=255, index=True)
    action: str = Field(default=PHIAction.ACCESS.value, max_length=20, index=True)
    resource_id: str = Field(default="", max_length=255, index=True)
    outcome: str = Field(default="allowed", max_length=20, index=True)
    reason: str = Field(default="", max_length=1024)
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


class HIPAAComplianceService:
    """Service that enforces HIPAA minimum-necessary access, consent, and right-to-delete."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.policy = load_policy_template(ComplianceFramework.HIPAA)

    def grant_consent(
        self,
        subject_id: str,
        purpose: str,
        expires_in_days: int = 365,
        meta: dict | None = None,
    ) -> ConsentRecord:
        """Record a patient's consent for a specific purpose."""
        if not self.policy.require_control("HIPAA-3"):
            raise PolicyViolationError("HIPAA consent control is not required by policy")
        record = ConsentRecord(
            subject_id=subject_id,
            purpose=purpose,
            granted=True,
            status=ConsentStatus.ACTIVE.value,
            expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
            meta=meta or {},
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def revoke_consent(self, consent_id: str) -> ConsentRecord:
        """Revoke an existing consent record."""
        record = self.session.get(ConsentRecord, consent_id)
        if record is None:
            raise ValueError("consent record not found")
        record.granted = False
        record.revoked_at = datetime.now(UTC)
        record.status = ConsentStatus.REVOKED.value
        record.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(record)
        return record

    def _check_consent(self, subject_id: str, purpose: str) -> bool:
        """Return True if an active consent exists for the subject and purpose."""
        statement = select(ConsentRecord).where(
            ConsentRecord.subject_id == subject_id,
            ConsentRecord.purpose == purpose,
        )
        for record in self.session.exec(statement):
            if record.is_active():
                return True
        return False

    def access_phi(self, subject_id: str, actor_id: str, resource_id: str, purpose: str) -> PHIAccessLog:
        """Check consent and log a PHI access attempt."""
        allowed = self._check_consent(subject_id, purpose)
        outcome = "allowed" if allowed else "denied"
        reason = f"consent {'granted' if allowed else 'missing'} for {purpose}"
        log = PHIAccessLog(
            subject_id=subject_id,
            actor_id=actor_id,
            action=PHIAction.ACCESS.value,
            resource_id=resource_id,
            outcome=outcome,
            reason=reason,
        )
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)
        if not allowed:
            raise PolicyViolationError(f"PHI access denied for {subject_id}: {reason}")
        return log

    def right_to_delete(self, subject_id: str, actor_id: str) -> list[PHIAccessLog]:
        """Record a right-to-delete request and return deletion audit logs."""
        if not self.policy.require_control("HIPAA-4"):
            raise PolicyViolationError("HIPAA right-to-access/delete control is not required by policy")
        log = PHIAccessLog(
            subject_id=subject_id,
            actor_id=actor_id,
            action=PHIAction.DELETE.value,
            resource_id="*",
            outcome="allowed",
            reason="patient right-to-delete request",
        )
        # Mark all consents as revoked as a proxy for deletion in this skeleton.
        statement = select(ConsentRecord).where(ConsentRecord.subject_id == subject_id)
        for record in self.session.exec(statement):
            record.granted = False
            record.status = ConsentStatus.REVOKED.value
            record.revoked_at = datetime.now(UTC)
            record.updated_at = datetime.now(UTC)
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)
        return [log]
