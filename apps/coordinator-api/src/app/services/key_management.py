"""
Key management service for confidential transactions
"""

import os
import json
import base64
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..models import KeyPair, KeyRotationLog, AuditAuthorization
from ..settings import settings
from ..logging import get_logger

logger = get_logger(__name__)


class KeyManager:
    """Manages encryption keys for confidential transactions"""
    
    def __init__(self, storage_backend: "KeyStorageBackend"):
        self.storage = storage_backend
        self.backend = default_backend()
        self._key_cache = {}
        self._audit_key = None
        self._audit_key_rotation = timedelta(days=30)
    
    async def generate_key_pair(self, participant_id: str) -> KeyPair:
        """Generate X25519 key pair for participant"""
        try:
            # Generate new key pair
            private_key = X25519PrivateKey.generate()
            public_key = private_key.public_key()
            
            # Create key pair object
            key_pair = KeyPair(
                participant_id=participant_id,
                private_key=private_key.private_bytes_raw(),
                public_key=public_key.public_bytes_raw(),
                algorithm="X25519",
                created_at=datetime.utcnow(),
                version=1
            )
            
            # Store securely
            await self.storage.store_key_pair(key_pair)
            
            # Cache public key
            self._key_cache[participant_id] = {
                "public_key": public_key,
                "version": key_pair.version
            }
            
            logger.info(f"Generated key pair for participant: {participant_id}")
            return key_pair
            
        except Exception as e:
            logger.error(f"Failed to generate key pair for {participant_id}: {e}")
            raise KeyManagementError(f"Key generation failed: {e}")
    
    async def rotate_keys(self, participant_id: str) -> KeyPair:
        """Rotate encryption keys for participant"""
        try:
            # Get current key pair
            current_key = await self.storage.get_key_pair(participant_id)
            if not current_key:
                raise KeyNotFoundError(f"No existing keys for {participant_id}")
            
            # Generate new key pair
            new_key_pair = await self.generate_key_pair(participant_id)
            
            # Log rotation
            rotation_log = KeyRotationLog(
                participant_id=participant_id,
                old_version=current_key.version,
                new_version=new_key_pair.version,
                rotated_at=datetime.utcnow(),
                reason="scheduled_rotation"
            )
            await self.storage.log_rotation(rotation_log)
            
            # Re-encrypt active transactions (in production)
            await self._reencrypt_transactions(participant_id, current_key, new_key_pair)
            
            logger.info(f"Rotated keys for participant: {participant_id}")
            return new_key_pair
            
        except Exception as e:
            logger.error(f"Failed to rotate keys for {participant_id}: {e}")
            raise KeyManagementError(f"Key rotation failed: {e}")
    
    def get_public_key(self, participant_id: str) -> X25519PublicKey:
        """Get public key for participant"""
        # Check cache first
        if participant_id in self._key_cache:
            return self._key_cache[participant_id]["public_key"]
        
        # Load from storage
        key_pair = self.storage.get_key_pair_sync(participant_id)
        if not key_pair:
            raise KeyNotFoundError(f"No keys found for participant: {participant_id}")
        
        # Reconstruct public key
        public_key = X25519PublicKey.from_public_bytes(key_pair.public_key)
        
        # Cache it
        self._key_cache[participant_id] = {
            "public_key": public_key,
            "version": key_pair.version
        }
        
        return public_key
    
    def get_private_key(self, participant_id: str) -> X25519PrivateKey:
        """Get private key for participant (from secure storage)"""
        key_pair = self.storage.get_key_pair_sync(participant_id)
        if not key_pair:
            raise KeyNotFoundError(f"No keys found for participant: {participant_id}")
        
        # Reconstruct private key
        private_key = X25519PrivateKey.from_private_bytes(key_pair.private_key)
        return private_key
    
    async def get_audit_key(self) -> X25519PublicKey:
        """Get public audit key for escrow"""
        if not self._audit_key or self._should_rotate_audit_key():
            await self._rotate_audit_key()
        
        return self._audit_key
    
    async def get_audit_private_key(self, authorization: str) -> X25519PrivateKey:
        """Get private audit key with authorization"""
        # Verify authorization
        if not await self.verify_audit_authorization(authorization):
            raise AccessDeniedError("Invalid audit authorization")
        
        # Load audit key from secure storage
        audit_key_data = await self.storage.get_audit_key()
        if not audit_key_data:
            raise KeyNotFoundError("Audit key not found")
        
        return X25519PrivateKey.from_private_bytes(audit_key_data.private_key)
    
    async def verify_audit_authorization(self, authorization: str) -> bool:
        """Verify audit authorization token"""
        try:
            # Decode authorization
            auth_data = base64.b64decode(authorization).decode()
            auth_json = json.loads(auth_data)
            
            # Check expiration
            expires_at = datetime.fromisoformat(auth_json["expires_at"])
            if datetime.utcnow() > expires_at:
                return False
            
            # Verify signature (in production, use proper signature verification)
            # For now, just check format
            required_fields = ["issuer", "subject", "expires_at", "signature"]
            return all(field in auth_json for field in required_fields)
            
        except Exception as e:
            logger.error(f"Failed to verify audit authorization: {e}")
            return False
    
    async def create_audit_authorization(
        self,
        issuer: str,
        purpose: str,
        expires_in_hours: int = 24
    ) -> str:
        """Create audit authorization token"""
        try:
            # Create authorization payload
            payload = {
                "issuer": issuer,
                "subject": "audit_access",
                "purpose": purpose,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(hours=expires_in_hours)).isoformat(),
                "signature": "placeholder"  # In production, sign with issuer key
            }
            
            # Encode and return
            auth_json = json.dumps(payload)
            return base64.b64encode(auth_json.encode()).decode()
            
        except Exception as e:
            logger.error(f"Failed to create audit authorization: {e}")
            raise KeyManagementError(f"Authorization creation failed: {e}")
    
    async def list_participants(self) -> List[str]:
        """List all participants with keys"""
        return await self.storage.list_participants()
    
    async def revoke_keys(self, participant_id: str, reason: str) -> bool:
        """Revoke participant's keys"""
        try:
            # Mark keys as revoked
            success = await self.storage.revoke_keys(participant_id, reason)
            
            if success:
                # Clear cache
                if participant_id in self._key_cache:
                    del self._key_cache[participant_id]
                
                logger.info(f"Revoked keys for participant: {participant_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to revoke keys for {participant_id}: {e}")
            return False
    
    async def _rotate_audit_key(self):
        """Rotate the audit escrow key"""
        try:
            # Generate new audit key pair
            audit_private = X25519PrivateKey.generate()
            audit_public = audit_private.public_key()
            
            # Store securely
            audit_key_pair = KeyPair(
                participant_id="audit",
                private_key=audit_private.private_bytes_raw(),
                public_key=audit_public.public_bytes_raw(),
                algorithm="X25519",
                created_at=datetime.utcnow(),
                version=1
            )
            
            await self.storage.store_audit_key(audit_key_pair)
            self._audit_key = audit_public
            
            logger.info("Rotated audit escrow key")
            
        except Exception as e:
            logger.error(f"Failed to rotate audit key: {e}")
            raise KeyManagementError(f"Audit key rotation failed: {e}")
    
    def _should_rotate_audit_key(self) -> bool:
        """Check if audit key needs rotation"""
        # In production, check last rotation time
        return self._audit_key is None
    
    async def _reencrypt_transactions(
        self,
        participant_id: str,
        old_key_pair: KeyPair,
        new_key_pair: KeyPair
    ):
        """Re-encrypt active transactions with new key"""
        # This would be implemented in production
        # For now, just log the action
        logger.info(f"Would re-encrypt transactions for {participant_id}")
        pass


