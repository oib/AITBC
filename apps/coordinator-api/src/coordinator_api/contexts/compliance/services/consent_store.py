"""SQL-backed ConsentStore for the coordinator compliance middleware."""

from __future__ import annotations

from datetime import UTC, datetime

from aitbc.compliance.consent import ConsentRecord as AITBCConsentRecord
from aitbc.compliance.consent import ConsentStore
from aitbc.compliance.policies import DataClassification, normalize_classification
from sqlmodel import select

from ....storage.db import session_scope
from ..hipaa import ConsentRecord as SQLConsentRecord


def _ensure_aware(value: datetime | None) -> datetime | None:
    """Return an aware datetime, treating naive values as UTC."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class SQLConsentStore(ConsentStore):
    """Persist consent records in the coordinator ``consent_record`` table."""

    def _to_aitbc(self, row: SQLConsentRecord | None) -> AITBCConsentRecord | None:
        """Convert a database row to the shared ``ConsentRecord`` dataclass."""
        if row is None:
            return None
        classifications: set[DataClassification] = set()
        for value in row.meta.get("classifications") or []:
            try:
                classifications.add(normalize_classification(value))
            except Exception:
                continue
        return AITBCConsentRecord(
            subject_id=row.subject_id,
            purpose=row.purpose,
            granted=row.granted and row.status == "active",
            classifications=classifications,
            expires_at=_ensure_aware(row.expires_at),
            revoked_at=_ensure_aware(row.revoked_at),
            meta=dict(row.meta),
            created_at=_ensure_aware(row.created_at) or datetime.now(UTC),
        )

    def _from_aitbc(self, record: AITBCConsentRecord) -> SQLConsentRecord:
        """Convert a shared ``ConsentRecord`` to a database row."""
        status = "active" if record.is_active() and record.granted else "revoked"
        if record.expires_at is not None and record.expires_at <= datetime.now(UTC):
            status = "expired"
        return SQLConsentRecord(
            subject_id=record.subject_id,
            purpose=record.purpose,
            granted=record.granted,
            status=status,
            expires_at=record.expires_at,
            revoked_at=record.revoked_at,
            meta={
                "classifications": sorted(str(c) for c in record.classifications),
                **record.meta,
            },
        )

    def get(self, subject_id: str, purpose: str) -> AITBCConsentRecord | None:
        """Return the active consent record for a subject and purpose."""
        with session_scope() as session:
            statement = select(SQLConsentRecord).where(
                SQLConsentRecord.subject_id == subject_id,
                SQLConsentRecord.purpose == purpose,
            )
            row = session.exec(statement).first()
            return self._to_aitbc(row)

    def put(self, record: AITBCConsentRecord) -> None:
        """Persist or update a consent record."""
        with session_scope() as session:
            statement = select(SQLConsentRecord).where(
                SQLConsentRecord.subject_id == record.subject_id,
                SQLConsentRecord.purpose == record.purpose,
            )
            existing = session.exec(statement).first()
            if existing:
                existing.granted = record.granted
                existing.status = "active" if record.is_active() and record.granted else "revoked"
                existing.expires_at = record.expires_at
                existing.revoked_at = record.revoked_at
                existing.meta = {
                    "classifications": sorted(str(c) for c in record.classifications),
                    **record.meta,
                }
                existing.updated_at = datetime.now(UTC)
                session.add(existing)
            else:
                session.add(self._from_aitbc(record))
            session.commit()
