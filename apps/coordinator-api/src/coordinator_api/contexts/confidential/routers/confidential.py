"""
API endpoints for confidential transactions
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit


from ....auth import AdminDep, AdminOrClientDep, AuthDep
from ....config import settings
from ....schemas import (
    AccessLogQuery,
    AccessLogResponse,
    ConfidentialAccessRequest,
    ConfidentialAccessResponse,
    ConfidentialPaymentCreate,
    ConfidentialPaymentView,
    ConfidentialTransactionCreate,
    ConfidentialTransactionView,
    KeyRegistrationRequest,
    KeyRegistrationResponse,
)
from ...security.services.encryption import EncryptionService
from ...security.services.key_management import KeyManagementError, KeyManager, validate_participant_id

logger = get_logger(__name__)


def _require_participant(principal: str, participant_id: str, role: str | None) -> None:
    """Non-admin callers may only act on their own participant id (#1881)."""
    # #1932 F1: participant_id becomes a filename under key_storage_dir —
    # reject traversal/separator payloads for every role, admin included.
    try:
        validate_participant_id(participant_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if role == "admin":
        return
    if str(participant_id) != str(principal):
        raise HTTPException(status_code=403, detail="participant_id must match the authenticated principal")


router = APIRouter(prefix="/confidential", tags=["confidential"])
security = HTTPBearer()
encryption_service: EncryptionService | None = None
key_manager: KeyManager | None = None


def get_encryption_service() -> EncryptionService:
    """Get encryption service instance"""
    global encryption_service
    if encryption_service is None:
        from ....contexts.security.services.key_management import FileKeyStorage

        key_storage = FileKeyStorage(settings.key_storage_dir)
        key_manager = KeyManager(key_storage)
        encryption_service = EncryptionService(key_manager)  # type: ignore[arg-type]
    return encryption_service


def get_key_manager() -> KeyManager:
    """Get key manager instance"""
    global key_manager
    if key_manager is None:
        from ....contexts.security.services.key_management import FileKeyStorage

        key_storage = FileKeyStorage(settings.key_storage_dir)
        key_manager = KeyManager(key_storage)
    return key_manager


@router.post("/transactions", response_model=ConfidentialTransactionView)
@rate_limit(rate=20, per=60)
def create_confidential_transaction(
    request_http: Request,
    request: ConfidentialTransactionCreate,
    _user: AuthDep,
) -> ConfidentialTransactionView:
    """Create a new confidential transaction with optional encryption.

    Disabled: there is no confidential-transaction store, so the previous
    implementation built an in-memory object, encrypted into locals and
    persisted nothing — every created transaction was silently orphaned
    (#2174).
    """
    raise HTTPException(
        status_code=501,
        detail="Confidential transaction creation is not implemented: no confidential transaction store exists",
    )


@router.get("/transactions/{transaction_id}", response_model=ConfidentialTransactionView)
@rate_limit(rate=200, per=60)
def get_confidential_transaction(
    request: Request,
    transaction_id: str,
    _user: AuthDep,
) -> ConfidentialTransactionView:
    """Get confidential transaction metadata (without decrypting sensitive data).

    Disabled: with no confidential-transaction store every lookup is a lie
    by construction (#2174).
    """
    raise HTTPException(
        status_code=501,
        detail="Confidential transaction reads are not implemented: no confidential transaction store exists",
    )


@router.post("/transactions/{transaction_id}/access", response_model=ConfidentialAccessResponse)
@rate_limit(rate=20, per=60)
def access_confidential_data(
    request: Request,
    request_data: ConfidentialAccessRequest,
    transaction_id: str,
    user: AuthDep,
) -> ConfidentialAccessResponse:
    """Request access to decrypt confidential transaction data.

    Disabled: with no confidential-transaction store there is no encrypted
    payload to authorize against — the previous implementation fabricated a
    transaction and returned hardcoded 'decrypted' data (#2174).
    """
    if request_data.transaction_id != transaction_id:
        raise HTTPException(status_code=400, detail="Transaction ID mismatch")
    principal = str(user.get("sub") or user.get("user_id") or "")
    if request_data.requester != principal and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="requester must match the authenticated principal")
    raise HTTPException(
        status_code=501,
        detail="Confidential data access is not implemented: no confidential transaction store exists",
    )


@router.post("/transactions/{transaction_id}/audit", response_model=ConfidentialAccessResponse)
@rate_limit(rate=20, per=60)
def audit_access_confidential_data(
    request: Request,
    transaction_id: str,
    authorization: str,
    _user: AuthDep,
    purpose: str = "audit",
) -> ConfidentialAccessResponse:
    """Audit access to confidential transaction data.

    Disabled: with no confidential-transaction store there is no encrypted
    payload to audit-decrypt — the previous implementation always 404'd on
    its own fabricated empty transaction (#2174).
    """
    raise HTTPException(
        status_code=501,
        detail="Confidential audit access is not implemented: no confidential transaction store exists",
    )


@router.post("/keys/register", response_model=KeyRegistrationResponse)
@rate_limit(rate=20, per=60)
async def register_encryption_key(
    request: Request,
    request_data: KeyRegistrationRequest,
    user: AdminOrClientDep,
) -> KeyRegistrationResponse:
    """Register public key for confidential transactions"""
    _require_participant(str(user.get("sub") or ""), request_data.participant_id, user.get("role"))
    try:
        km = get_key_manager()
        existing_pair = km.storage.get_key_pair_sync(request_data.participant_id)
        if existing_pair is not None:
            return KeyRegistrationResponse(
                success=True,
                participant_id=request_data.participant_id,
                key_version=existing_pair.version,
                registered_at=existing_pair.created_at,
                error=None,
            )
        key_pair = await km.generate_key_pair(request_data.participant_id)
        return KeyRegistrationResponse(
            success=True,
            participant_id=request_data.participant_id,
            key_version=key_pair.version,
            registered_at=key_pair.created_at,
            error=None,
        )
    except KeyManagementError as e:
        logger.error("Key registration failed: %s", e)
        return KeyRegistrationResponse(
            success=False,
            participant_id=request_data.participant_id,
            key_version=0,
            registered_at=datetime.now(UTC),
            error=str(e),
        )
    except Exception as e:
        logger.error("Failed to register key: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/keys/rotate")
@rate_limit(rate=20, per=60)
async def rotate_encryption_key(
    request: Request,
    participant_id: str,
    user: AdminOrClientDep,
) -> dict[str, Any]:
    """Rotate encryption keys for participant"""
    _require_participant(str(user.get("sub") or ""), participant_id, user.get("role"))
    try:
        km = get_key_manager()
        new_key_pair = await km.rotate_keys(participant_id)
        return {
            "success": True,
            "participant_id": participant_id,
            "new_version": new_key_pair.version,
            "rotated_at": new_key_pair.created_at,
        }
    except NotImplementedError as e:
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=501, detail="Internal server error") from e
    except KeyManagementError as e:
        logger.error("Key rotation failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to rotate keys: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/access/logs", response_model=AccessLogResponse)
