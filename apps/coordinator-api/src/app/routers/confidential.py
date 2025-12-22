"""
API endpoints for confidential transactions
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import json
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..models import (
    ConfidentialTransaction,
    ConfidentialTransactionCreate,
    ConfidentialTransactionView,
    ConfidentialAccessRequest,
    ConfidentialAccessResponse,
    KeyRegistrationRequest,
    KeyRegistrationResponse,
    AccessLogQuery,
    AccessLogResponse
)
from ..services.encryption import EncryptionService, EncryptedData
from ..services.key_management import KeyManager, KeyManagementError
from ..services.access_control import AccessController
from ..auth import get_api_key
from ..logging import get_logger

logger = get_logger(__name__)

# Initialize router and security
router = APIRouter(prefix="/confidential", tags=["confidential"])
security = HTTPBearer()
limiter = Limiter(key_func=get_remote_address)

# Global instances (in production, inject via DI)
encryption_service: Optional[EncryptionService] = None
key_manager: Optional[KeyManager] = None
access_controller: Optional[AccessController] = None


def get_encryption_service() -> EncryptionService:
    """Get encryption service instance"""
    global encryption_service
    if encryption_service is None:
        # Initialize with key manager
        from ..services.key_management import FileKeyStorage
        key_storage = FileKeyStorage("/tmp/aitbc_keys")
        key_manager = KeyManager(key_storage)
        encryption_service = EncryptionService(key_manager)
    return encryption_service


def get_key_manager() -> KeyManager:
    """Get key manager instance"""
    global key_manager
    if key_manager is None:
        from ..services.key_management import FileKeyStorage
        key_storage = FileKeyStorage("/tmp/aitbc_keys")
        key_manager = KeyManager(key_storage)
    return key_manager


def get_access_controller() -> AccessController:
    """Get access controller instance"""
    global access_controller
    if access_controller is None:
        from ..services.access_control import PolicyStore
        policy_store = PolicyStore()
        access_controller = AccessController(policy_store)
    return access_controller


@router.post("/transactions", response_model=ConfidentialTransactionView)
async def create_confidential_transaction(
    request: ConfidentialTransactionCreate,
    api_key: str = Depends(get_api_key)
):
    """Create a new confidential transaction with optional encryption"""
    try:
        # Generate transaction ID
        transaction_id = f"ctx-{datetime.utcnow().timestamp()}"
        
        # Create base transaction
        transaction = ConfidentialTransaction(
            transaction_id=transaction_id,
            job_id=request.job_id,
            timestamp=datetime.utcnow(),
            status="created",
            amount=request.amount,
            pricing=request.pricing,
            settlement_details=request.settlement_details,
            confidential=request.confidential,
            participants=request.participants,
            access_policies=request.access_policies
        )
        
        # Encrypt sensitive data if requested
        if request.confidential and request.participants:
            # Prepare data for encryption
            sensitive_data = {
                "amount": request.amount,
                "pricing": request.pricing,
                "settlement_details": request.settlement_details
            }
            
            # Remove None values
            sensitive_data = {k: v for k, v in sensitive_data.items() if v is not None}
            
            if sensitive_data:
                # Encrypt data
                enc_service = get_encryption_service()
                encrypted = enc_service.encrypt(
                    data=sensitive_data,
                    participants=request.participants,
                    include_audit=True
                )
                
                # Update transaction with encrypted data
                transaction.encrypted_data = encrypted.to_dict()["ciphertext"]
                transaction.encrypted_keys = encrypted.to_dict()["encrypted_keys"]
                transaction.algorithm = encrypted.algorithm
                
                # Clear plaintext fields
                transaction.amount = None
                transaction.pricing = None
                transaction.settlement_details = None
        
        # Store transaction (in production, save to database)
        logger.info(f"Created confidential transaction: {transaction_id}")
        
        # Return view
        return ConfidentialTransactionView(
            transaction_id=transaction.transaction_id,
            job_id=transaction.job_id,
            timestamp=transaction.timestamp,
            status=transaction.status,
            amount=transaction.amount,  # Will be None if encrypted
            pricing=transaction.pricing,
            settlement_details=transaction.settlement_details,
            confidential=transaction.confidential,
            participants=transaction.participants,
            has_encrypted_data=transaction.encrypted_data is not None
        )
        
    except Exception as e:
        logger.error(f"Failed to create confidential transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transactions/{transaction_id}", response_model=ConfidentialTransactionView)
async def get_confidential_transaction(
    transaction_id: str,
    api_key: str = Depends(get_api_key)
):
    """Get confidential transaction metadata (without decrypting sensitive data)"""
    try:
        # Retrieve transaction (in production, query from database)
        # For now, return error as we don't have storage
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get transaction {transaction_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transactions/{transaction_id}/access", response_model=ConfidentialAccessResponse)
@limiter.limit("10/minute")  # Rate limit decryption requests
async def access_confidential_data(
    request: ConfidentialAccessRequest,
    transaction_id: str,
    api_key: str = Depends(get_api_key)
):
    """Request access to decrypt confidential transaction data"""
    try:
        # Validate request
        if request.transaction_id != transaction_id:
            raise HTTPException(status_code=400, detail="Transaction ID mismatch")
        
        # Get transaction (in production, query from database)
        # For now, create mock transaction
        transaction = ConfidentialTransaction(
            transaction_id=transaction_id,
            job_id="test-job",
            timestamp=datetime.utcnow(),
            status="completed",
            confidential=True,
            participants=["client-456", "miner-789"]
        )
        
        if not transaction.confidential:
            raise HTTPException(status_code=400, detail="Transaction is not confidential")
        
        # Check access authorization
        acc_controller = get_access_controller()
        if not acc_controller.verify_access(request):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Decrypt data
        enc_service = get_encryption_service()
        
        # Reconstruct encrypted data
        if not transaction.encrypted_data or not transaction.encrypted_keys:
            raise HTTPException(status_code=404, detail="No encrypted data found")
        
        encrypted_data = EncryptedData.from_dict({
            "ciphertext": transaction.encrypted_data,
            "encrypted_keys": transaction.encrypted_keys,
            "algorithm": transaction.algorithm or "AES-256-GCM+X25519"
        })
        
        # Decrypt for requester
        try:
            decrypted_data = enc_service.decrypt(
                encrypted_data=encrypted_data,
                participant_id=request.requester,
                purpose=request.purpose
            )
            
            return ConfidentialAccessResponse(
                success=True,
                data=decrypted_data,
                access_id=f"access-{datetime.utcnow().timestamp()}"
            )
            
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return ConfidentialAccessResponse(
                success=False,
                error=str(e)
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to access confidential data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transactions/{transaction_id}/audit", response_model=ConfidentialAccessResponse)
async def audit_access_confidential_data(
    transaction_id: str,
    authorization: str,
    purpose: str = "compliance",
    api_key: str = Depends(get_api_key)
):
    """Audit access to confidential transaction data"""
    try:
        # Get transaction
        transaction = ConfidentialTransaction(
            transaction_id=transaction_id,
            job_id="test-job",
            timestamp=datetime.utcnow(),
            status="completed",
            confidential=True
        )
        
        if not transaction.confidential:
            raise HTTPException(status_code=400, detail="Transaction is not confidential")
        
        # Decrypt with audit key
        enc_service = get_encryption_service()
        
        if not transaction.encrypted_data or not transaction.encrypted_keys:
            raise HTTPException(status_code=404, detail="No encrypted data found")
        
        encrypted_data = EncryptedData.from_dict({
            "ciphertext": transaction.encrypted_data,
            "encrypted_keys": transaction.encrypted_keys,
            "algorithm": transaction.algorithm or "AES-256-GCM+X25519"
        })
        
        # Decrypt for audit
        try:
            decrypted_data = enc_service.audit_decrypt(
                encrypted_data=encrypted_data,
                audit_authorization=authorization,
                purpose=purpose
            )
            
            return ConfidentialAccessResponse(
                success=True,
                data=decrypted_data,
                access_id=f"audit-{datetime.utcnow().timestamp()}"
            )
            
        except Exception as e:
            logger.error(f"Audit decryption failed: {e}")
            return ConfidentialAccessResponse(
                success=False,
                error=str(e)
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed audit access: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/keys/register", response_model=KeyRegistrationResponse)
async def register_encryption_key(
    request: KeyRegistrationRequest,
    api_key: str = Depends(get_api_key)
):
    """Register public key for confidential transactions"""
    try:
        # Get key manager
        km = get_key_manager()
        
        # Check if participant already has keys
        try:
            existing_key = km.get_public_key(request.participant_id)
            if existing_key:
                # Key exists, return version
                return KeyRegistrationResponse(
                    success=True,
                    participant_id=request.participant_id,
                    key_version=1,  # Would get from storage
                    registered_at=datetime.utcnow(),
                    error=None
                )
        except:
            pass  # Key doesn't exist, continue
        
        # Generate new key pair
        key_pair = await km.generate_key_pair(request.participant_id)
        
        return KeyRegistrationResponse(
            success=True,
            participant_id=request.participant_id,
            key_version=key_pair.version,
            registered_at=key_pair.created_at,
            error=None
        )
        
    except KeyManagementError as e:
        logger.error(f"Key registration failed: {e}")
        return KeyRegistrationResponse(
            success=False,
            participant_id=request.participant_id,
            key_version=0,
            registered_at=datetime.utcnow(),
            error=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to register key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/keys/rotate")
async def rotate_encryption_key(
    participant_id: str,
    api_key: str = Depends(get_api_key)
):
    """Rotate encryption keys for participant"""
    try:
        km = get_key_manager()
        
        # Rotate keys
        new_key_pair = await km.rotate_keys(participant_id)
        
        return {
            "success": True,
            "participant_id": participant_id,
            "new_version": new_key_pair.version,
            "rotated_at": new_key_pair.created_at
        }
        
    except KeyManagementError as e:
        logger.error(f"Key rotation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to rotate keys: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/access/logs", response_model=AccessLogResponse)
async def get_access_logs(
    query: AccessLogQuery = Depends(),
    api_key: str = Depends(get_api_key)
):
    """Get access logs for confidential transactions"""
    try:
        # Query logs (in production, query from database)
        # For now, return empty response
        return AccessLogResponse(
            logs=[],
            total_count=0,
            has_more=False
        )
        
    except Exception as e:
        logger.error(f"Failed to get access logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_confidential_status(
    api_key: str = Depends(get_api_key)
):
    """Get status of confidential transaction system"""
    try:
        km = get_key_manager()
        enc_service = get_encryption_service()
        
        # Get system status
        participants = await km.list_participants()
        
        return {
            "enabled": True,
            "algorithm": "AES-256-GCM+X25519",
            "participants_count": len(participants),
            "transactions_count": 0,  # Would query from database
            "audit_enabled": True
        }
        
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
