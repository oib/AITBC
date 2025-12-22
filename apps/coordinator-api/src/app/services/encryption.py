"""
Encryption service for confidential transactions
"""

import os
import json
import base64
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption

from ..models import ConfidentialTransaction, AccessLog
from ..settings import settings
from ..logging import get_logger

logger = get_logger(__name__)


class EncryptedData:
    """Container for encrypted data and keys"""
    
    def __init__(
        self,
        ciphertext: bytes,
        encrypted_keys: Dict[str, bytes],
        algorithm: str = "AES-256-GCM+X25519",
        nonce: Optional[bytes] = None,
        tag: Optional[bytes] = None
    ):
        self.ciphertext = ciphertext
        self.encrypted_keys = encrypted_keys
        self.algorithm = algorithm
        self.nonce = nonce
        self.tag = tag
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "ciphertext": base64.b64encode(self.ciphertext).decode(),
            "encrypted_keys": {
                participant: base64.b64encode(key).decode()
                for participant, key in self.encrypted_keys.items()
            },
            "algorithm": self.algorithm,
            "nonce": base64.b64encode(self.nonce).decode() if self.nonce else None,
            "tag": base64.b64encode(self.tag).decode() if self.tag else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EncryptedData":
        """Create from dictionary"""
        return cls(
            ciphertext=base64.b64decode(data["ciphertext"]),
            encrypted_keys={
                participant: base64.b64decode(key)
                for participant, key in data["encrypted_keys"].items()
            },
            algorithm=data["algorithm"],
            nonce=base64.b64decode(data["nonce"]) if data.get("nonce") else None,
            tag=base64.b64decode(data["tag"]) if data.get("tag") else None
        )


