"""Compliance policy helpers."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ComplianceFramework(str, Enum):
    SOC2 = "soc2"
    GDPR = "gdpr"
    HIPAA = "hipaa"
    ISO27001 = "iso27001"


def load_policy_template(framework: str) -> dict[str, Any]:
    """Return a stub policy template for the requested framework."""
    return {"framework": framework, "controls": []}


def normalize_classification(classification: str) -> str:
    """Normalize a data classification string."""
    try:
        return DataClassification(classification.lower()).value
    except ValueError:
        return DataClassification.INTERNAL.value


__all__ = [
    "ComplianceFramework",
    "DataClassification",
    "load_policy_template",
    "normalize_classification",
]
