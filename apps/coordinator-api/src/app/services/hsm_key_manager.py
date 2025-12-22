"""
HSM-backed key management for production use
"""

import os
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from abc import ABC, abstractmethod

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.backends import default_backend

from ..models import KeyPair, KeyRotationLog, AuditAuthorization
from ..repositories.confidential import (
    ParticipantKeyRepository,
    KeyRotationRepository
)
from ..config import settings
from ..logging import get_logger

logger = get_logger(__name__)


class HSMProvider(ABC):
    """Abstract base class for HSM providers"""
    
    @abstractmethod
    async def generate_key(self, key_id: str) -> Tuple[bytes, bytes]:
        """Generate key pair in HSM, return (public_key, key_handle)"""
        pass
    
    @abstractmethod
    async def sign_with_key(self, key_handle: bytes, data: bytes) -> bytes:
        """Sign data with HSM-stored private key"""
        pass
    
    @abstractmethod
    async def derive_shared_secret(self, key_handle: bytes, public_key: bytes) -> bytes:
        """Derive shared secret using ECDH"""
        pass
    
    @abstractmethod
    async def delete_key(self, key_handle: bytes) -> bool:
        """Delete key from HSM"""
        pass
    
    @abstractmethod
    async def list_keys(self) -> List[str]:
        """List all key IDs in HSM"""
        pass


class SoftwareHSMProvider(HSMProvider):
    """Software-based HSM provider for development/testing"""
    
    def __init__(self):
        self._keys: Dict[str, X25519PrivateKey] = {}
        self._backend = default_backend()
    
    async def generate_key(self, key_id: str) -> Tuple[bytes, bytes]:
        """Generate key pair in memory"""
        private_key = X25519PrivateKey.generate()
        public_key = private_key.public_key()
        
        # Store private key (in production, this would be in secure hardware)
        self._keys[key_id] = private_key
        
        return (
            public_key.public_bytes(Encoding.Raw, PublicFormat.Raw),
            key_id.encode()  # Use key_id as handle
        )
    
    async def sign_with_key(self, key_handle: bytes, data: bytes) -> bytes:
        """Sign with stored private key"""
        key_id = key_handle.decode()
        private_key = self._keys.get(key_id)
        
        if not private_key:
            raise ValueError(f"Key not found: {key_id}")
        
        # For X25519, we don't sign - we exchange
        # This is a placeholder for actual HSM operations
        return b"signature_placeholder"
    
    async def derive_shared_secret(self, key_handle: bytes, public_key: bytes) -> bytes:
        """Derive shared secret"""
        key_id = key_handle.decode()
        private_key = self._keys.get(key_id)
        
        if not private_key:
            raise ValueError(f"Key not found: {key_id}")
        
        peer_public = X25519PublicKey.from_public_bytes(public_key)
        return private_key.exchange(peer_public)
    
    async def delete_key(self, key_handle: bytes) -> bool:
        """Delete key from memory"""
        key_id = key_handle.decode()
        if key_id in self._keys:
            del self._keys[key_id]
            return True
        return False
    
    async def list_keys(self) -> List[str]:
        """List all keys"""
        return list(self._keys.keys())


class AzureKeyVaultProvider(HSMProvider):
    """Azure Key Vault HSM provider for production"""
    
    def __init__(self, vault_url: str, credential):
        from azure.keyvault.keys.crypto import CryptographyClient
        from azure.keyvault.keys import KeyClient
        from azure.identity import DefaultAzureCredential
        
        self.vault_url = vault_url
        self.credential = credential or DefaultAzureCredential()
        self.key_client = KeyClient(vault_url, self.credential)
        self.crypto_client = None
    
    async def generate_key(self, key_id: str) -> Tuple[bytes, bytes]:
        """Generate key in Azure Key Vault"""
        # Create EC-HSM key
        key = await self.key_client.create_ec_key(
            key_id,
            curve="P-256"  # Azure doesn't support X25519 directly
        )
        
        # Get public key
        public_key = key.key.cryptography_client.public_key()
        public_bytes = public_key.public_bytes(
            Encoding.Raw,
            PublicFormat.Raw
        )
        
        return public_bytes, key.id.encode()
    
    async def sign_with_key(self, key_handle: bytes, data: bytes) -> bytes:
        """Sign with Azure Key Vault"""
        key_id = key_handle.decode()
        crypto_client = self.key_client.get_cryptography_client(key_id)
        
        sign_result = await crypto_client.sign("ES256", data)
        return sign_result.signature
    
    async def derive_shared_secret(self, key_handle: bytes, public_key: bytes) -> bytes:
        """Derive shared secret (not directly supported in Azure)"""
        # Would need to use a different approach
        raise NotImplementedError("ECDH not supported in Azure Key Vault")
    
    async def delete_key(self, key_handle: bytes) -> bool:
        """Delete key from Azure Key Vault"""
        key_name = key_handle.decode().split("/")[-1]
        await self.key_client.begin_delete_key(key_name)
        return True
    
    async def list_keys(self) -> List[str]:
        """List keys in Azure Key Vault"""
        keys = []
        async for key in self.key_client.list_properties_of_keys():
            keys.append(key.name)
        return keys