class EncryptionService:
    """Service for encrypting/decrypting confidential transaction data"""
    
    def __init__(self, key_manager: "KeyManager"):
        self.key_manager = key_manager
        self.backend = default_backend()
        self.algorithm = "AES-256-GCM+X25519"
    
    def encrypt(
        self,
        data: Dict[str, Any],
        participants: List[str],
        include_audit: bool = True
    ) -> EncryptedData:
        """Encrypt data for multiple participants
        
        Args:
            data: Data to encrypt
            participants: List of participant IDs who can decrypt
            include_audit: Whether to include audit escrow key
            
        Returns:
            EncryptedData container with ciphertext and encrypted keys
        """
        try:
            # Generate random DEK (Data Encryption Key)
            dek = os.urandom(32)  # 256-bit key for AES-256
            nonce = os.urandom(12)  # 96-bit nonce for GCM
            
            # Serialize and encrypt data
            plaintext = json.dumps(data, separators=(",", ":")).encode()
            aesgcm = AESGCM(dek)
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)
            
            # Extract tag (included in ciphertext for GCM)
            tag = ciphertext[-16:]
            actual_ciphertext = ciphertext[:-16]
            
            # Encrypt DEK for each participant
            encrypted_keys = {}
            for participant in participants:
                try:
                    public_key = self.key_manager.get_public_key(participant)
                    encrypted_dek = self._encrypt_dek(dek, public_key)
                    encrypted_keys[participant] = encrypted_dek
                except Exception as e:
                    logger.error(f"Failed to encrypt DEK for participant {participant}: {e}")
                    continue
            
            # Add audit escrow if requested
            if include_audit:
                try:
                    audit_public_key = self.key_manager.get_audit_key()
                    encrypted_dek = self._encrypt_dek(dek, audit_public_key)
                    encrypted_keys["audit"] = encrypted_dek
                except Exception as e:
                    logger.error(f"Failed to encrypt DEK for audit: {e}")
            
            return EncryptedData(
                ciphertext=actual_ciphertext,
                encrypted_keys=encrypted_keys,
                algorithm=self.algorithm,
                nonce=nonce,
                tag=tag
            )
            
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Failed to encrypt data: {e}")
    
    def decrypt(
        self,
        encrypted_data: EncryptedData,
        participant_id: str,
        purpose: str = "access"
    ) -> Dict[str, Any]:
        """Decrypt data for a specific participant
        
        Args:
            encrypted_data: The encrypted data container
            participant_id: ID of the participant requesting decryption
            purpose: Purpose of decryption for audit logging
            
        Returns:
            Decrypted data as dictionary
        """
        try:
            # Get participant's private key
            private_key = self.key_manager.get_private_key(participant_id)
            
            # Get encrypted DEK for participant
            if participant_id not in encrypted_data.encrypted_keys:
                raise AccessDeniedError(f"Participant {participant_id} not authorized")
            
            encrypted_dek = encrypted_data.encrypted_keys[participant_id]
            
            # Decrypt DEK
            dek = self._decrypt_dek(encrypted_dek, private_key)
            
            # Reconstruct ciphertext with tag
            full_ciphertext = encrypted_data.ciphertext + encrypted_data.tag
            
            # Decrypt data
            aesgcm = AESGCM(dek)
            plaintext = aesgcm.decrypt(encrypted_data.nonce, full_ciphertext, None)
            
            data = json.loads(plaintext.decode())
            
            # Log access
            self._log_access(
                transaction_id=None,  # Will be set by caller
                participant_id=participant_id,
                purpose=purpose,
                success=True
            )
            
            return data
            
        except Exception as e:
            logger.error(f"Decryption failed for participant {participant_id}: {e}")
            self._log_access(
                transaction_id=None,
                participant_id=participant_id,
                purpose=purpose,
                success=False,
                error=str(e)
            )
            raise DecryptionError(f"Failed to decrypt data: {e}")
    
    def audit_decrypt(
        self,
        encrypted_data: EncryptedData,
        audit_authorization: str,
        purpose: str = "audit"
    ) -> Dict[str, Any]:
        """Decrypt data for audit purposes
        
        Args:
            encrypted_data: The encrypted data container
            audit_authorization: Authorization token for audit access
            purpose: Purpose of decryption
            
        Returns:
            Decrypted data as dictionary
        """
        try:
            # Verify audit authorization
            if not self.key_manager.verify_audit_authorization(audit_authorization):
                raise AccessDeniedError("Invalid audit authorization")
            
            # Get audit private key
            audit_private_key = self.key_manager.get_audit_private_key(audit_authorization)
            
            # Decrypt using audit key
            if "audit" not in encrypted_data.encrypted_keys:
                raise AccessDeniedError("Audit escrow not available")
            
            encrypted_dek = encrypted_data.encrypted_keys["audit"]
            dek = self._decrypt_dek(encrypted_dek, audit_private_key)
            
            # Decrypt data
            full_ciphertext = encrypted_data.ciphertext + encrypted_data.tag
            aesgcm = AESGCM(dek)
            plaintext = aesgcm.decrypt(encrypted_data.nonce, full_ciphertext, None)
            
            data = json.loads(plaintext.decode())
            
            # Log audit access
            self._log_access(
                transaction_id=None,
                participant_id="audit",
                purpose=f"audit:{purpose}",
                success=True,
                authorization=audit_authorization
            )
            
            return data
            
        except Exception as e:
            logger.error(f"Audit decryption failed: {e}")
            raise DecryptionError(f"Failed to decrypt for audit: {e}")
    
    def _encrypt_dek(self, dek: bytes, public_key: X25519PublicKey) -> bytes:
        """Encrypt DEK using ECIES with X25519"""
        # Generate ephemeral key pair
        ephemeral_private = X25519PrivateKey.generate()
        ephemeral_public = ephemeral_private.public_key()
        
        # Perform ECDH
        shared_key = ephemeral_private.exchange(public_key)
        
        # Derive encryption key from shared secret
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"AITBC-DEK-Encryption",
            backend=self.backend
        ).derive(shared_key)
        
        # Encrypt DEK with AES-GCM
        aesgcm = AESGCM(derived_key)
        nonce = os.urandom(12)
        encrypted_dek = aesgcm.encrypt(nonce, dek, None)
        
        # Return ephemeral public key + nonce + encrypted DEK
        return (
            ephemeral_public.public_bytes(Encoding.Raw, PublicFormat.Raw) +
            nonce +
            encrypted_dek
        )
    
    def _decrypt_dek(self, encrypted_dek: bytes, private_key: X25519PrivateKey) -> bytes:
        """Decrypt DEK using ECIES with X25519"""
        # Extract components
        ephemeral_public_bytes = encrypted_dek[:32]
        nonce = encrypted_dek[32:44]
        dek_ciphertext = encrypted_dek[44:]
        
        # Reconstruct ephemeral public key
        ephemeral_public = X25519PublicKey.from_public_bytes(ephemeral_public_bytes)
        
        # Perform ECDH
        shared_key = private_key.exchange(ephemeral_public)
        
        # Derive decryption key
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"AITBC-DEK-Encryption",
            backend=self.backend
        ).derive(shared_key)
        
        # Decrypt DEK
        aesgcm = AESGCM(derived_key)
        dek = aesgcm.decrypt(nonce, dek_ciphertext, None)
        
        return dek
    
    def _log_access(
        self,
        transaction_id: Optional[str],
        participant_id: str,
        purpose: str,
        success: bool,
        error: Optional[str] = None,
        authorization: Optional[str] = None
    ):
        """Log access to confidential data"""
        try:
            log_entry = {
                "transaction_id": transaction_id,
                "participant_id": participant_id,
                "purpose": purpose,
                "timestamp": datetime.utcnow().isoformat(),
                "success": success,
                "error": error,
                "authorization": authorization
            }
            
            # In production, this would go to secure audit log
            logger.info(f"Confidential data access: {json.dumps(log_entry)}")
            
        except Exception as e:
            logger.error(f"Failed to log access: {e}")


class EncryptionError(Exception):
    """Base exception for encryption errors"""
    pass


class DecryptionError(EncryptionError):
    """Exception for decryption errors"""
    pass


class AccessDeniedError(EncryptionError):
    """Exception for access denied errors"""
    pass
