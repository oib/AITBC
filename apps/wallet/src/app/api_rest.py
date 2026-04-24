from __future__ import annotations

import base64
from datetime import datetime

from aitbc.logging import get_logger

from fastapi import APIRouter, Depends, HTTPException, status, Request

from .deps import get_receipt_service, get_keystore, get_ledger
# Temporarily disable multi-chain imports
# from .chain.manager import ChainManager, chain_manager
# from .chain.multichain_ledger import MultiChainLedgerAdapter
# from .chain.chain_aware_wallet_service import ChainAwareWalletService
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
    ChainInfo,
    ChainListResponse,
    ChainCreateRequest,
    ChainCreateResponse,
    WalletMigrationRequest,
    WalletMigrationResponse,
    from_validation_result,
)
from .keystore.persistent_service import PersistentKeystoreService
from .ledger_mock import SQLiteLedgerAdapter
from .receipts.service import ReceiptValidationResult, ReceiptVerifierService
from .chain.manager import ChainManager, chain_manager
from .chain.multichain_ledger import MultiChainLedgerAdapter
from .chain.chain_aware_wallet_service import ChainAwareWalletService
from .security import RateLimiter, wipe_buffer

logger = get_logger(__name__)
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
    keystore: PersistentKeystoreService = Depends(get_keystore),
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
    keystore: PersistentKeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> WalletCreateResponse:
    _enforce_limit("wallet-create", http_request)

    try:
        secret = base64.b64decode(request.secret_key) if request.secret_key else None
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid base64 secret") from exc

    try:
        ip_address = http_request.client.host if http_request.client else "unknown"
        record = keystore.create_wallet(
            wallet_id=request.wallet_id,
            password=request.password,
            secret=secret,
            metadata=request.metadata,
            ip_address=ip_address
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
    keystore: PersistentKeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> WalletUnlockResponse:
    _enforce_limit("wallet-unlock", http_request, wallet_id)
    try:
        ip_address = http_request.client.host if http_request.client else "unknown"
        secret = bytearray(keystore.unlock_wallet(wallet_id, request.password, ip_address))
        ledger.record_event(wallet_id, "unlocked", {"success": True, "ip_address": ip_address})
        logger.info("Unlocked wallet", extra={"wallet_id": wallet_id})
    except (KeyError, ValueError):
        ip_address = http_request.client.host if http_request.client else "unknown"
        ledger.record_event(wallet_id, "unlocked", {"success": False, "ip_address": ip_address})
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
    keystore: PersistentKeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> WalletSignResponse:
    _enforce_limit("wallet-sign", http_request, wallet_id)
    try:
        message = base64.b64decode(request.message_base64)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid base64 message") from exc

    try:
        ip_address = http_request.client.host if http_request.client else "unknown"
        signature = keystore.sign_message(wallet_id, request.password, message, ip_address)
        ledger.record_event(wallet_id, "sign", {"success": True, "ip_address": ip_address})
        logger.debug("Signed payload", extra={"wallet_id": wallet_id})
    except (KeyError, ValueError):
        ip_address = http_request.client.host if http_request.client else "unknown"
        ledger.record_event(wallet_id, "sign", {"success": False, "ip_address": ip_address})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    signature_b64 = base64.b64encode(signature).decode()
    return WalletSignResponse(wallet_id=wallet_id, signature_base64=signature_b64)


# Multi-Chain Endpoints

@router.get("/chains", response_model=ChainListResponse, summary="List all chains")
def list_chains(
    chain_manager: ChainManager = Depends(get_chain_manager),
    multichain_ledger: MultiChainLedgerAdapter = Depends(get_multichain_ledger)
) -> ChainListResponse:
    """List all blockchain chains with their statistics"""
    chains = []
    active_chains = chain_manager.get_active_chains()
    
    for chain in chain_manager.list_chains():
        stats = multichain_ledger.get_chain_stats(chain.chain_id)
        
        chain_info = ChainInfo(
            chain_id=chain.chain_id,
            name=chain.name,
            status=chain.status.value,
            coordinator_url=chain.coordinator_url,
            created_at=chain.created_at.isoformat(),
            updated_at=chain.updated_at.isoformat(),
            wallet_count=stats.get("wallet_count", 0),
            recent_activity=stats.get("recent_activity", 0)
        )
        chains.append(chain_info)
    
    return ChainListResponse(
        chains=chains,
        total_chains=len(chains),
        active_chains=len(active_chains)
    )


@router.post("/chains", response_model=ChainCreateResponse, status_code=status.HTTP_201_CREATED, summary="Create a new chain")
def create_chain(
    request: ChainCreateRequest,
    http_request: Request,
    chain_manager: ChainManager = Depends(get_chain_manager)
) -> ChainCreateResponse:
    """Create a new blockchain chain configuration"""
    _enforce_limit("chain-create", http_request)
    
    from .chain.manager import ChainConfig
    
    chain_config = ChainConfig(
        chain_id=request.chain_id,
        name=request.name,
        coordinator_url=request.coordinator_url,
        coordinator_api_key=request.coordinator_api_key,
        metadata=request.metadata
    )
    
    success = chain_manager.add_chain(chain_config)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chain {request.chain_id} already exists"
        )
    
    chain_info = ChainInfo(
        chain_id=chain_config.chain_id,
        name=chain_config.name,
        status=chain_config.status.value,
        coordinator_url=chain_config.coordinator_url,
        created_at=chain_config.created_at.isoformat(),
        updated_at=chain_config.updated_at.isoformat(),
        wallet_count=0,
        recent_activity=0
    )
    
    return ChainCreateResponse(chain=chain_info)


