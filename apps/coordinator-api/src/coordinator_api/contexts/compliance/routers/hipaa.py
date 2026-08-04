"""HIPAA compliance REST endpoints for v0.15.1 B2."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from ....auth import require_auth
from ....storage import get_session
from ..hipaa import ConsentRecord, HIPAAComplianceService, PHIAccessLog

router = APIRouter(tags=["compliance", "hipaa"], prefix="/hipaa", dependencies=[Depends(require_auth)])


def _get_service(session: Annotated[Session, Depends(get_session)]) -> HIPAAComplianceService:
    """Return a HIPAA service bound to the request session."""
    return HIPAAComplianceService(session)


class ConsentGrant(BaseModel):
    """Request body for granting consent."""

    subject_id: str
    purpose: str
    expires_in_days: int = 365
    meta: dict[str, Any] = {}


class RightToDelete(BaseModel):
    """Request body for a right-to-delete request."""

    actor_id: str


@router.post("/consent", response_model=ConsentRecord, status_code=status.HTTP_201_CREATED)
def grant_consent(
    payload: ConsentGrant,
    service: Annotated[HIPAAComplianceService, Depends(_get_service)],
) -> ConsentRecord:
    """Record patient consent for a specific purpose."""
    return service.grant_consent(
        subject_id=payload.subject_id,
        purpose=payload.purpose,
        expires_in_days=payload.expires_in_days,
        meta=payload.meta,
    )


@router.post("/consent/{consent_id}/revoke", response_model=ConsentRecord)
def revoke_consent(
    consent_id: str,
    service: Annotated[HIPAAComplianceService, Depends(_get_service)],
) -> ConsentRecord:
    """Revoke an existing consent record."""
    try:
        return service.revoke_consent(consent_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/phi/access", response_model=PHIAccessLog, status_code=status.HTTP_201_CREATED)
def access_phi(
    subject_id: str,
    actor_id: str,
    resource_id: str,
    purpose: str,
    service: Annotated[HIPAAComplianceService, Depends(_get_service)],
) -> PHIAccessLog:
    """Request access to PHI; denied if consent is missing or revoked."""
    from aitbc.compliance.errors import PolicyViolationError

    try:
        return service.access_phi(subject_id, actor_id, resource_id, purpose)
    except PolicyViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/phi/delete", response_model=list[PHIAccessLog], status_code=status.HTTP_201_CREATED)
def right_to_delete(
    payload: RightToDelete,
    subject_id: str,
    service: Annotated[HIPAAComplianceService, Depends(_get_service)],
) -> list[PHIAccessLog]:
    """Process a patient right-to-delete request."""
    return service.right_to_delete(subject_id, payload.actor_id)
