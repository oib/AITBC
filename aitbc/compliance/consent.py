"""Consent tracking and revocation abstractions for compliance middleware (v0.15.2 §A1).

The default ``ConsentTracker`` stores records in memory. A persistent store can be
injected via ``ConsentStore`` to integrate with the coordinator-api
``consent_record`` table or any other backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

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


@runtime_checkable
class ConsentStore(Protocol):
    """Backend storage protocol for ``ConsentRecord`` instances."""

    def get(self, subject_id: str, purpose: str) -> ConsentRecord | None:
        """Return the active consent record or None."""

    def put(self, record: ConsentRecord) -> None:
        """Persist a consent record."""


class _InMemoryConsentStore:
    """Default in-memory store used when no external store is injected."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], ConsentRecord] = {}

    def get(self, subject_id: str, purpose: str) -> ConsentRecord | None:
        return self._records.get((subject_id, purpose))

    def put(self, record: ConsentRecord) -> None:
        self._records[(record.subject_id, record.purpose)] = record


class ConsentTracker:
    """Consent tracker that delegates storage to a ``ConsentStore``."""

    def __init__(self, store: ConsentStore | None = None) -> None:
        self._store: ConsentStore = store or _InMemoryConsentStore()

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
        self._store.put(record)
        return record

    def revoke(self, subject_id: str, purpose: str) -> None:
        """Revoke consent for a subject and purpose."""
        record = self._store.get(subject_id, purpose)
        if record is not None:
            record.granted = False
            record.revoked_at = datetime.now(UTC)
            self._store.put(record)

    def require_consent(
        self,
        subject_id: str,
        purpose: str,
        classification: DataClassification | str | None = None,
    ) -> ConsentRecord:
        """Return the active consent record or raise ``PolicyViolationError``."""
        record = self._store.get(subject_id, purpose)
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