@router.get("/chains/{chain_id}/wallets", response_model=WalletListResponse, summary="List wallets in a specific chain")
def list_chain_wallets(
    chain_id: str,
    wallet_service: ChainAwareWalletService = Depends(get_chain_aware_wallet_service)
) -> WalletListResponse:
    """List wallets in a specific blockchain chain"""
    wallets = wallet_service.list_wallets(chain_id)
    
    descriptors = []
    for wallet in wallets:
        descriptor = WalletDescriptor(
            wallet_id=wallet.wallet_id,
            chain_id=wallet.chain_id,
            public_key=wallet.public_key,
            address=wallet.address,
            metadata=wallet.metadata
        )
        descriptors.append(descriptor)
    
    return WalletListResponse(items=descriptors)


@router.post("/chains/{chain_id}/wallets", response_model=WalletCreateResponse, status_code=status.HTTP_201_CREATED, summary="Create wallet in a specific chain")
def create_chain_wallet(
    chain_id: str,
    request: WalletCreateRequest,
    http_request: Request,
    wallet_service: ChainAwareWalletService = Depends(get_chain_aware_wallet_service)
) -> WalletCreateResponse:
    """Create a wallet in a specific blockchain chain"""
    # Validate chain_id to prevent path traversal
    import re
    CHAIN_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{3,30}$')
    
    if not CHAIN_ID_PATTERN.match(chain_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chain_id format")
    
    _enforce_limit("wallet-create", http_request)
    
    try:
        secret = base64.b64decode(request.secret_key) if request.secret_key else None
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid base64 secret") from exc
    
    wallet_metadata = wallet_service.create_wallet(
        chain_id=chain_id,
        wallet_id=request.wallet_id,
        password=request.password,
        secret_key=secret,
        metadata=request.metadata
    )
    
    if not wallet_metadata:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create wallet in chain"
        )
    
    wallet = WalletDescriptor(
        wallet_id=wallet_metadata.wallet_id,
        chain_id=wallet_metadata.chain_id,
        public_key=wallet_metadata.public_key,
        address=wallet_metadata.address,
        metadata=wallet_metadata.metadata
    )
    
    return WalletCreateResponse(wallet=wallet)