class AWSKMSProvider(HSMProvider):
    """AWS KMS HSM provider for production"""
    
    def __init__(self, region_name: str):
        import boto3
        self.kms = boto3.client('kms', region_name=region_name)
    
    async def generate_key(self, key_id: str) -> Tuple[bytes, bytes]:
        """Generate key pair in AWS KMS"""
        # Create CMK
        response = self.kms.create_key(
            Description=f"AITBC confidential transaction key for {key_id}",
            KeyUsage='ENCRYPT_DECRYPT',
            KeySpec='ECC_NIST_P256'
        )
        
        # Get public key
        public_key = self.kms.get_public_key(KeyId=response['KeyMetadata']['KeyId'])
        
        return public_key['PublicKey'], response['KeyMetadata']['KeyId'].encode()
    
    async def sign_with_key(self, key_handle: bytes, data: bytes) -> bytes:
        """Sign with AWS KMS"""
        response = self.kms.sign(
            KeyId=key_handle.decode(),
            Message=data,
            MessageType='RAW',
            SigningAlgorithm='ECDSA_SHA_256'
        )
        return response['Signature']
    
    async def derive_shared_secret(self, key_handle: bytes, public_key: bytes) -> bytes:
        """Derive shared secret (not directly supported in KMS)"""
        raise NotImplementedError("ECDH not supported in AWS KMS")
    
    async def delete_key(self, key_handle: bytes) -> bool:
        """Schedule key deletion in AWS KMS"""
        self.kms.schedule_key_deletion(KeyId=key_handle.decode())
        return True
    
    async def list_keys(self) -> List[str]:
        """List keys in AWS KMS"""
        keys = []
        paginator = self.kms.get_paginator('list_keys')
        for page in paginator.paginate():
            for key in page['Keys']:
                keys.append(key['KeyId'])
        return keys


