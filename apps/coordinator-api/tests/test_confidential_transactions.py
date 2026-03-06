"""
Tests for confidential transaction functionality
"""

import pytest
import asyncio
import json
import base64
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from app.models import (
    ConfidentialTransaction,
    ConfidentialTransactionCreate,
    ConfidentialAccessRequest,
    KeyRegistrationRequest
)
from app.services.encryption import EncryptionService, EncryptedData
from app.services.key_management import KeyManager, FileKeyStorage
from app.services.access_control import AccessController, PolicyStore
from app.services.audit_logging import AuditLogger


class TestEncryptionService:
    """Test encryption service functionality"""
    
    @pytest.fixture
    def key_manager(self):
        """Create test key manager"""
        storage = FileKeyStorage("/tmp/test_keys")
        return KeyManager(storage)
    
    @pytest.fixture
    def encryption_service(self, key_manager):
        """Create test encryption service"""
        return EncryptionService(key_manager)
    
    @pytest.mark.asyncio
    async def test_encrypt_decrypt_success(self, encryption_service, key_manager):
        """Test successful encryption and decryption"""
        # Generate test keys
        await key_manager.generate_key_pair("client-123")
        await key_manager.generate_key_pair("miner-456")
        
        # Test data
        data = {
            "amount": "1000",
            "pricing": {"rate": "0.1", "currency": "AITBC"},
            "settlement_details": {"method": "crypto", "address": "0x123..."}
        }
        
        participants = ["client-123", "miner-456"]
        
        # Encrypt data
        encrypted = encryption_service.encrypt(
            data=data,
            participants=participants,
            include_audit=True
        )
        
        assert encrypted.ciphertext is not None
        assert len(encrypted.encrypted_keys) == 3  # 2 participants + audit
        assert "client-123" in encrypted.encrypted_keys
        assert "miner-456" in encrypted.encrypted_keys
        assert "audit" in encrypted.encrypted_keys
        
        # Decrypt for client
        decrypted = encryption_service.decrypt(
            encrypted_data=encrypted,
            participant_id="client-123",
            purpose="settlement"
        )
        
        assert decrypted == data
        
        # Decrypt for miner
        decrypted_miner = encryption_service.decrypt(
            encrypted_data=encrypted,
            participant_id="miner-456",
            purpose="settlement"
        )
        
        assert decrypted_miner == data
    
    @pytest.mark.asyncio
    async def test_audit_decrypt(self, encryption_service, key_manager):
        """Test audit decryption"""
        # Generate keys
        await key_manager.generate_key_pair("client-123")
        
        # Create audit authorization
        auth = await key_manager.create_audit_authorization(
            issuer="regulator",
            purpose="compliance"
        )
        
        # Encrypt data
        data = {"amount": "1000", "secret": "hidden"}
        encrypted = encryption_service.encrypt(
            data=data,
            participants=["client-123"],
            include_audit=True
        )
        
        # Decrypt with audit key
        decrypted = encryption_service.audit_decrypt(
            encrypted_data=encrypted,
            audit_authorization=auth,
            purpose="compliance"
        )
        
        assert decrypted == data
    
    def test_encrypt_no_participants(self, encryption_service):
        """Test encryption with no participants"""
        data = {"test": "data"}
        
        with pytest.raises(Exception):
            encryption_service.encrypt(
                data=data,
                participants=[],
                include_audit=True
            )


class TestKeyManager:
    """Test key management functionality"""
    
    @pytest.fixture
    def key_storage(self, tmp_path):
        """Create test key storage"""
        return FileKeyStorage(str(tmp_path / "keys"))
    
    @pytest.fixture
    def key_manager(self, key_storage):
        """Create test key manager"""
        return KeyManager(key_storage)
    
    @pytest.mark.asyncio
    async def test_generate_key_pair(self, key_manager):
        """Test key pair generation"""
        key_pair = await key_manager.generate_key_pair("test-participant")
        
        assert key_pair.participant_id == "test-participant"
        assert key_pair.algorithm == "X25519"
        assert key_pair.private_key is not None
        assert key_pair.public_key is not None
        assert key_pair.version == 1
    
    @pytest.mark.asyncio
    async def test_key_rotation(self, key_manager):
        """Test key rotation"""
        # Generate initial key
        initial_key = await key_manager.generate_key_pair("test-participant")
        initial_version = initial_key.version
        
        # Rotate keys
        new_key = await key_manager.rotate_keys("test-participant")
        
        assert new_key.participant_id == "test-participant"
        assert new_key.version > initial_version
        assert new_key.private_key != initial_key.private_key
        assert new_key.public_key != initial_key.public_key
    
    def test_get_public_key(self, key_manager):
        """Test retrieving public key"""
        # This would need a key to be pre-generated
        with pytest.raises(Exception):
            key_manager.get_public_key("nonexistent")


