"""Consent tracking and revocation abstractions for compliance middleware (v0.15.2 §A1).

ponytail: This is an in-memory policy skeleton. Production should persist consent
records and integrate with the coordinator-api ``consent_record`` table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .errors import PolicyViolationError
from .policies import DataClassification, normalize_classification


@dataclass
class ConsentRecord:
    """A consent decision for a subject, purpose, and optional classification."""

    subject_id: str
    purpose: str
    granted: bool = True
    classifications: set[DataClassification] = field(default_factory=set)
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_active(self, now: datetime | None = None) -> bool:
        """Return True if consent is granted and not expired or revoked."""
        if now is None:
            now = datetime.now(UTC)
        if not self.granted or self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= now:
            return False
        return True

    def allows(self, classification: DataClassification | str) -> bool:
        """Return True if the consent covers ``classification``."""
        if not self.classifications:
            return True
        return normalize_classification(classification) in self.classifications


class ConsentTracker:
    """In-memory consent tracker used by middleware before DB integration."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], ConsentRecord] = {}

    def grant(
        self,
        subject_id: str,
        purpose: str,
        classifications: set[DataClassification] | set[str] | None = None,
        expires_in_days: int = 365,
        meta: dict[str, Any] | None = None,
    ) -> ConsentRecord:
        """Record consent for a subject and purpose."""
        normalized: set[DataClassification] = set()
        if classifications:
            for c in classifications:
                normalized.add(normalize_classification(c))
        record = ConsentRecord(
            subject_id=subject_id,
            purpose=purpose,
            granted=True,
            classifications=normalized,
            expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
            meta=meta or {},
        )
        self._records[(subject_id, purpose)] = record
        return record

    def revoke(self, subject_id: str, purpose: str) -> None:
        """Revoke consent for a subject and purpose."""
        key = (subject_id, purpose)
        if key in self._records:
            self._records[key].granted = False
            self._records[key].revoked_at = datetime.now(UTC)

    def require_consent(
        self,
        subject_id: str,
        purpose: str,
        classification: DataClassification | str | None = None,
    ) -> ConsentRecord:
        """Return the active consent record or raise ``PolicyViolationError``."""
        record = self._records.get((subject_id, purpose))
        if record is None or not record.is_active():
            raise PolicyViolationError(f"consent required for {subject_id}/{purpose}")
        if classification is not None and not record.allows(classification):
            raise PolicyViolationError(f"consent for {subject_id}/{purpose} does not cover {classification}")
        return record

    def is_consented(
        self,
        subject_id: str,
        purpose: str,
        classification: DataClassification | str | None = None,
    ) -> bool:
        """Return True if active consent exists for the subject/purpose/classification."""
        try:
            self.require_consent(subject_id, purpose, classification)
        except PolicyViolationError:
            return False
        return True
