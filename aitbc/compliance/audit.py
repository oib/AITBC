"""Consent, retention, and audit-log helpers for AITBC compliance (v0.11.0 §A4).

These primitives support policy-aware middleware in ``apps/coordinator-api``
and are designed to work with the ``CompliancePolicy`` templates defined in
``aitbc.compliance.policies``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
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
            now = datetime.now(UTC)
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
        now = datetime.now(UTC)
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
        now = datetime.now(UTC)
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


@dataclass
class AuditLog:
    """Append-only, tamper-evident audit log.

    Each appended ``AuditEvent`` is chained to the hash of the previous event,
    forming a simple linked integrity chain. ``verify()`` re-computes the chain
    and returns True only if no event has been modified or reordered.
    """

    log_id: str
    events: list[AuditEvent] = field(default_factory=list)
    chain_hashes: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.events) != len(self.chain_hashes):
            raise ValueError("events and chain_hashes must have the same length")

    def _hash_event(self, event: AuditEvent, previous_hash: str) -> str:
        payload = {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "actor": event.actor,
            "resource": event.resource,
            "action": event.action,
            "classification": str(event.classification),
            "outcome": str(event.outcome),
            "policy_id": event.policy_id,
            "details": event.details,
            "previous_hash": previous_hash,
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def append(self, event: AuditEvent) -> str:
        """Append an event and return its chain hash."""
        previous_hash = self.chain_hashes[-1] if self.chain_hashes else "0" * 64
        chain_hash = self._hash_event(event, previous_hash)
        self.events.append(event)
        self.chain_hashes.append(chain_hash)
        return chain_hash

    def verify(self) -> bool:
        """Return True if the chain is intact."""
        previous_hash = "0" * 64
        for event, stored_hash in zip(self.events, self.chain_hashes, strict=True):
            expected = self._hash_event(event, previous_hash)
            if expected != stored_hash:
                return False
            previous_hash = stored_hash
        return True

    def last_hash(self) -> str:
        """Return the latest chain hash, or the genesis hash if empty."""
        return self.chain_hashes[-1] if self.chain_hashes else "0" * 64


def verify_audit_log(log: AuditLog) -> bool:
    """Top-level helper to verify an audit log's integrity."""
    return log.verify()
