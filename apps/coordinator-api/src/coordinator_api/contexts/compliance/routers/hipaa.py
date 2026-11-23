"""HIPAA compliance REST endpoints for v0.15.1 B2."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

from ....auth import AuthDep, require_auth
from ....storage import get_session
from ..hipaa import ConsentRecord, HIPAAComplianceService, PHIAccessLog
from aitbc.rate_limiting import rate_limit

router = APIRouter(tags=["compliance", "hipaa"], prefix="/hipaa", dependencies=[Depends(require_auth)])


def _get_service(session: Annotated[Session, Depends(get_session)]) -> HIPAAComplianceService:
    """Return a HIPAA service bound to the request session."""
    return HIPAAComplianceService(session)


def _require_subject_or_admin(user: dict[str, Any], *ids: str) -> None:
    """#2703: consent/PHI mutations bind subject and actor to the caller —
    any authenticated user must not grant, revoke, access or erase another
    subject's record. Admins keep cross-subject access for operators."""
    if user.get("role") == "admin" or all(user.get("sub") == i for i in ids):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="subject/actor does not match the caller")


class ConsentGrant(BaseModel):
    """Request body for granting consent."""

    subject_id: str
    purpose: str
    # #2703: unbounded ints overflow timedelta() into a 500.
    expires_in_days: int = Field(default=365, ge=1, le=3650)
    meta: dict[str, Any] = {}


class RightToDelete(BaseModel):
    """Request body for a right-to-delete request."""

    actor_id: str


@router.post("/consent", response_model=ConsentRecord, status_code=status.HTTP_201_CREATED)
@rate_limit(rate=20, per=60)
def grant_consent(
    payload: ConsentGrant,
    service: Annotated[HIPAAComplianceService, Depends(_get_service)],
    user: AuthDep,
    *,
    request: Request,
) -> ConsentRecord:
    """Record patient consent for a specific purpose."""
    _require_subject_or_admin(user, payload.subject_id)
    return service.grant_consent(
        subject_id=payload.subject_id,
        purpose=payload.purpose,
        expires_in_days=payload.expires_in_days,
        meta=payload.meta,
    )


@router.post("/consent/{consent_id}/revoke", response_model=ConsentRecord)
@rate_limit(rate=20, per=60)
def revoke_consent(
    consent_id: str,
    service: Annotated[HIPAAComplianceService, Depends(_get_service)],
    user: AuthDep,
    *,
    request: Request,
) -> ConsentRecord:
    """Revoke an existing consent record."""
    record = service.session.get(ConsentRecord, consent_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="consent record not found")
    _require_subject_or_admin(user, record.subject_id)
    try:
        return service.revoke_consent(consent_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/phi/access", response_model=PHIAccessLog, status_code=status.HTTP_201_CREATED)
@rate_limit(rate=20, per=60)
def access_phi(
    subject_id: str,
    actor_id: str,
    resource_id: str,
    purpose: str,
    service: Annotated[HIPAAComplianceService, Depends(_get_service)],
    user: AuthDep,
    *,
    request: Request,
) -> PHIAccessLog:
    """Request access to PHI; denied if consent is missing or revoked."""
    from aitbc.compliance.errors import PolicyViolationError

    _require_subject_or_admin(user, subject_id, actor_id)
    try:
        return service.access_phi(subject_id, actor_id, resource_id, purpose)
    except PolicyViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/phi/delete", response_model=list[PHIAccessLog], status_code=status.HTTP_201_CREATED)
@rate_limit(rate=20, per=60)
def right_to_delete(
    payload: RightToDelete,
    subject_id: str,
    service: Annotated[HIPAAComplianceService, Depends(_get_service)],
    user: AuthDep,
    *,
    request: Request,
) -> list[PHIAccessLog]:
    """Process a patient right-to-delete request."""
    _require_subject_or_admin(user, subject_id, payload.actor_id)
    return service.right_to_delete(subject_id, payload.actor_id)
