"""AITBC industry-specific compliance abstractions (v0.11.0 §A4).

Provides:
- ComplianceFramework and DataClassification enums
- Control and CompliancePolicy dataclasses
- Pre-built policy templates for HIPAA, SOC2, GLBA, PCI-DSS, Manufacturing,
  Education, and Retail
- Consent, retention, and audit-log helpers
"""

from __future__ import annotations

from .audit import (
    AuditEvent,
    AuditLog,
    AuditOutcome,
    ConsentRecord,
    RetentionAction,
    RetentionPolicy,
    build_audit_event,
    is_sensitive_classification,
    require_consent,
    retention_expired,
    verify_audit_log,
)
from .retention import RetentionEngine, RetentionSchedule, apply_retention
from .errors import ComplianceError, InvalidClassificationError, PolicyViolationError
from .policies import (
    ComplianceFramework,
    CompliancePolicy,
    Control,
    DataClassification,
    load_policy_template,
    normalize_classification,
)

__all__ = [
    "AuditEvent",
    "AuditLog",
    "AuditOutcome",
    "ComplianceError",
    "ComplianceFramework",
    "CompliancePolicy",
    "ConsentRecord",
    "Control",
    "DataClassification",
    "InvalidClassificationError",
    "PolicyViolationError",
    "RetentionAction",
    "RetentionEngine",
    "RetentionPolicy",
    "RetentionSchedule",
    "apply_retention",
    "build_audit_event",
    "is_sensitive_classification",
    "load_policy_template",
    "normalize_classification",
    "require_consent",
    "retention_expired",
    "verify_audit_log",
]
