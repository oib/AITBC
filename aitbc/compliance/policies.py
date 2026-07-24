"""Shared compliance policy templates for AITBC (v0.11.0 §A4).

Defines policy primitives and pre-built templates for regulated industries.
Templates can be loaded by ``load_policy_template`` and extended by services
in ``apps/coordinator-api``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .errors import InvalidClassificationError


class ComplianceFramework(StrEnum):
    """Supported compliance frameworks and industry templates."""

    HIPAA = "hipaa"
    SOC2 = "soc2"
    GLBA = "glba"
    PCI_DSS = "pci_dss"
    MANUFACTURING = "manufacturing"
    EDUCATION = "education"
    RETAIL = "retail"
    GENERIC = "generic"


class DataClassification(StrEnum):
    """Data classification labels used across compliance policies."""

    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"
    PII = "pii"
    PHI = "phi"
    PCI = "pci"


SENSITIVE_CLASSIFICATIONS = {
    DataClassification.PII,
    DataClassification.PHI,
    DataClassification.PCI,
    DataClassification.CONFIDENTIAL,
    DataClassification.RESTRICTED,
}


def normalize_classification(
    classification: DataClassification | str,
) -> DataClassification:
    """Validate and normalize a classification label."""
    if isinstance(classification, DataClassification):
        return classification
    try:
        return DataClassification(classification)
    except ValueError as exc:
        raise InvalidClassificationError(f"Unknown data classification: {classification}") from exc


def _classifications(*labels: str) -> set[DataClassification]:
    return {DataClassification(label) for label in labels}


@dataclass
class Control:
    """A single compliance control requirement."""

    control_id: str
    name: str
    category: str
    required: bool = True
    evidence_template: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompliancePolicy:
    """A compliance policy composed of classifications and controls."""

    policy_id: str
    name: str
    framework: ComplianceFramework | str
    version: str
    description: str = ""
    classifications: set[DataClassification] = field(default_factory=set)
    controls: list[Control] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.framework, str):
            self.framework = ComplianceFramework(self.framework)
        self.classifications = {normalize_classification(c) for c in self.classifications}
        if not self.policy_id:
            raise ValueError("policy_id is required")

    def allows_classification(self, classification: DataClassification | str) -> bool:
        """Return True if the policy explicitly covers a classification."""
        if isinstance(classification, str):
            classification = DataClassification(classification)
        return classification in self.classifications

    def require_control(self, control_id: str) -> bool:
        """Return True if a control is required by this policy."""
        return any(c.control_id == control_id and c.required for c in self.controls)


# Pre-built policy templates keyed by framework.
_POLICY_TEMPLATES: dict[ComplianceFramework, CompliancePolicy] = {
    ComplianceFramework.HIPAA: CompliancePolicy(
        policy_id="hipaa-v1",
        name="HIPAA Healthcare Policy",
        framework=ComplianceFramework.HIPAA,
        version="1.0.0",
        description="Protects PHI through access controls, audit logging, consent, and retention rules.",
        classifications=_classifications("phi", "pii", "restricted", "confidential"),
        controls=[
            Control("HIPAA-1", "Minimum Necessary Access", "access", True),
            Control("HIPAA-2", "Audit Logging for PHI", "audit", True),
            Control("HIPAA-3", "Consent and Authorization", "consent", True),
            Control("HIPAA-4", "Right to Access and Delete", "data_subject_rights", True),
            Control("HIPAA-5", "Encryption at Rest and in Transit", "encryption", True),
        ],
    ),
    ComplianceFramework.SOC2: CompliancePolicy(
        policy_id="soc2-v1",
        name="SOC 2 Trust Services Policy",
        framework=ComplianceFramework.SOC2,
        version="1.0.0",
        description="Covers security, availability, processing integrity, confidentiality, and privacy controls.",
        classifications=_classifications("internal", "restricted", "confidential", "pii"),
        controls=[
            Control("SOC2-1", "Access Control and Identity Management", "access", True),
            Control("SOC2-2", "System Monitoring and Alerting", "monitoring", True),
            Control("SOC2-3", "Change Management", "change_management", True),
            Control("SOC2-4", "Incident Response", "incident_response", True),
        ],
    ),
    ComplianceFramework.GLBA: CompliancePolicy(
        policy_id="glba-v1",
        name="GLBA Financial Privacy Policy",
        framework=ComplianceFramework.GLBA,
        version="1.0.0",
        description="Safeguards customer financial information and privacy notices.",
        classifications=_classifications("pii", "confidential", "restricted"),
        controls=[
            Control("GLBA-1", "Customer Information Safeguards", "safeguards", True),
            Control("GLBA-2", "Privacy Notice Delivery", "privacy", True),
            Control("GLBA-3", "Opt-Out Management", "consent", True),
        ],
    ),
    ComplianceFramework.PCI_DSS: CompliancePolicy(
        policy_id="pci-dss-v1",
        name="PCI-DSS Payment Card Policy",
        framework=ComplianceFramework.PCI_DSS,
        version="1.0.0",
        description="Protects cardholder data through encryption, access control, and network segmentation.",
        classifications=_classifications("pci", "confidential", "restricted"),
        controls=[
            Control("PCI-1", "Encrypt Stored Cardholder Data", "encryption", True),
            Control("PCI-2", "Access Control Measures", "access", True),
            Control("PCI-3", "Network Segmentation", "network", True),
            Control("PCI-4", "Vulnerability Management", "vulnerability", True),
        ],
    ),
    ComplianceFramework.MANUFACTURING: CompliancePolicy(
        policy_id="manufacturing-v1",
        name="Manufacturing Industry Policy",
        framework=ComplianceFramework.MANUFACTURING,
        version="1.0.0",
        description="Covers supply-chain integrity and operational technology data protection.",
        classifications=_classifications("internal", "restricted", "confidential"),
        controls=[
            Control("MFG-1", "Supply Chain Integrity", "supply_chain", True),
            Control("MFG-2", "OT Network Segmentation", "network", True),
            Control("MFG-3", "Quality and Traceability Logs", "audit", True),
        ],
    ),
    ComplianceFramework.EDUCATION: CompliancePolicy(
        policy_id="education-v1",
        name="Education Industry Policy",
        framework=ComplianceFramework.EDUCATION,
        version="1.0.0",
        description="Protects student records and education-related personal data.",
        classifications=_classifications("pii", "internal", "restricted"),
        controls=[
            Control("EDU-1", "Student Data Privacy", "privacy", True),
            Control("EDU-2", "Directory Information Controls", "access", True),
            Control("EDU-3", "Parental Consent Management", "consent", True),
        ],
    ),
    ComplianceFramework.RETAIL: CompliancePolicy(
        policy_id="retail-v1",
        name="Retail Industry Policy",
        framework=ComplianceFramework.RETAIL,
        version="1.0.0",
        description="Combines PCI-DSS controls with customer data protection for retail operations.",
        classifications=_classifications("pci", "pii", "confidential", "restricted"),
        controls=[
            Control("RET-1", "Payment Data Protection", "encryption", True),
            Control("RET-2", "Customer Data Retention", "retention", True),
            Control("RET-3", "Loyalty Program Data Minimization", "data_minimization", True),
        ],
    ),
    ComplianceFramework.GENERIC: CompliancePolicy(
        policy_id="generic-v1",
        name="Generic Data Protection Policy",
        framework=ComplianceFramework.GENERIC,
        version="1.0.0",
        description="Baseline data classification and access controls for non-regulated workloads.",
        classifications=_classifications("public", "internal", "restricted"),
        controls=[
            Control("GEN-1", "Data Classification", "classification", True),
            Control("GEN-2", "Least Privilege Access", "access", True),
            Control("GEN-3", "Basic Audit Logging", "audit", False),
        ],
    ),
}


def load_policy_template(framework: ComplianceFramework | str) -> CompliancePolicy:
    """Return a deep copy of a pre-built compliance policy template.

    The returned policy can be customized by callers without mutating the
    shared template.
    """
    if isinstance(framework, str):
        framework = ComplianceFramework(framework)
    base = _POLICY_TEMPLATES[framework]
    return CompliancePolicy(
        policy_id=base.policy_id,
        name=base.name,
        framework=base.framework,
        version=base.version,
        description=base.description,
        classifications=set(base.classifications),
        controls=[
            Control(
                c.control_id,
                c.name,
                c.category,
                c.required,
                c.evidence_template,
                dict(c.meta),
            )
            for c in base.controls
        ],
        meta=dict(base.meta),
    )