@router.post("/chains/{chain_id}/wallets/{wallet_id}/unlock", response_model=WalletUnlockResponse, summary="Unlock wallet in a specific chain")
def unlock_chain_wallet(
    chain_id: str,
    wallet_id: str,
    request: WalletUnlockRequest,
    http_request: Request,
    wallet_service: ChainAwareWalletService = Depends(get_chain_aware_wallet_service)
) -> WalletUnlockResponse:
    """Unlock a wallet in a specific blockchain chain"""
    # Validate chain_id to prevent path traversal
    import re
    CHAIN_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{3,30}$')
    
    if not CHAIN_ID_PATTERN.match(chain_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chain_id format")
    
    _enforce_limit("wallet-unlock", http_request, wallet_id)
    
    success = wallet_service.unlock_wallet(chain_id, wallet_id, request.password)
    if not success:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    
    return WalletUnlockResponse(wallet_id=wallet_id, chain_id=chain_id, unlocked=True)


@router.post("/chains/{chain_id}/wallets/{wallet_id}/sign", response_model=WalletSignResponse, summary="Sign payload with wallet in a specific chain")
def sign_chain_payload(
    chain_id: str,
    wallet_id: str,
    request: WalletSignRequest,
    http_request: Request,
    wallet_service: ChainAwareWalletService = Depends(get_chain_aware_wallet_service)
) -> WalletSignResponse:
    """Sign a payload with a wallet in a specific blockchain chain"""
    # Validate chain_id to prevent path traversal
    import re
    CHAIN_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{3,30}$')
    
    if not CHAIN_ID_PATTERN.match(chain_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chain_id format")
    
    _enforce_limit("wallet-sign", http_request, wallet_id)
    
    try:
        message = base64.b64decode(request.message_base64)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid base64 message") from exc
    
    ip_address = http_request.client.host if http_request.client else "unknown"
    signature = wallet_service.sign_message(chain_id, wallet_id, request.password, message, ip_address)
    
    if not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    
    return WalletSignResponse(
        wallet_id=wallet_id,
        chain_id=chain_id,
        signature_base64=base64.b64encode(signature).decode()
    )


@router.post("/wallets/migrate", response_model=WalletMigrationResponse, summary="Migrate wallet between chains")
def migrate_wallet(
    request: WalletMigrationRequest,
    http_request: Request,
    wallet_service: ChainAwareWalletService = Depends(get_chain_aware_wallet_service)
) -> WalletMigrationResponse:
    """Migrate a wallet from one chain to another"""
    # Validate chain_ids to prevent path traversal
    import re
    CHAIN_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{3,30}$')
    
    if not CHAIN_ID_PATTERN.match(request.source_chain_id) or not CHAIN_ID_PATTERN.match(request.target_chain_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chain_id format")
    
    _enforce_limit("wallet-migrate", http_request)
    
    success = wallet_service.migrate_wallet_between_chains(
        source_chain_id=request.source_chain_id,
        target_chain_id=request.target_chain_id,
        wallet_id=request.wallet_id,
        password=request.password,
        new_password=request.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to migrate wallet"
        )
    
    # Get both wallet descriptors
    source_wallet = wallet_service.get_wallet(request.source_chain_id, request.wallet_id)
    target_wallet = wallet_service.get_wallet(request.target_chain_id, request.wallet_id)
    
    if not source_wallet or not target_wallet:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Migration completed but wallet retrieval failed"
        )
    
    source_descriptor = WalletDescriptor(
        wallet_id=source_wallet.wallet_id,
        chain_id=source_wallet.chain_id,
        public_key=source_wallet.public_key,
        address=source_wallet.address,
        metadata=source_wallet.metadata
    )
    
    target_descriptor = WalletDescriptor(
        wallet_id=target_wallet.wallet_id,
        chain_id=target_wallet.chain_id,
        public_key=target_wallet.public_key,
        address=target_wallet.address,
        metadata=target_wallet.metadata
    )
    
    return WalletMigrationResponse(
        success=True,
        source_wallet=source_descriptor,
        target_wallet=target_descriptor,
        migration_timestamp=datetime.now().isoformat()
    )
