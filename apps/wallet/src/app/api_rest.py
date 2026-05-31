from __future__ import annotations

import asyncio
import base64

from fastapi import APIRouter, Depends, HTTPException, Request, status

from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

from .deps import get_keystore, get_ledger, get_receipt_service
from .keystore.persistent_service import PersistentKeystoreService
from .ledger_mock import SQLiteLedgerAdapter

# Temporarily disable multi-chain imports
# from .chain.manager import ChainManager, chain_manager
# from .chain.multichain_ledger import MultiChainLedgerAdapter
# from .chain.chain_aware_wallet_service import ChainAwareWalletService
from .models import (
    ReceiptVerificationListResponse,
    ReceiptVerifyResponse,
    WalletCreateRequest,
    WalletCreateResponse,
    WalletDescriptor,
    WalletListResponse,
    WalletSignRequest,
    WalletSignResponse,
    WalletTransactionRequest,
    WalletTransactionResponse,
    WalletUnlockRequest,
    WalletUnlockResponse,
    from_validation_result,
)
from .receipts.service import ReceiptValidationResult, ReceiptVerifierService

# Temporarily disable multi-chain imports to match deps.py
# from .chain.manager import ChainManager, chain_manager
# from .chain.multichain_ledger import MultiChainLedgerAdapter
# from .chain.chain_aware_wallet_service import ChainAwareWalletService
from .security import wipe_buffer

logger = get_logger(__name__)


router = APIRouter(tags=["wallets", "receipts"])


def _result_to_response(result: ReceiptValidationResult) -> ReceiptVerifyResponse:
    payload = from_validation_result(result)
    return ReceiptVerifyResponse(result=payload)


