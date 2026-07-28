"""Unit tests for aitbc.compliance shared abstractions (v0.11.0 §A4).

Covers policy template loading, classification normalization, consent,
retention, and audit event helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aitbc.compliance import (
    AuditEvent,
    AuditOutcome,
    ComplianceFramework,
    ConsentRecord,
    Control,
    DataClassification,
    RetentionPolicy,
    build_audit_event,
    is_sensitive_classification,
    load_policy_template,
    normalize_classification,
    require_consent,
    retention_expired,
)
from aitbc.compliance.errors import InvalidClassificationError, PolicyViolationError


@pytest.mark.parametrize(
    "framework,control_id",
    [
        (ComplianceFramework.HIPAA, "HIPAA-1"),
        (ComplianceFramework.SOC2, "SOC2-1"),
        (ComplianceFramework.GLBA, "GLBA-1"),
        (ComplianceFramework.PCI_DSS, "PCI-1"),
        (ComplianceFramework.MANUFACTURING, "MFG-1"),
        (ComplianceFramework.EDUCATION, "EDU-1"),
        (ComplianceFramework.RETAIL, "RET-1"),
        (ComplianceFramework.GENERIC, "GEN-1"),
    ],
)
def test_load_policy_template(framework: ComplianceFramework, control_id: str) -> None:
    policy = load_policy_template(framework)
    assert policy.framework == framework
    assert policy.require_control(control_id)


def test_template_is_independent_copy() -> None:
    first = load_policy_template("generic")
    second = load_policy_template("generic")
    second.controls.append(Control("GEN-99", "Extra", "extra"))
    assert len(first.controls) != len(second.controls)


def test_normalize_classification() -> None:
    assert normalize_classification("phi") == DataClassification.PHI
    assert normalize_classification(DataClassification.PCI) == DataClassification.PCI


def test_normalize_invalid_classification() -> None:
    with pytest.raises(InvalidClassificationError):
        normalize_classification("top-secret")


def test_is_sensitive_classification() -> None:
    assert is_sensitive_classification("phi") is True
    assert is_sensitive_classification("public") is False


def test_compliance_policy_allows_classification() -> None:
    policy = load_policy_template("hipaa")
    assert policy.allows_classification("phi") is True
    assert policy.allows_classification("public") is False


def test_consent_record_active() -> None:
    consent = ConsentRecord(
        subject_id="user-1",
        purpose="analytics",
    )
    assert consent.is_active() is True


def test_consent_record_expired() -> None:
    now = datetime.now(UTC)
    consent = ConsentRecord(
        subject_id="user-1",
        purpose="analytics",
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    assert consent.is_active(now) is False


def test_consent_record_revoked() -> None:
    consent = ConsentRecord(
        subject_id="user-1",
        purpose="analytics",
        granted=True,
        revoked_at=datetime.now(UTC),
    )
    assert consent.is_active() is False


def test_retention_expired() -> None:
    now = datetime.now(UTC)
    retention = RetentionPolicy(classification="pii", duration_days=30)
    created = now - timedelta(days=31)
    assert retention_expired(retention, created, now) is True


def test_retention_not_expired() -> None:
    now = datetime.now(UTC)
    retention = RetentionPolicy(classification="pii", duration_days=30)
    created = now - timedelta(days=5)
    assert retention_expired(retention, created, now) is False


def test_build_audit_event() -> None:
    event = build_audit_event(
        event_id="ev-1",
        actor="agent-a",
        resource="blob-123",
        action="read",
        classification="phi",
        outcome="allowed",
        policy_id="hipaa-v1",
    )
    assert isinstance(event, AuditEvent)
    assert event.outcome == AuditOutcome.ALLOWED
    assert event.classification == DataClassification.PHI


def test_require_consent_active() -> None:
    consent = ConsentRecord(subject_id="user-1", purpose="process")
    require_consent(consent)


def test_require_consent_missing() -> None:
    with pytest.raises(PolicyViolationError):
        require_consent(None, purpose="process")
