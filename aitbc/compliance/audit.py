"""Consent, retention, and audit-log helpers for AITBC compliance (v0.11.0 §A4).

These primitives support policy-aware middleware in ``apps/coordinator-api``
and are designed to work with the ``CompliancePolicy`` templates defined in
``aitbc.compliance.policies``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from .errors import PolicyViolationError
from .policies import DataClassification, normalize_classification


class RetentionAction(StrEnum):
    """Action to take when a retention period expires."""

    DELETE = "delete"
    ARCHIVE = "archive"
    REVIEW = "review"


class AuditOutcome(StrEnum):
    """Outcome of an audited action."""

    ALLOWED = "allowed"
    DENIED = "denied"
    FLAGGED = "flagged"


@dataclass
class ConsentRecord:
    """A record of consent for a data processing purpose."""

    subject_id: str
    purpose: str
    granted: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.subject_id or not self.purpose:
            raise ValueError("subject_id and purpose are required")

    def is_active(self, now: datetime | None = None) -> bool:
        """Return True if consent is granted and not expired/revoked."""
        if not self.granted or self.revoked_at is not None:
            return False
        if now is None:
            now = datetime.utcnow()
        if self.expires_at is not None and self.expires_at <= now:
            return False
        return True


@dataclass
class RetentionPolicy:
    """Retention rules for a data classification."""

    classification: DataClassification | str
    duration_days: int
    action: RetentionAction | str = RetentionAction.DELETE
    on_expire: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.classification = normalize_classification(self.classification)
        if isinstance(self.action, str):
            self.action = RetentionAction(self.action)
        if self.duration_days < 0:
            raise ValueError("duration_days cannot be negative")


@dataclass
class AuditEvent:
    """A single compliance-audit event."""

    event_id: str
    timestamp: datetime
    actor: str
    resource: str
    action: str
    classification: DataClassification | str
    outcome: AuditOutcome | str
    policy_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.classification = normalize_classification(self.classification)
        if isinstance(self.outcome, str):
            self.outcome = AuditOutcome(self.outcome)


def is_sensitive_classification(classification: DataClassification | str) -> bool:
    """Return True for classifications that require elevated protections."""
    normalized = normalize_classification(classification)
    from .policies import SENSITIVE_CLASSIFICATIONS

    return normalized in SENSITIVE_CLASSIFICATIONS


def retention_expired(
    retention: RetentionPolicy,
    created_at: datetime,
    now: datetime | None = None,
) -> bool:
    """Return True if a record has exceeded its retention period."""
    if now is None:
        now = datetime.utcnow()
    expiry = created_at + timedelta(days=retention.duration_days)
    return now >= expiry


def build_audit_event(
    event_id: str,
    actor: str,
    resource: str,
    action: str,
    classification: DataClassification | str,
    outcome: AuditOutcome | str,
    policy_id: str = "",
    now: datetime | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Factory for creating a timestamped audit event."""
    if now is None:
        now = datetime.utcnow()
    return AuditEvent(
        event_id=event_id,
        timestamp=now,
        actor=actor,
        resource=resource,
        action=action,
        classification=classification,
        outcome=outcome,
        policy_id=policy_id,
        details=details or {},
    )


def require_consent(
    consent: ConsentRecord | None,
    *,
    purpose: str = "",
    now: datetime | None = None,
) -> None:
    """Raise PolicyViolationError if active consent is missing."""
    if consent is None or not consent.is_active(now):
        purpose_label = consent.purpose if consent is not None else purpose
        raise PolicyViolationError(f"Active consent required for purpose: {purpose_label}")
