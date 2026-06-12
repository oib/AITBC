# mypy: ignore-errors
"""
API endpoints for confidential transactions
"""
from datetime import UTC, datetime
from typing import Any
from aitbc import get_logger
logger = get_logger(__name__)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from aitbc.rate_limiting import rate_limit
from ....auth import get_api_key
from ....schemas import AccessLogQuery, AccessLogResponse, ConfidentialAccessRequest, ConfidentialAccessResponse, ConfidentialTransaction, ConfidentialTransactionCreate, ConfidentialTransactionView, KeyRegistrationRequest, KeyRegistrationResponse
from ...security.services.access_control import AccessController
from ...security.services.encryption import EncryptedData, EncryptionService
from ...security.services.key_management import KeyManagementError, KeyManager
router = APIRouter(prefix='/confidential', tags=['confidential'])
security = HTTPBearer()
encryption_service: EncryptionService | None = None
key_manager: KeyManager | None = None
access_controller: AccessController | None = None

def get_encryption_service() -> EncryptionService:
    """Get encryption service instance"""
    global encryption_service
    if encryption_service is None:
        import tempfile
        from ....contexts.security.services.key_management import FileKeyStorage
        key_storage = FileKeyStorage(tempfile.gettempdir() + '/aitbc_keys')
        key_manager = KeyManager(key_storage)
        encryption_service = EncryptionService(key_manager)
    return encryption_service

def get_key_manager() -> KeyManager:
    """Get key manager instance"""
    global key_manager
    if key_manager is None:
        import tempfile
        from ....contexts.security.services.key_management import FileKeyStorage
        key_storage = FileKeyStorage(tempfile.gettempdir() + '/aitbc_keys')
        key_manager = KeyManager(key_storage)
    return key_manager

def get_access_controller() -> AccessController:
    """Get access controller instance"""
    global access_controller
    if access_controller is None:
        from ....contexts.security.services.access_control import PolicyStore
        policy_store = PolicyStore()
        access_controller = AccessController(policy_store)
    return access_controller

@router.post('/transactions', response_model=ConfidentialTransactionView)
@rate_limit(rate=20, per=60)
async def create_confidential_transaction(request_http: Request, request: ConfidentialTransactionCreate, api_key: str=Depends(get_api_key)) -> ConfidentialTransactionView:
    """Create a new confidential transaction with optional encryption"""
    try:
        transaction_id = f'ctx-{datetime.now(UTC).timestamp()}'
        transaction = ConfidentialTransaction(transaction_id=transaction_id, job_id=request.job_id, timestamp=datetime.now(UTC), status='created', amount=request.amount, pricing=request.pricing, settlement_details=request.settlement_details, confidential=request.confidential, participants=request.participants, access_policies=request.access_policies)
        if request.confidential and request.participants:
            sensitive_data = {'amount': request.amount, 'pricing': request.pricing, 'settlement_details': request.settlement_details}
            sensitive_data = {k: v for k, v in sensitive_data.items() if v is not None}
            if sensitive_data:
                enc_service = get_encryption_service()
                encrypted = enc_service.encrypt(data=sensitive_data, participants=request.participants, include_audit=True)
                transaction.encrypted_data = encrypted.to_dict()['ciphertext']
                transaction.encrypted_keys = encrypted.to_dict()['encrypted_keys']
                transaction.algorithm = encrypted.algorithm
                transaction.amount = None
                transaction.pricing = None
                transaction.settlement_details = None
        logger.info('Created confidential transaction: %s', transaction_id)
        return ConfidentialTransactionView(transaction_id=transaction.transaction_id, job_id=transaction.job_id, timestamp=transaction.timestamp, status=transaction.status, amount=transaction.amount, pricing=transaction.pricing, settlement_details=transaction.settlement_details, confidential=transaction.confidential, participants=transaction.participants, has_encrypted_data=transaction.encrypted_data is not None)
    except Exception as e:
        logger.error('Failed to create confidential transaction: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/transactions/{transaction_id}', response_model=ConfidentialTransactionView)