class KeyStorageBackend:
    """Abstract base for key storage backends"""
    
    async def store_key_pair(self, key_pair: KeyPair) -> bool:
        """Store key pair securely"""
        raise NotImplementedError
    
    async def get_key_pair(self, participant_id: str) -> Optional[KeyPair]:
        """Get key pair for participant"""
        raise NotImplementedError
    
    def get_key_pair_sync(self, participant_id: str) -> Optional[KeyPair]:
        """Synchronous get key pair"""
        raise NotImplementedError
    
    async def store_audit_key(self, key_pair: KeyPair) -> bool:
        """Store audit key pair"""
        raise NotImplementedError
    
    async def get_audit_key(self) -> Optional[KeyPair]:
        """Get audit key pair"""
        raise NotImplementedError
    
    async def list_participants(self) -> List[str]:
        """List all participants"""
        raise NotImplementedError
    
    async def revoke_keys(self, participant_id: str, reason: str) -> bool:
        """Revoke keys for participant"""
        raise NotImplementedError
    
    async def log_rotation(self, rotation_log: KeyRotationLog) -> bool:
        """Log key rotation"""
        raise NotImplementedError


class FileKeyStorage(KeyStorageBackend):
    """File-based key storage for development"""
    
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
    
    async def store_key_pair(self, key_pair: KeyPair) -> bool:
        """Store key pair to file"""
        try:
            file_path = os.path.join(self.storage_path, f"{key_pair.participant_id}.json")
            
            # Store private key in separate encrypted file
            private_path = os.path.join(self.storage_path, f"{key_pair.participant_id}.priv")
            
            # In production, encrypt private key with master key
            with open(private_path, "wb") as f:
                f.write(key_pair.private_key)
            
            # Store public metadata
            metadata = {
                "participant_id": key_pair.participant_id,
                "public_key": base64.b64encode(key_pair.public_key).decode(),
                "algorithm": key_pair.algorithm,
                "created_at": key_pair.created_at.isoformat(),
                "version": key_pair.version
            }
            
            with open(file_path, "w") as f:
                json.dump(metadata, f)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store key pair: {e}")
            return False
    
    async def get_key_pair(self, participant_id: str) -> Optional[KeyPair]:
        """Get key pair from file"""
        return self.get_key_pair_sync(participant_id)
    
    def get_key_pair_sync(self, participant_id: str) -> Optional[KeyPair]:
        """Synchronous get key pair"""
        try:
            file_path = os.path.join(self.storage_path, f"{participant_id}.json")
            private_path = os.path.join(self.storage_path, f"{participant_id}.priv")
            
            if not os.path.exists(file_path) or not os.path.exists(private_path):
                return None
            
            # Load metadata
            with open(file_path, "r") as f:
                metadata = json.load(f)
            
            # Load private key
            with open(private_path, "rb") as f:
                private_key = f.read()
            
            return KeyPair(
                participant_id=metadata["participant_id"],
                private_key=private_key,
                public_key=base64.b64decode(metadata["public_key"]),
                algorithm=metadata["algorithm"],
                created_at=datetime.fromisoformat(metadata["created_at"]),
                version=metadata["version"]
            )
            
        except Exception as e:
            logger.error(f"Failed to get key pair: {e}")
            return None
    
    async def store_audit_key(self, key_pair: KeyPair) -> bool:
        """Store audit key"""
        audit_path = os.path.join(self.storage_path, "audit.json")
        audit_priv_path = os.path.join(self.storage_path, "audit.priv")
        
        try:
            # Store private key
            with open(audit_priv_path, "wb") as f:
                f.write(key_pair.private_key)
            
            # Store metadata
            metadata = {
                "participant_id": "audit",
                "public_key": base64.b64encode(key_pair.public_key).decode(),
                "algorithm": key_pair.algorithm,
                "created_at": key_pair.created_at.isoformat(),
                "version": key_pair.version
            }
            
            with open(audit_path, "w") as f:
                json.dump(metadata, f)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store audit key: {e}")
            return False
    
    async def get_audit_key(self) -> Optional[KeyPair]:
        """Get audit key"""
        return self.get_key_pair_sync("audit")
    
    async def list_participants(self) -> List[str]:
        """List all participants"""
        participants = []
        for file in os.listdir(self.storage_path):
            if file.endswith(".json") and file != "audit.json":
                participant_id = file[:-5]  # Remove .json
                participants.append(participant_id)
        return participants
    
    async def revoke_keys(self, participant_id: str, reason: str) -> bool:
        """Revoke keys by deleting files"""
        try:
            file_path = os.path.join(self.storage_path, f"{participant_id}.json")
            private_path = os.path.join(self.storage_path, f"{participant_id}.priv")
            
            # Move to revoked folder instead of deleting
            revoked_path = os.path.join(self.storage_path, "revoked")
            os.makedirs(revoked_path, exist_ok=True)
            
            if os.path.exists(file_path):
                os.rename(file_path, os.path.join(revoked_path, f"{participant_id}.json"))
            if os.path.exists(private_path):
                os.rename(private_path, os.path.join(revoked_path, f"{participant_id}.priv"))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to revoke keys: {e}")
            return False
    
    async def log_rotation(self, rotation_log: KeyRotationLog) -> bool:
        """Log key rotation"""
        log_path = os.path.join(self.storage_path, "rotations.log")
        
        try:
            with open(log_path, "a") as f:
                f.write(json.dumps({
                    "participant_id": rotation_log.participant_id,
                    "old_version": rotation_log.old_version,
                    "new_version": rotation_log.new_version,
                    "rotated_at": rotation_log.rotated_at.isoformat(),
                    "reason": rotation_log.reason
                }) + "\n")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to log rotation: {e}")
            return False


class KeyManagementError(Exception):
    """Base exception for key management errors"""
    pass


class KeyNotFoundError(KeyManagementError):
    """Raised when key is not found"""
    pass


class AccessDeniedError(KeyManagementError):
    """Raised when access is denied"""
    pass