class TestAccessController:
    """Test access control functionality"""
    
    @pytest.fixture
    def policy_store(self):
        """Create test policy store"""
        return PolicyStore()
    
    @pytest.fixture
    def access_controller(self, policy_store):
        """Create test access controller"""
        return AccessController(policy_store)
    
    def test_client_access_own_data(self, access_controller):
        """Test client accessing own transaction"""
        request = ConfidentialAccessRequest(
            transaction_id="tx-123",
            requester="client-456",
            purpose="settlement"
        )
        
        # Should allow access
        assert access_controller.verify_access(request) is True
    
    def test_miner_access_assigned_data(self, access_controller):
        """Test miner accessing assigned transaction"""
        request = ConfidentialAccessRequest(
            transaction_id="tx-123",
            requester="miner-789",
            purpose="settlement"
        )
        
        # Should allow access
        assert access_controller.verify_access(request) is True
    
    def test_unauthorized_access(self, access_controller):
        """Test unauthorized access attempt"""
        request = ConfidentialAccessRequest(
            transaction_id="tx-123",
            requester="unauthorized-user",
            purpose="settlement"
        )
        
        # Should deny access
        assert access_controller.verify_access(request) is False
    
    def test_audit_access(self, access_controller):
        """Test auditor access"""
        request = ConfidentialAccessRequest(
            transaction_id="tx-123",
            requester="auditor-001",
            purpose="compliance"
        )
        
        # Should allow access during business hours
        assert access_controller.verify_access(request) is True


class TestAuditLogger:
    """Test audit logging functionality"""
    
    @pytest.fixture
    def audit_logger(self, tmp_path):
        """Create test audit logger"""
        return AuditLogger(log_dir=str(tmp_path / "audit"))
    
    def test_log_access(self, audit_logger):
        """Test logging access events"""
        # Log access event
        audit_logger.log_access(
            participant_id="client-456",
            transaction_id="tx-123",
            action="decrypt",
            outcome="success",
            ip_address="192.168.1.1",
            user_agent="test-client"
        )
        
        # Wait for background writer
        import time
        time.sleep(0.1)
        
        # Query logs
        events = audit_logger.query_logs(
            participant_id="client-456",
            limit=10
        )
        
        assert len(events) > 0
        assert events[0].participant_id == "client-456"
        assert events[0].transaction_id == "tx-123"
        assert events[0].action == "decrypt"
        assert events[0].outcome == "success"
    
    def test_log_key_operation(self, audit_logger):
        """Test logging key operations"""
        audit_logger.log_key_operation(
            participant_id="miner-789",
            operation="rotate",
            key_version=2,
            outcome="success"
        )
        
        # Wait for background writer
        import time
        time.sleep(0.1)
        
        # Query logs
        events = audit_logger.query_logs(
            event_type="key_operation",
            limit=10
        )
        
        assert len(events) > 0
        assert events[0].event_type == "key_operation"
        assert events[0].action == "rotate"
        assert events[0].details["key_version"] == 2
    
    def test_export_logs(self, audit_logger):
        """Test log export functionality"""
        # Add some test events
        audit_logger.log_access(
            participant_id="test-user",
            transaction_id="tx-456",
            action="test",
            outcome="success"
        )
        
        # Wait for background writer
        import time
        time.sleep(0.1)
        
        # Export logs
        export_data = audit_logger.export_logs(
            start_time=datetime.utcnow() - timedelta(hours=1),
            end_time=datetime.utcnow(),
            format="json"
        )
        
        # Parse export
        export = json.loads(export_data)
        
        assert "export_metadata" in export
        assert "events" in export
        assert export["export_metadata"]["event_count"] > 0