@router.get(
    "/receipts/{job_id}",
    response_model=ReceiptVerifyResponse,
    summary="Verify latest receipt for a job",
)
@rate_limit(rate=200, per=60)
def verify_latest_receipt(
    request: Request,
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
@rate_limit(rate=200, per=60)
def verify_receipt_history(
    request: Request,
    job_id: str,
    service: ReceiptVerifierService = Depends(get_receipt_service),
) -> ReceiptVerificationListResponse:
    results = service.verify_history(job_id)
    items = [from_validation_result(result) for result in results]
    return ReceiptVerificationListResponse(items=items)


@router.get("/wallets", response_model=WalletListResponse, summary="List wallets")
@rate_limit(rate=200, per=60)
def list_wallets(
    request: Request,
    keystore: PersistentKeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> WalletListResponse:
    descriptors = []
    for record in keystore.list_records():
        ledger_record = ledger.get_wallet(record.wallet_id)
        meta = ledger_record.metadata if ledger_record else record.metadata
        chain_id = meta.get("chain_id", "ait-mainnet") if isinstance(meta, dict) else "ait-mainnet"
        descriptors.append(
            WalletDescriptor(
                wallet_id=record.wallet_id,
                chain_id=chain_id,
                public_key=record.public_key,
                address=None,
                metadata=meta if isinstance(meta, dict) else {}
            )
        )

    return WalletListResponse(items=descriptors)

@router.post("/wallets", response_model=WalletCreateResponse, status_code=status.HTTP_201_CREATED, summary="Create wallet")
@rate_limit(rate=50, per=60)
async def create_wallet(
    request: Request,
    wallet_request: WalletCreateRequest,
    keystore: PersistentKeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> WalletCreateResponse:

    try:
        secret = base64.b64decode(wallet_request.secret_key) if wallet_request.secret_key else None
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid base64 secret") from exc

    # Include chain_id in metadata
    metadata = wallet_request.metadata.copy()
    metadata["chain_id"] = wallet_request.chain_id

    try:
        ip_address = request.client.host if request.client else "unknown"
        record = await asyncio.to_thread(
            keystore.create_wallet,
            wallet_id=wallet_request.wallet_id,
            password=wallet_request.password,
            secret=secret,
            metadata=metadata,
            ip_address=ip_address
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"reason": "password_too_weak", "min_length": 10, "message": str(exc)},
        ) from exc

    await asyncio.to_thread(ledger.upsert_wallet, record.wallet_id, record.public_key, metadata)
    await asyncio.to_thread(ledger.record_event, record.wallet_id, "created", {"metadata": metadata})
    logger.info("Created wallet", extra={"wallet_id": record.wallet_id, "chain_id": wallet_request.chain_id})
    wallet = WalletDescriptor(
        wallet_id=record.wallet_id,
        chain_id=wallet_request.chain_id,
        public_key=record.public_key,
        address=None,
        metadata=metadata
    )
    return WalletCreateResponse(wallet=wallet)


@router.post("/wallets/{wallet_id}/unlock", response_model=WalletUnlockResponse, summary="Unlock wallet")
@rate_limit(rate=50, per=60)
def unlock_wallet(
    request: Request,
    wallet_id: str,
    unlock_request: WalletUnlockRequest,
    keystore: PersistentKeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> WalletUnlockResponse:
    try:
        ip_address = request.client.host if request.client else "unknown"
        secret = bytearray(keystore.unlock_wallet(wallet_id, unlock_request.password, ip_address))
        ledger.record_event(wallet_id, "unlocked", {"success": True, "ip_address": ip_address})
        logger.info("Unlocked wallet", extra={"wallet_id": wallet_id})
    except (KeyError, ValueError):
        ip_address = request.client.host if request.client else "unknown"
        ledger.record_event(wallet_id, "unlocked", {"success": False, "ip_address": ip_address})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    finally:
        if "secret" in locals():
            wipe_buffer(secret)
    # We don't expose the secret in response
    return WalletUnlockResponse(wallet_id=wallet_id, unlocked=True)


@router.post("/wallets/{wallet_id}/sign", response_model=WalletSignResponse, summary="Sign payload")
@rate_limit(rate=50, per=60)
def sign_payload(
    request: Request,
    wallet_id: str,
    sign_request: WalletSignRequest,
    keystore: PersistentKeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> WalletSignResponse:
    try:
        message = base64.b64decode(sign_request.message_base64)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid base64 message") from exc

    try:
        ip_address = request.client.host if request.client else "unknown"
        signature = keystore.sign_message(wallet_id, sign_request.password, message, ip_address)
        ledger.record_event(wallet_id, "sign", {"success": True, "ip_address": ip_address})
        logger.debug("Signed payload", extra={"wallet_id": wallet_id})
    except (KeyError, ValueError):
        ip_address = request.client.host if request.client else "unknown"
        ledger.record_event(wallet_id, "sign", {"success": False, "ip_address": ip_address})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    signature_b64 = base64.b64encode(signature).decode()
    chain_id = "ait-mainnet"
    if ledger_record := ledger.get_wallet(wallet_id):
        chain_id = ledger_record.metadata.get("chain_id", "ait-mainnet") if isinstance(ledger_record.metadata, dict) else "ait-mainnet"
    return WalletSignResponse(wallet_id=wallet_id, chain_id=chain_id, signature_base64=signature_b64)


@router.post("/wallets/{wallet_id}/send", response_model=WalletTransactionResponse, summary="Send transaction")
@rate_limit(rate=20, per=60)
def send_transaction(
    request: Request,
    wallet_id: str,
    tx_request: WalletTransactionRequest,
    keystore: PersistentKeystoreService = Depends(get_keystore),
    ledger: SQLiteLedgerAdapter = Depends(get_ledger),
) -> WalletTransactionResponse:
    """
    Sign and submit a transaction to the blockchain.
    
    This endpoint creates, signs, and broadcasts a real transaction
    using the wallet's private key.
    """
    try:
        ip_address = request.client.host if request.client else "unknown"

        # Call the keystore to sign and submit
        result = keystore.sign_and_submit_transaction(
            wallet_id=wallet_id,
            password=tx_request.password,
            recipient=tx_request.recipient,
            amount=tx_request.amount,
            fee=tx_request.fee,
            nonce=tx_request.nonce,
            chain_id=tx_request.chain_id,
            payload=tx_request.payload,
            ip_address=ip_address
        )

        if not result.get("success"):
            error_msg = result.get("error", "Transaction failed")
            logger.warning("Transaction submission failed", extra={
                "wallet_id": wallet_id,
                "error": error_msg
            })
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

        logger.info("Transaction submitted successfully", extra={
            "wallet_id": wallet_id,
            "tx_hash": result.get("tx_hash"),
            "recipient": result.get("recipient")
        })

        return WalletTransactionResponse(
            success=True,
            tx_hash=result.get("tx_hash", ""),
            status=result.get("status", "pending"),
            sender=result.get("sender", ""),
            recipient=result.get("recipient", ""),
            amount=result.get("amount", 0),
            fee=result.get("fee", 0),
            nonce=result.get("nonce", 0)
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error in transaction submission", extra={
            "wallet_id": wallet_id,
            "error": str(exc)
        })
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/wallets/{wallet_id}/faucet", response_model=WalletTransactionResponse, summary="Request faucet funds")
@rate_limit(rate=5, per=3600)  # 5 requests per hour
async def faucet_request(
    request: Request,
    wallet_id: str,
    keystore: PersistentKeystoreService = Depends(get_keystore),
) -> WalletTransactionResponse:
    """
    Request test tokens from the blockchain faucet.
    
    This endpoint funds a newly created wallet with test tokens
    for development and testing purposes.
    """
    try:
        ip_address = request.client.host if request.client else "unknown"

        # Get wallet public key
        record = keystore.get_wallet(wallet_id)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

        address = record.public_key

        # Call blockchain faucet
        import httpx

        from .settings import settings

        rpc_url = settings.blockchain_rpc_url
        response = httpx.post(
            f"{rpc_url}/rpc/faucet",
            json={"address": address, "amount": 1000000},
            timeout=30.0
        )
        response.raise_for_status()
        result = response.json()

        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Faucet request failed")
            )

        logger.info("Faucet funding successful", extra={
            "wallet_id": wallet_id,
            "address": address,
            "amount": result.get("amount", 0)
        })

        return WalletTransactionResponse(
            success=True,
            tx_hash=result.get("tx_hash", ""),
            status="confirmed",
            sender="faucet",
            recipient=address,
            amount=result.get("amount", 0),
            fee=0,
            nonce=0
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Faucet request failed", extra={
            "wallet_id": wallet_id,
            "error": str(exc)
        })
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# Multi-Chain Endpoints - Temporarily disabled due to missing chain manager dependencies
# Uncomment these when multi-chain functionality is re-enabled

# @router.get("/chains", response_model=ChainListResponse, summary="List all chains")
# @rate_limit(rate=200, per=60)
# def list_chains(
#     request: Request,
#     chain_manager: ChainManager = Depends(get_chain_manager),
#     multichain_ledger: MultiChainLedgerAdapter = Depends(get_multichain_ledger)
# ) -> ChainListResponse:
#     """List all blockchain chains with their statistics"""
#     chains = []
#     active_chains = chain_manager.get_active_chains()
#
#     for chain in chain_manager.list_chains():
#         stats = multichain_ledger.get_chain_stats(chain.chain_id)
#
#         chain_info = ChainInfo(
#             chain_id=chain.chain_id,
#             name=chain.name,
#             status=chain.status.value,
#             coordinator_url=chain.coordinator_url,
#             created_at=chain.created_at.isoformat(),
#             updated_at=chain.updated_at.isoformat(),
#             wallet_count=stats.get("wallet_count", 0),
#             recent_activity=stats.get("recent_activity", 0)
#         )
#         chains.append(chain_info)
#
#     return ChainListResponse(
#         chains=chains,
#         total_chains=len(chains),
#         active_chains=len(active_chains)
#     )


# @router.post("/chains", response_model=ChainCreateResponse, status_code=status.HTTP_201_CREATED, summary="Create a new chain")
# @rate_limit(rate=50, per=60)
# def create_chain(
#     request: Request,
#     chain_request: ChainCreateRequest,
#     chain_manager: ChainManager = Depends(get_chain_manager)
# ) -> ChainCreateResponse:
#     """Create a new blockchain chain configuration"""
#     from .chain.manager import ChainConfig
#
#     chain_config = ChainConfig(
#         chain_id=chain_request.chain_id,
#         name=chain_request.name,
#         coordinator_url=chain_request.coordinator_url,
#         coordinator_api_key=chain_request.coordinator_api_key,
#         metadata=chain_request.metadata
#     )
#
#     success = chain_manager.add_chain(chain_config)
#     if not success:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail=f"Chain {chain_request.chain_id} already exists"
#         )
#
#     chain_info = ChainInfo(
#         chain_id=chain_config.chain_id,
#         name=chain_config.name,
#         status=chain_config.status.value,
#         coordinator_url=chain_config.coordinator_url,
#         created_at=chain_config.created_at.isoformat(),
#         updated_at=chain_config.updated_at.isoformat(),
#         wallet_count=0,
#         recent_activity=0
#     )
#     return ChainCreateResponse(chain=chain_info)


# @router.get("/chains/{chain_id}/wallets", response_model=WalletListResponse, summary="List wallets in a specific chain")
# @rate_limit(rate=200, per=60)
# def list_chain_wallets(
#     request: Request,
#     chain_id: str,
#     wallet_service: ChainAwareWalletService = Depends(get_chain_aware_wallet_service)
# ) -> WalletListResponse:
#     """List wallets in a specific blockchain chain"""
#     wallets = wallet_service.list_wallets(chain_id)
#
#     descriptors = []
#     for wallet in wallets:
#         descriptor = WalletDescriptor(
#             wallet_id=wallet.wallet_id,
#             chain_id=wallet.chain_id,
#             public_key=wallet.public_key,
#             address=wallet.address,
#             metadata=wallet.metadata
#         )
#         descriptors.append(descriptor)
#
#     return WalletListResponse(
#         chain_id=chain_id,
#         wallets=descriptors,
#         total_wallets=len(descriptors)
#     )


# @router.post("/chains/{chain_id}/wallets", response_model=WalletCreateResponse, status_code=status.HTTP_201_CREATED, summary="Create wallet in a specific chain")
# @rate_limit(rate=50, per=60)
# def create_chain_wallet(
#     request: Request,
#     chain_id: str,
#     wallet_request: WalletCreateRequest,
#     wallet_service: ChainAwareWalletService = Depends(get_chain_aware_wallet_service)
# ) -> WalletCreateResponse:
#     """Create a wallet in a specific blockchain chain"""
#     # Validate chain_id to prevent path traversal
#     import re
#     CHAIN_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{3,30}$')
#
#     if not CHAIN_ID_PATTERN.match(chain_id):
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chain_id format")
#
#     try:
#         secret = base64.b64decode(wallet_request.secret_key) if wallet_request.secret_key else None
#     except Exception as exc:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid base64 secret") from exc
#
#     wallet_metadata = wallet_service.create_wallet(
#         chain_id=chain_id,
#         wallet_id=wallet_request.wallet_id,
#         password=wallet_request.password,
#         secret_key=secret,
#         metadata=wallet_request.metadata
#     )
#
#     if not wallet_metadata:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Failed to create wallet in chain"
#         )
#
#     wallet = WalletDescriptor(
#         wallet_id=wallet_metadata.wallet_id,
#         chain_id=wallet_metadata.chain_id,
#         public_key=wallet_metadata.public_key,
#         address=wallet_metadata.address,
#         metadata=wallet_metadata.metadata
#     )
#
#     return WalletCreateResponse(wallet=wallet)


# @router.post("/chains/{chain_id}/wallets/{wallet_id}/unlock", response_model=WalletUnlockResponse, summary="Unlock wallet in a specific chain")
# @rate_limit(rate=50, per=60)
# def unlock_chain_wallet(
#     request: Request,
#     chain_id: str,
#     wallet_id: str,
#     unlock_request: WalletUnlockRequest,
#     wallet_service: ChainAwareWalletService = Depends(get_chain_aware_wallet_service)
# ) -> WalletUnlockResponse:
#     """Unlock a wallet in a specific blockchain chain"""
#     # Validate chain_id to prevent path traversal
#     import re
#     CHAIN_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{3,30}$')
#
#     if not CHAIN_ID_PATTERN.match(chain_id):
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chain_id format")
#
#     success = wallet_service.unlock_wallet(chain_id, wallet_id, unlock_request.password)
#     if not success:
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
#
#     return WalletUnlockResponse(wallet_id=wallet_id, chain_id=chain_id, unlocked=True)


# @router.post("/chains/{chain_id}/wallets/{wallet_id}/sign", response_model=WalletSignResponse, summary="Sign payload with wallet in a specific chain")
# @rate_limit(rate=50, per=60)
# def sign_chain_payload(
#     request: Request,
#     chain_id: str,
#     wallet_id: str,
#     sign_request: WalletSignRequest,
#     wallet_service: ChainAwareWalletService = Depends(get_chain_aware_wallet_service)
# ) -> WalletSignResponse:
#     """Sign a payload with a wallet in a specific blockchain chain"""
#     # Validate chain_id to prevent path traversal
#     import re
#     CHAIN_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{3,30}$')
#
#     if not CHAIN_ID_PATTERN.match(chain_id):
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chain_id format")
#
#     try:
#         message = base64.b64decode(sign_request.message_base64)
#     except Exception as exc:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid base64 message") from exc
#
#     ip_address = request.client.host if request.client else "unknown"
#     signature = wallet_service.sign_message(chain_id, wallet_id, sign_request.password, message, ip_address)
#
#     if not signature:
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
#
#     return WalletSignResponse(
#         wallet_id=wallet_id,
#         chain_id=chain_id,
#         signature_base64=base64.b64encode(signature).decode()
#     )


# @router.post("/wallets/migrate", response_model=WalletMigrationResponse, summary="Migrate wallet between chains")
# @rate_limit(rate=50, per=60)
# def migrate_wallet(
#     request: Request,
#     migration_request: WalletMigrationRequest,
#     wallet_service: ChainAwareWalletService = Depends(get_chain_aware_wallet_service)
# ) -> WalletMigrationResponse:
#     """Migrate a wallet from one chain to another"""
#     # Validate chain_ids to prevent path traversal
#     import re
#     CHAIN_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{3,30}$')
#
#     if not CHAIN_ID_PATTERN.match(migration_request.source_chain_id) or not CHAIN_ID_PATTERN.match(migration_request.target_chain_id):
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chain_id format")
#
#     success = wallet_service.migrate_wallet_between_chains(
#         source_chain_id=migration_request.source_chain_id,
#         target_chain_id=migration_request.target_chain_id,
#         wallet_id=migration_request.wallet_id,
#         password=migration_request.password,
#         new_password=migration_request.new_password
#     )
#
#     if not success:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Failed to migrate wallet"
#         )
#
#     # Get both wallet descriptors
#     source_wallet = wallet_service.get_wallet(migration_request.source_chain_id, migration_request.wallet_id)
#     target_wallet = wallet_service.get_wallet(migration_request.target_chain_id, migration_request.wallet_id)
#
#     if not source_wallet or not target_wallet:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Migration completed but wallet retrieval failed"
#         )
#
#     source_descriptor = WalletDescriptor(
#         wallet_id=source_wallet.wallet_id,
#         chain_id=source_wallet.chain_id,
#         public_key=source_wallet.public_key,
#         address=source_wallet.address,
#         metadata=source_wallet.metadata
#     )
#
#     target_descriptor = WalletDescriptor(
#         wallet_id=target_wallet.wallet_id,
#         chain_id=target_wallet.chain_id,
#         public_key=target_wallet.public_key,
#         address=target_wallet.address,
#         metadata=target_wallet.metadata
#     )
#
#     return WalletMigrationResponse(
#         success=True,
#         source_wallet=source_descriptor,
#         target_wallet=target_descriptor,
#         migration_timestamp=datetime.now().isoformat()
#     )
