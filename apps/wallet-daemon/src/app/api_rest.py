from __future__ import annotations

import base64

import logging
import base64

from fastapi import APIRouter, Depends, HTTPException, status, Request

from .deps import get_receipt_service, get_keystore, get_ledger
from .models import (
    ReceiptVerificationListResponse,
    ReceiptVerificationModel,
    ReceiptVerifyResponse,
    SignatureValidationModel,
    WalletCreateRequest,
    WalletCreateResponse,
    WalletListResponse,
    WalletUnlockRequest,
    WalletUnlockResponse,
    WalletSignRequest,
    WalletSignResponse,
    WalletDescriptor,
    from_validation_result,
)
from .keystore.service import KeystoreService
from .ledger_mock import SQLiteLedgerAdapter
from .receipts.service import ReceiptValidationResult, ReceiptVerifierService
from .security import RateLimiter, wipe_buffer

logger = logging.getLogger(__name__)
_rate_limiter = RateLimiter(max_requests=30, window_seconds=60)


def _rate_key(action: str, request: Request, wallet_id: Optional[str] = None) -> str:
    host = request.client.host if request.client else "unknown"
    parts = [action, host]
    if wallet_id:
        parts.append(wallet_id)
    return ":".join(parts)


def _enforce_limit(action: str, request: Request, wallet_id: Optional[str] = None) -> None:
    key = _rate_key(action, request, wallet_id)
    if not _rate_limiter.allow(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded")


router = APIRouter(prefix="/v1", tags=["wallets", "receipts"])


def _result_to_response(result: ReceiptValidationResult) -> ReceiptVerifyResponse:
    payload = from_validation_result(result)
    return ReceiptVerifyResponse(result=payload)


@router.get(
    "/receipts/{job_id}",
    response_model=ReceiptVerifyResponse,
    summary="Verify latest receipt for a job",
)
def verify_latest_receipt(
    job_id: str,
    service: ReceiptVerifierService = Depends(get_receipt_service),
) -> ReceiptVerifyResponse:
    result = service.verify_latest(job_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="receipt not found")
    return _result_to_response(result)


@router.get(
    "/receipts/{job_id}/history",
    response_model=ReceiptVerificationListResponse,
    summary="Verify all historical receipts for a job",
)
def verify_receipt_history(
    job_id: str,
    service: ReceiptVerifierService = Depends(get_receipt_service),
) -> ReceiptVerificationListResponse:
    results = service.verify_history(job_id)
    items = [from_validation_result(result) for result in results]
    return ReceiptVerificationListResponse(items=items)


@router.get("/wallets", response_model=WalletListResponse, summary="List wallets")
def list_wallets(
    keystore: KeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> WalletListResponse:
    descriptors = []
    for record in keystore.list_records():
        ledger_record = ledger.get_wallet(record.wallet_id)
        metadata = ledger_record.metadata if ledger_record else record.metadata
        descriptors.append(
            WalletDescriptor(wallet_id=record.wallet_id, public_key=record.public_key, metadata=metadata)
        )

    return WalletListResponse(items=descriptors)

@router.post("/wallets", response_model=WalletCreateResponse, status_code=status.HTTP_201_CREATED, summary="Create wallet")
def create_wallet(
    request: WalletCreateRequest,
    http_request: Request,
    keystore: KeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> WalletCreateResponse:
    _enforce_limit("wallet-create", http_request)

    try:
        secret = base64.b64decode(request.secret_key) if request.secret_key else None
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid base64 secret") from exc

    try:
        record = keystore.create_wallet(
            wallet_id=request.wallet_id,
            password=request.password,
            secret=secret,
            metadata=request.metadata,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"reason": "password_too_weak", "min_length": 10, "message": str(exc)},
        ) from exc

    ledger.upsert_wallet(record.wallet_id, record.public_key, record.metadata)
    ledger.record_event(record.wallet_id, "created", {"metadata": record.metadata})
    logger.info("Created wallet", extra={"wallet_id": record.wallet_id})
    wallet = WalletDescriptor(wallet_id=record.wallet_id, public_key=record.public_key, metadata=record.metadata)
    return WalletCreateResponse(wallet=wallet)


@router.post("/wallets/{wallet_id}/unlock", response_model=WalletUnlockResponse, summary="Unlock wallet")
def unlock_wallet(
    wallet_id: str,
    request: WalletUnlockRequest,
    http_request: Request,
    keystore: KeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> WalletUnlockResponse:
    _enforce_limit("wallet-unlock", http_request, wallet_id)
    try:
        secret = bytearray(keystore.unlock_wallet(wallet_id, request.password))
        ledger.record_event(wallet_id, "unlocked", {"success": True})
        logger.info("Unlocked wallet", extra={"wallet_id": wallet_id})
    except (KeyError, ValueError):
        ledger.record_event(wallet_id, "unlocked", {"success": False})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    finally:
        if "secret" in locals():
            wipe_buffer(secret)
    # We don't expose the secret in response
    return WalletUnlockResponse(wallet_id=wallet_id, unlocked=True)


@router.post("/wallets/{wallet_id}/sign", response_model=WalletSignResponse, summary="Sign payload")
def sign_payload(
    wallet_id: str,
    request: WalletSignRequest,
    http_request: Request,
    keystore: KeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> WalletSignResponse:
    _enforce_limit("wallet-sign", http_request, wallet_id)
    try:
        message = base64.b64decode(request.message_base64)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid base64 message") from exc

    try:
        signature = keystore.sign_message(wallet_id, request.password, message)
        ledger.record_event(wallet_id, "sign", {"success": True})
        logger.debug("Signed payload", extra={"wallet_id": wallet_id})
    except (KeyError, ValueError):
        ledger.record_event(wallet_id, "sign", {"success": False})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    signature_b64 = base64.b64encode(signature).decode()
    return WalletSignResponse(wallet_id=wallet_id, signature_base64=signature_b64)
