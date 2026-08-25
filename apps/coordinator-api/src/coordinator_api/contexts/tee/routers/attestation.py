"""TEE remote attestation REST endpoints for Agent B v0.14.1 B1."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from ....auth import AuthDep
from ....storage import get_session
from ..attestation import EnclaveIdentity, EnclaveOwnershipError, EnclaveStatus, TEEAttestation, TEEAttestationService

router = APIRouter(tags=["tee"], prefix="/tee")


def _get_service(session: Annotated[Session, Depends(get_session)]) -> TEEAttestationService:
    """Return a TEE attestation service bound to the request session."""
    return TEEAttestationService(session)


class AttestationSubmit(BaseModel):
    """Request body for submitting a remote attestation quote."""

    enclave_id: str
    quote: str
    measurement: str = ""


class EnclaveRegister(BaseModel):
    """Request body for registering an enclave identity."""

    enclave_id: str
    public_key: str
    # Security fix (2026-08-24): accepted for backward wire compatibility but
    # no longer trusted -- ownership is derived from the authenticated
    # caller (see register_enclave below), not from a client-supplied field.
    agent_id: str = ""
    status: str = "active"
    allowed_measurements: list[str] = []


@router.post("/attestations", response_model=TEEAttestation, status_code=status.HTTP_201_CREATED)
def submit_attestation(
    payload: AttestationSubmit,
    service: Annotated[TEEAttestationService, Depends(_get_service)],
) -> TEEAttestation:
    """Submit and verify a TEE attestation quote.

    By default the endpoint records self-consistent quotes as
    ``self_consistent`` (``registered=False``). Callers that need a real
    trust root must use the job release path, which calls
    ``verify_and_store(..., require_registered=True)``.
    """
    return service.verify_and_store(payload.enclave_id, payload.quote, payload.measurement)


@router.get("/attestations/{attestation_id}", response_model=TEEAttestation)
def get_attestation(
    attestation_id: str,
    service: Annotated[TEEAttestationService, Depends(_get_service)],
) -> TEEAttestation:
    """Retrieve a stored attestation result."""
    attestation = service.get_attestation(attestation_id)
    if attestation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attestation not found")
    return attestation


@router.post("/enclaves", response_model=EnclaveIdentity, status_code=status.HTTP_201_CREATED)
def register_enclave(
    payload: EnclaveRegister,
    service: Annotated[TEEAttestationService, Depends(_get_service)],
    user: AuthDep,
) -> EnclaveIdentity:
    """Register or update an enclave identity.

    Security fix (2026-08-24): the registering identity is the authenticated
    caller (``user["sub"]``), not the client-supplied ``payload.agent_id`` --
    otherwise any caller could claim ownership of any enclave_id just by
    naming themselves in the request body. ``register_enclave`` itself
    refuses to hand an existing registration to a different owner.
    """
    try:
        enclave_status = EnclaveStatus(payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status: {payload.status}") from exc
    try:
        return service.register_enclave(
            payload.enclave_id,
            payload.public_key,
            user["sub"],
            status=enclave_status,
            allowed_measurements=payload.allowed_measurements,
        )
    except EnclaveOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/enclaves/{enclave_id}", response_model=EnclaveIdentity)
def get_enclave(
    enclave_id: str,
    service: Annotated[TEEAttestationService, Depends(_get_service)],
) -> EnclaveIdentity:
    """Retrieve an enclave identity by enclave_id."""
    identity = service.get_enclave(enclave_id)
    if identity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enclave not found")
    return identity