class TestConfidentialTransactionAPI:
    """Test confidential transaction API endpoints"""
    
    @pytest.mark.asyncio
    async def test_create_confidential_transaction(self):
        """Test creating a confidential transaction"""
        from app.routers.confidential import create_confidential_transaction
        
        request = ConfidentialTransactionCreate(
            job_id="job-123",
            amount="1000",
            pricing={"rate": "0.1"},
            confidential=True,
            participants=["client-456", "miner-789"]
        )
        
        # Mock API key
        with patch('app.routers.confidential.get_api_key', return_value="test-key"):
            response = await create_confidential_transaction(request)
        
        assert response.transaction_id.startswith("ctx-")
        assert response.job_id == "job-123"
        assert response.confidential is True
        assert response.has_encrypted_data is True
        assert response.amount is None  # Should be encrypted
    
    @pytest.mark.asyncio
    async def test_access_confidential_data(self):
        """Test accessing confidential transaction data"""
        from app.routers.confidential import access_confidential_data
        
        request = ConfidentialAccessRequest(
            transaction_id="tx-123",
            requester="client-456",
            purpose="settlement"
        )
        
        # Mock dependencies
        with patch('app.routers.confidential.get_api_key', return_value="test-key"), \
             patch('app.routers.confidential.get_access_controller') as mock_ac, \
             patch('app.routers.confidential.get_encryption_service') as mock_es:
            
            # Mock access control
            mock_ac.return_value.verify_access.return_value = True
            
            # Mock encryption service
            mock_es.return_value.decrypt.return_value = {
                "amount": "1000",
                "pricing": {"rate": "0.1"}
            }
            
            response = await access_confidential_data(request, "tx-123")
        
        assert response.success is True
        assert response.data is not None
        assert response.data["amount"] == "1000"
    
    @pytest.mark.asyncio
    async def test_register_key(self):
        """Test key registration"""
        from app.routers.confidential import register_encryption_key
        
        # Generate test key pair
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        private_key = X25519PrivateKey.generate()
        public_key = private_key.public_key()
        public_key_bytes = public_key.public_bytes_raw()
        
        request = KeyRegistrationRequest(
            participant_id="test-participant",
            public_key=base64.b64encode(public_key_bytes).decode()
        )
        
        with patch('app.routers.confidential.get_api_key', return_value="test-key"):
            response = await register_encryption_key(request)
        
        assert response.success is True
        assert response.participant_id == "test-participant"
        assert response.key_version >= 1


# Integration Tests
class TestConfidentialTransactionFlow:
    """End-to-end tests for confidential transaction flow"""
    
    @pytest.mark.asyncio
    async def test_full_confidential_flow(self):
        """Test complete confidential transaction flow"""
        # Setup
        key_storage = FileKeyStorage("/tmp/integration_keys")
        key_manager = KeyManager(key_storage)
        encryption_service = EncryptionService(key_manager)
        access_controller = AccessController(PolicyStore())
        
        # 1. Generate keys for participants
        await key_manager.generate_key_pair("client-123")
        await key_manager.generate_key_pair("miner-456")
        
        # 2. Create confidential transaction
        transaction_data = {
            "amount": "1000",
            "pricing": {"rate": "0.1", "currency": "AITBC"},
            "settlement_details": {"method": "crypto"}
        }
        
        participants = ["client-123", "miner-456"]
        
        # 3. Encrypt data
        encrypted = encryption_service.encrypt(
            data=transaction_data,
            participants=participants,
            include_audit=True
        )
        
        # 4. Store transaction (mock)
        transaction = ConfidentialTransaction(
            transaction_id="ctx-test-123",
            job_id="job-456",
            timestamp=datetime.utcnow(),
            status="created",
            confidential=True,
            participants=participants,
            encrypted_data=encrypted.to_dict()["ciphertext"],
            encrypted_keys=encrypted.to_dict()["encrypted_keys"],
            algorithm=encrypted.algorithm
        )
        
        # 5. Client accesses data
        client_request = ConfidentialAccessRequest(
            transaction_id=transaction.transaction_id,
            requester="client-123",
            purpose="settlement"
        )
        
        assert access_controller.verify_access(client_request) is True
        
        client_data = encryption_service.decrypt(
            encrypted_data=encrypted,
            participant_id="client-123",
            purpose="settlement"
        )
        
        assert client_data == transaction_data
        
        # 6. Miner accesses data
        miner_request = ConfidentialAccessRequest(
            transaction_id=transaction.transaction_id,
            requester="miner-456",
            purpose="settlement"
        )
        
        assert access_controller.verify_access(miner_request) is True
        
        miner_data = encryption_service.decrypt(
            encrypted_data=encrypted,
            participant_id="miner-456",
            purpose="settlement"
        )
        
        assert miner_data == transaction_data
        
        # 7. Unauthorized access denied
        unauthorized_request = ConfidentialAccessRequest(
            transaction_id=transaction.transaction_id,
            requester="unauthorized",
            purpose="settlement"
        )
        
        assert access_controller.verify_access(unauthorized_request) is False
        
        # 8. Audit access
        audit_auth = await key_manager.create_audit_authorization(
            issuer="regulator",
            purpose="compliance"
        )
        
        audit_data = encryption_service.audit_decrypt(
            encrypted_data=encrypted,
            audit_authorization=audit_auth,
            purpose="compliance"
        )
        
        assert audit_data == transaction_data
        
        # Cleanup
        import shutil
        shutil.rmtree("/tmp/integration_keys", ignore_errors=True)