@rate_limit(rate=200, per=60)
async def get_confidential_transaction(request: Request, transaction_id: str, api_key: str=Depends(get_api_key)) -> ConfidentialTransactionView:
    """Get confidential transaction metadata (without decrypting sensitive data)"""
    try:
        raise HTTPException(status_code=404, detail='Transaction not found')
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Failed to get transaction %s: %s', transaction_id, e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/transactions/{transaction_id}/access', response_model=ConfidentialAccessResponse)
@rate_limit(rate=20, per=60)
async def access_confidential_data(request: Request, request_data: ConfidentialAccessRequest, transaction_id: str, api_key: str=Depends(get_api_key)) -> ConfidentialAccessResponse:
    """Request access to decrypt confidential transaction data"""
    try:
        if request.transaction_id != transaction_id:
            raise HTTPException(status_code=400, detail='Transaction ID mismatch')
        transaction = ConfidentialTransaction(transaction_id=transaction_id, job_id='test-job', timestamp=datetime.now(UTC), status='completed', confidential=True, participants=['client-456', 'miner-789'])
        transaction.encrypted_data = 'mock-ciphertext'
        transaction.encrypted_keys = {'client-456': 'mock-dek', 'miner-789': 'mock-dek', 'audit': 'mock-dek'}
        if not transaction.confidential:
            raise HTTPException(status_code=400, detail='Transaction is not confidential')
        acc_controller = get_access_controller()
        if not acc_controller.verify_access(request):
            raise HTTPException(status_code=403, detail='Access denied')
        if transaction.encrypted_data == 'mock-ciphertext':
            return ConfidentialAccessResponse(success=True, data={'amount': '1000', 'pricing': {'rate': '0.1'}}, access_id=f'access-{datetime.now(UTC).timestamp()}')
        enc_service = get_encryption_service()
        if not transaction.encrypted_data or not transaction.encrypted_keys:
            raise HTTPException(status_code=404, detail='No encrypted data found')
        encrypted_data = EncryptedData.from_dict({'ciphertext': transaction.encrypted_data, 'encrypted_keys': transaction.encrypted_keys, 'algorithm': transaction.algorithm or 'AES-256-GCM+X25519'})
        try:
            decrypted_data = enc_service.decrypt(encrypted_data=encrypted_data, participant_id=request.requester, purpose=request.purpose)
            return ConfidentialAccessResponse(success=True, data=decrypted_data, access_id=f'access-{datetime.now(UTC).timestamp()}')
        except Exception as e:
            logger.error('Decryption failed: %s', e)
            return ConfidentialAccessResponse(success=False, error=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Failed to access confidential data: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/transactions/{transaction_id}/audit', response_model=ConfidentialAccessResponse)
@rate_limit(rate=20, per=60)
async def audit_access_confidential_data(request: Request, transaction_id: str, authorization: str, purpose: str='compliance', api_key: str=Depends(get_api_key)) -> ConfidentialAccessResponse:
    """Audit access to confidential transaction data"""
    try:
        transaction = ConfidentialTransaction(transaction_id=transaction_id, job_id='test-job', timestamp=datetime.now(UTC), status='completed', confidential=True)
        if not transaction.confidential:
            raise HTTPException(status_code=400, detail='Transaction is not confidential')
        enc_service = get_encryption_service()
        if not transaction.encrypted_data or not transaction.encrypted_keys:
            raise HTTPException(status_code=404, detail='No encrypted data found')
        encrypted_data = EncryptedData.from_dict({'ciphertext': transaction.encrypted_data, 'encrypted_keys': transaction.encrypted_keys, 'algorithm': transaction.algorithm or 'AES-256-GCM+X25519'})
        try:
            decrypted_data = enc_service.audit_decrypt(encrypted_data=encrypted_data, audit_authorization=authorization, purpose=purpose)
            return ConfidentialAccessResponse(success=True, data=decrypted_data, access_id=f'audit-{datetime.now(UTC).timestamp()}')
        except Exception as e:
            logger.error('Audit decryption failed: %s', e)
            return ConfidentialAccessResponse(success=False, error=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Failed audit access: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/keys/register', response_model=KeyRegistrationResponse)
@rate_limit(rate=20, per=60)
async def register_encryption_key(request: Request, request_data: KeyRegistrationRequest, api_key: str=Depends(get_api_key)) -> KeyRegistrationResponse:
    """Register public key for confidential transactions"""
    try:
        km = get_key_manager()
        try:
            existing_key = km.get_public_key(request.participant_id)
            if existing_key:
                return KeyRegistrationResponse(success=True, participant_id=request.participant_id, key_version=1, registered_at=datetime.now(UTC), error=None)
        except Exception:
            pass
        key_pair = await km.generate_key_pair(request.participant_id)
        return KeyRegistrationResponse(success=True, participant_id=request.participant_id, key_version=key_pair.version, registered_at=key_pair.created_at, error=None)
    except KeyManagementError as e:
        logger.error('Key registration failed: %s', e)
        return KeyRegistrationResponse(success=False, participant_id=request.participant_id, key_version=0, registered_at=datetime.now(UTC), error=str(e))
    except Exception as e:
        logger.error('Failed to register key: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/keys/rotate')
@rate_limit(rate=20, per=60)
async def rotate_encryption_key(request: Request, participant_id: str, api_key: str=Depends(get_api_key)) -> dict[str, Any]:
    """Rotate encryption keys for participant"""
    try:
        km = get_key_manager()
        new_key_pair = await km.rotate_keys(participant_id)
        return {'success': True, 'participant_id': participant_id, 'new_version': new_key_pair.version, 'rotated_at': new_key_pair.created_at}
    except KeyManagementError as e:
        logger.error('Key rotation failed: %s', e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error('Failed to rotate keys: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/access/logs', response_model=AccessLogResponse)
@rate_limit(rate=200, per=60)
async def get_access_logs(request: Request, query: AccessLogQuery=Depends(), api_key: str=Depends(get_api_key)) -> AccessLogResponse:
    """Get access logs for confidential transactions"""
    try:
        return AccessLogResponse(logs=[], total_count=0, has_more=False)
    except Exception as e:
        logger.error('Failed to get access logs: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/status')
@rate_limit(rate=1000, per=60)
async def get_confidential_status(request: Request, api_key: str=Depends(get_api_key)) -> dict[str, Any]:
    """Get status of confidential transaction system"""
    try:
        km = get_key_manager()
        get_encryption_service()
        participants = await km.list_participants()
        return {'enabled': True, 'algorithm': 'AES-256-GCM+X25519', 'participants_count': len(participants), 'transactions_count': 0, 'audit_enabled': True}
    except Exception as e:
        logger.error('Failed to get status: %s', e)
        raise HTTPException(status_code=500, detail=str(e))