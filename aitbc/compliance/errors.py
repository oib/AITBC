"""Domain exceptions for aitbc.compliance (v0.11.0 §A4)."""

from __future__ import annotations


class ComplianceError(Exception):
    """Base exception for compliance domain errors."""


class InvalidClassificationError(ComplianceError):
    """Data classification is unknown or not allowed by the active policy."""


class PolicyViolationError(ComplianceError):
    """An action violates the active compliance policy."""