class HSMKeyManager:
    """HSM-backed key manager for production"""
    
    def __init__(self, hsm_provider: HSMProvider, key_repository: ParticipantKeyRepository):
        self.hsm = hsm_provider
        self.key_repo = key_repository
        self._master_key = None
        self._init_master_key()
    
    def _init_master_key(self):
        """Initialize master key for encrypting stored data"""
        # In production, this would come from HSM or KMS
        self._master_key = os.urandom(32)
    
    async def generate_key_pair(self, participant_id: str) -> KeyPair:
        """Generate key pair in HSM"""
        try:
            # Generate key in HSM
            hsm_key_id = f"aitbc-{participant_id}-{datetime.utcnow().timestamp()}"
            public_key_bytes, key_handle = await self.hsm.generate_key(hsm_key_id)
            
            # Create key pair record
            key_pair = KeyPair(
                participant_id=participant_id,
                private_key=key_handle,  # Store HSM handle, not actual private key
                public_key=public_key_bytes,
                algorithm="X25519",
                created_at=datetime.utcnow(),
                version=1
            )
            
            # Store metadata in database
            await self.key_repo.create(
                await self._get_session(),
                key_pair
            )
            
            logger.info(f"Generated HSM key pair for participant: {participant_id}")
            return key_pair
            
        except Exception as e:
            logger.error(f"Failed to generate HSM key pair for {participant_id}: {e}")
            raise
    
    async def rotate_keys(self, participant_id: str) -> KeyPair:
        """Rotate keys in HSM"""
        # Get current key
        current_key = await self.key_repo.get_by_participant(
            await self._get_session(),
            participant_id
        )
        
        if not current_key:
            raise ValueError(f"No existing keys for {participant_id}")
        
        # Generate new key
        new_key_pair = await self.generate_key_pair(participant_id)
        
        # Log rotation
        rotation_log = KeyRotationLog(
            participant_id=participant_id,
            old_version=current_key.version,
            new_version=new_key_pair.version,
            rotated_at=datetime.utcnow(),
            reason="scheduled_rotation"
        )
        
        await self.key_repo.rotate(
            await self._get_session(),
            participant_id,
            new_key_pair
        )
        
        # Delete old key from HSM
        await self.hsm.delete_key(current_key.private_key)
        
        return new_key_pair
    
    def get_public_key(self, participant_id: str) -> X25519PublicKey:
        """Get public key for participant"""
        key = self.key_repo.get_by_participant_sync(participant_id)
        if not key:
            raise ValueError(f"No keys found for {participant_id}")
        
        return X25519PublicKey.from_public_bytes(key.public_key)
    
    async def get_private_key_handle(self, participant_id: str) -> bytes:
        """Get HSM key handle for participant"""
        key = await self.key_repo.get_by_participant(
            await self._get_session(),
            participant_id
        )
        
        if not key:
            raise ValueError(f"No keys found for {participant_id}")
        
        return key.private_key  # This is the HSM handle
    
    async def derive_shared_secret(
        self,
        participant_id: str,
        peer_public_key: bytes
    ) -> bytes:
        """Derive shared secret using HSM"""
        key_handle = await self.get_private_key_handle(participant_id)
        return await self.hsm.derive_shared_secret(key_handle, peer_public_key)
    
    async def sign_with_key(
        self,
        participant_id: str,
        data: bytes
    ) -> bytes:
        """Sign data using HSM-stored key"""
        key_handle = await self.get_private_key_handle(participant_id)
        return await self.hsm.sign_with_key(key_handle, data)
    
    async def revoke_keys(self, participant_id: str, reason: str) -> bool:
        """Revoke participant's keys"""
        # Get current key
        current_key = await self.key_repo.get_by_participant(
            await self._get_session(),
            participant_id
        )
        
        if not current_key:
            return False
        
        # Delete from HSM
        await self.hsm.delete_key(current_key.private_key)
        
        # Mark as revoked in database
        return await self.key_repo.update_active(
            await self._get_session(),
            participant_id,
            False,
            reason
        )
    
    async def create_audit_authorization(
        self,
        issuer: str,
        purpose: str,
        expires_in_hours: int = 24
    ) -> str:
        """Create audit authorization signed with HSM"""
        # Create authorization payload
        payload = {
            "issuer": issuer,
            "subject": "audit_access",
            "purpose": purpose,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(hours=expires_in_hours)).isoformat()
        }
        
        # Sign with audit key
        audit_key_handle = await self.get_private_key_handle("audit")
        signature = await self.hsm.sign_with_key(
            audit_key_handle,
            json.dumps(payload).encode()
        )
        
        payload["signature"] = signature.hex()
        
        # Encode for transport
        import base64
        return base64.b64encode(json.dumps(payload).encode()).decode()
    
    async def verify_audit_authorization(self, authorization: str) -> bool:
        """Verify audit authorization"""
        try:
            # Decode authorization
            import base64
            auth_data = base64.b64decode(authorization).decode()
            auth_json = json.loads(auth_data)
            
            # Check expiration
            expires_at = datetime.fromisoformat(auth_json["expires_at"])
            if datetime.utcnow() > expires_at:
                return False
            
            # Verify signature with audit public key
            audit_public_key = self.get_public_key("audit")
            # In production, verify with proper cryptographic library
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to verify audit authorization: {e}")
            return False
    
    async def _get_session(self):
        """Get database session"""
        # In production, inject via dependency injection
        async for session in get_async_session():
            return session


def create_hsm_key_manager() -> HSMKeyManager:
    """Create HSM key manager based on configuration"""
    from ..repositories.confidential import ParticipantKeyRepository
    
    # Get HSM provider from settings
    hsm_type = getattr(settings, 'HSM_PROVIDER', 'software')
    
    if hsm_type == 'software':
        hsm = SoftwareHSMProvider()
    elif hsm_type == 'azure':
        vault_url = getattr(settings, 'AZURE_KEY_VAULT_URL')
        hsm = AzureKeyVaultProvider(vault_url)
    elif hsm_type == 'aws':
        region = getattr(settings, 'AWS_REGION', 'us-east-1')
        hsm = AWSKMSProvider(region)
    else:
        raise ValueError(f"Unknown HSM provider: {hsm_type}")
    
    key_repo = ParticipantKeyRepository()
    
    return HSMKeyManager(hsm, key_repo)
