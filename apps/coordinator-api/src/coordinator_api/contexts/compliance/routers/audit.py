"""Compliance audit-log export endpoint (#2377).

``GET /v1/compliance/audit-logs`` merges the two compliance-domain audit
tables — ``transaction_audit_record`` (PCI/GLBA) and ``phi_access_log``
(HIPAA) — into one normalized, timestamp-descending list for admin export.
The CLI's ``aitbc compliance export-audit`` calls this path; before this
router existed the call 403'd/404'd against a route that was never mounted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ....auth import AdminDep, require_auth
from ....storage import get_session
from ..finance import TransactionAuditRecord
from ..hipaa import PHIAccessLog

logger = get_logger(__name__)

router = APIRouter(tags=["compliance", "audit"], prefix="/compliance", dependencies=[Depends(require_auth)])


class ComplianceAuditRecord(BaseModel):
    """One normalized audit row, whichever compliance table it came from."""

    record_id: str
    source: str = Field(description='"transaction" or "hipaa"')
    timestamp: datetime | None = None
    subject_id: str = ""
    actor_id: str = ""
    action: str = ""
    resource_id: str = ""
    outcome: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


def _transaction_record(row: TransactionAuditRecord) -> ComplianceAuditRecord:
    return ComplianceAuditRecord(
        record_id=row.id,
        source="transaction",
        timestamp=row.created_at,
        subject_id=row.counterparty_id,
        actor_id=row.actor_id,
        action="transaction",
        resource_id=row.transaction_id,
        outcome=row.status,
        details={
            "amount": str(row.amount),
            "asset": row.asset,
            "classification": row.classification,
            "policy_framework": row.policy_framework,
            "consent_required": row.consent_required,
            "consent_id": row.consent_id,
            "proof_hash": row.proof_hash,
            "finalized_at": row.finalized_at.isoformat() if row.finalized_at else None,
        },
    )


def _hipaa_record(row: PHIAccessLog) -> ComplianceAuditRecord:
    return ComplianceAuditRecord(
        record_id=row.id,
        source="hipaa",
        timestamp=row.created_at,
        subject_id=row.subject_id,
        actor_id=row.actor_id,
        action=row.action,
        resource_id=row.resource_id,
        outcome=row.outcome,
        details={"reason": row.reason, "meta": row.meta},
    )


@router.get("/audit-logs", response_model=list[ComplianceAuditRecord])
def list_audit_logs(
    session: Annotated[Session, Depends(get_session)],
    user: AdminDep,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[ComplianceAuditRecord]:
    """Return merged compliance audit records, newest first (admin only)."""
    try:
        # Pull limit+offset from each table; the merged window is sliced below.
        tx_rows = session.exec(
            select(TransactionAuditRecord)
            .order_by(desc(TransactionAuditRecord.created_at))  # type: ignore[arg-type]
            .limit(limit + offset)
        ).all()
        phi_rows = session.exec(
            select(PHIAccessLog)
            .order_by(desc(PHIAccessLog.created_at))  # type: ignore[arg-type]
            .limit(limit + offset)
        ).all()
    except Exception as exc:
        logger.error("Failed to query compliance audit logs: %s", exc)
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from exc

    records = [_transaction_record(r) for r in tx_rows] + [_hipaa_record(r) for r in phi_rows]
    # SQLite can hand back naive datetimes while others are aware — sort on the
    # ISO string, which orders identically and never raises on mixed tzinfo.
    records.sort(key=lambda r: r.timestamp.isoformat() if r.timestamp else "", reverse=True)
    return records[offset : offset + limit]