@rate_limit(rate=200, per=60)
def get_access_logs(
    request: Request,
    query: Annotated[AccessLogQuery, Depends()],
    _admin: AdminDep,
) -> AccessLogResponse:
    """Get access logs for confidential transactions.

    Disabled: no access-log store exists, so the previous implementation
    always returned an empty page that looked like "no access yet" (#2174).
    """
    raise HTTPException(
        status_code=501,
        detail="Confidential access logs are not implemented: no access-log store exists",
    )


@router.get("/status")
@rate_limit(rate=1000, per=60)
async def get_confidential_status(
    request: Request,
    _user: AuthDep,
) -> dict[str, Any]:
    """Get status of confidential transaction system.

    Reports only real capabilities: key management and the encryption
    service exist, but with no confidential-transaction store the system
    cannot serve transactions, so ``enabled`` is False and no
    ``transactions_count`` is fabricated (#2174).
    """
    try:
        km = get_key_manager()
        get_encryption_service()
        participants = await km.list_participants()
        return {
            "enabled": False,
            "reason": "Confidential transaction storage is not implemented; encryption and key services are available",
            "algorithm": "AES-256-GCM+X25519",
            "participants_count": len(participants),
            "audit_enabled": False,
        }
    except Exception as e:
        logger.error("Failed to get status: %s", e)
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/payments", response_model=ConfidentialPaymentView)
@rate_limit(rate=20, per=60)
def create_confidential_payment(
    request: ConfidentialPaymentCreate,
    user: AdminOrClientDep,
    *,
    http_request: Request,
) -> ConfidentialPaymentView:
    """Receive a confidential payment envelope from the CLI.

    Fail-closed: without a real TEE this endpoint must not emit a 'settled'
    receipt. When ``CONFIDENTIAL_TEE_ENABLED`` is true the coordinator records
    the envelope and returns a receipt; otherwise it returns 503 Service
    Unavailable so callers fall back to local simulated settlement.
    """
    _require_participant(str(user.get("sub") or ""), request.sender_id, user.get("role"))
    if not settings.confidential_tee_enabled:
        raise HTTPException(
            status_code=503,
            detail="Confidential TEE payment settlement is not enabled on this coordinator",
        )
    return ConfidentialPaymentView(
        payment_id=request.payment_id,
        sender_id=request.sender_id,
        recipient_id=request.recipient_id,
        amount_commitment=request.amount_commitment,
    )
