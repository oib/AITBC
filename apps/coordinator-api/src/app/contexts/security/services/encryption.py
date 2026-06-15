"""
Encryption service for confidential transactions
"""

import base64
import json
import os
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from aitbc import get_logger

logger = get_logger(__name__)


class KeyManager:
    pass


class EncryptedData:
    """Container for encrypted data and keys"""

    def __init__(
        self,
        ciphertext: bytes,
        encrypted_keys: dict[str, bytes],
        algorithm: str = "AES-256-GCM+X25519",
        nonce: bytes | None = None,
        tag: bytes | None = None,
    ):
        self.ciphertext = ciphertext
        self.encrypted_keys = encrypted_keys
        self.algorithm = algorithm
        self.nonce = nonce
        self.tag = tag

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "ciphertext": base64.b64encode(self.ciphertext).decode(),
            "encrypted_keys": {
                participant: base64.b64encode(key).decode() for participant, key in self.encrypted_keys.items()
            },
            "algorithm": self.algorithm,
            "nonce": base64.b64encode(self.nonce).decode() if self.nonce else None,
            "tag": base64.b64encode(self.tag).decode() if self.tag else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EncryptedData":
        """Create from dictionary"""
        return cls(
            ciphertext=base64.b64decode(data["ciphertext"]),
            encrypted_keys={participant: base64.b64decode(key) for participant, key in data["encrypted_keys"].items()},
            algorithm=data["algorithm"],
            nonce=base64.b64decode(data["nonce"]) if data.get("nonce") else None,
            tag=base64.b64decode(data["tag"]) if data.get("tag") else None,
        )


class EncryptionService:
    """Service for encrypting/decrypting confidential transaction data"""

    def __init__(self, key_manager: "KeyManager"):
        self.key_manager = key_manager
        self.backend = default_backend()
        self.algorithm = "AES-256-GCM+X25519"

    def encrypt(self, data: dict[str, Any], participants: list[str], include_audit: bool = True) -> EncryptedData:
        """Encrypt data for multiple participants

        Args:
            data: Data to encrypt
            participants: List of participant IDs who can decrypt
            include_audit: Whether to include audit escrow key

        Returns:
            EncryptedData container with ciphertext and encrypted keys
        """
        try:
            if not participants:
                raise EncryptionError("At least one participant is required")
            dek = os.urandom(32)
            nonce = os.urandom(12)
            plaintext = json.dumps(data, separators=(",", ":")).encode()
            aesgcm = AESGCM(dek)
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)
            tag = ciphertext[-16:]
            actual_ciphertext = ciphertext[:-16]
            encrypted_keys = {}
            for participant in participants:
                try:
                    public_key = self.key_manager.get_public_key(participant)  # type: ignore[attr-defined]
                    encrypted_dek = self._encrypt_dek(dek, public_key)
                    encrypted_keys[participant] = encrypted_dek
                except Exception as e:
                    logger.error("Failed to encrypt DEK for participant %s: %s", participant, e)
                    continue
            if include_audit:
                try:
                    audit_public_key = self.key_manager.get_audit_key()  # type: ignore[attr-defined]
                    encrypted_dek = self._encrypt_dek(dek, audit_public_key)
                    encrypted_keys["audit"] = encrypted_dek
                except Exception as e:
                    logger.error("Failed to encrypt DEK for audit: %s", e)
            return EncryptedData(
                ciphertext=actual_ciphertext, encrypted_keys=encrypted_keys, algorithm=self.algorithm, nonce=nonce, tag=tag
            )
        except Exception as e:
            logger.error("Encryption failed: %s", e)
            raise EncryptionError(f"Failed to encrypt data: {e}") from e

    def decrypt(self, encrypted_data: EncryptedData, participant_id: str, purpose: str = "access") -> dict[str, Any]:
        """Decrypt data for a specific participant

        Args:
            encrypted_data: The encrypted data container
            participant_id: ID of the participant requesting decryption
            purpose: Purpose of decryption for audit logging

        Returns:
            Decrypted data as dictionary
        """
        try:
            private_key = self.key_manager.get_private_key(participant_id)  # type: ignore[attr-defined]
            if participant_id not in encrypted_data.encrypted_keys:
                raise AccessDeniedError(f"Participant {participant_id} not authorized")
            encrypted_dek = encrypted_data.encrypted_keys[participant_id]
            dek = self._decrypt_dek(encrypted_dek, private_key)
            full_ciphertext = encrypted_data.ciphertext + encrypted_data.tag  # type: ignore[operator]
            aesgcm = AESGCM(dek)
            plaintext = aesgcm.decrypt(encrypted_data.nonce, full_ciphertext, None)  # type: ignore[arg-type]
            data = json.loads(plaintext.decode())
            self._log_access(transaction_id=None, participant_id=participant_id, purpose=purpose, success=True)
            return data  # type: ignore[no-any-return]
        except Exception as e:
            logger.error("Decryption failed for participant %s: %s", participant_id, e)
            self._log_access(transaction_id=None, participant_id=participant_id, purpose=purpose, success=False, error=str(e))
            raise DecryptionError(f"Failed to decrypt data: {e}") from e

    def audit_decrypt(self, encrypted_data: EncryptedData, audit_authorization: str, purpose: str = "audit") -> dict[str, Any]:
        """Decrypt data for audit purposes

        Args:
            encrypted_data: The encrypted data container
            audit_authorization: Authorization token for audit access
            purpose: Purpose of decryption

        Returns:
            Decrypted data as dictionary
        """
        try:
            auth_ok = self.key_manager.verify_audit_authorization_sync(audit_authorization)  # type: ignore[attr-defined]
            if not auth_ok:
                raise AccessDeniedError("Invalid audit authorization")
            audit_private_key = self.key_manager.get_audit_private_key_sync(audit_authorization)  # type: ignore[attr-defined]
            if "audit" not in encrypted_data.encrypted_keys:
                raise AccessDeniedError("Audit escrow not available")
            encrypted_dek = encrypted_data.encrypted_keys["audit"]
            dek = self._decrypt_dek(encrypted_dek, audit_private_key)
            full_ciphertext = encrypted_data.ciphertext + encrypted_data.tag  # type: ignore[operator]
            aesgcm = AESGCM(dek)
            plaintext = aesgcm.decrypt(encrypted_data.nonce, full_ciphertext, None)  # type: ignore[arg-type]
            data = json.loads(plaintext.decode())
            self._log_access(
                transaction_id=None,
                participant_id="audit",
                purpose=f"audit:{purpose}",
                success=True,
                authorization=audit_authorization,
            )
            return data  # type: ignore[no-any-return]
        except Exception as e:
            logger.error("Audit decryption failed: %s", e)
            raise DecryptionError(f"Failed to decrypt for audit: {e}") from e

    def _encrypt_dek(self, dek: bytes, public_key: X25519PublicKey) -> bytes:
        """Encrypt DEK using ECIES with X25519"""
        ephemeral_private = X25519PrivateKey.generate()
        ephemeral_public = ephemeral_private.public_key()
        shared_key = ephemeral_private.exchange(public_key)
        derived_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=b"AITBC-DEK-Encryption", backend=self.backend
        ).derive(shared_key)
        aesgcm = AESGCM(derived_key)
        nonce = os.urandom(12)
        encrypted_dek = aesgcm.encrypt(nonce, dek, None)
        return ephemeral_public.public_bytes(Encoding.Raw, PublicFormat.Raw) + nonce + encrypted_dek

    def _decrypt_dek(self, encrypted_dek: bytes, private_key: X25519PrivateKey) -> bytes:
        """Decrypt DEK using ECIES with X25519"""
        ephemeral_public_bytes = encrypted_dek[:32]
        nonce = encrypted_dek[32:44]
        dek_ciphertext = encrypted_dek[44:]
        ephemeral_public = X25519PublicKey.from_public_bytes(ephemeral_public_bytes)
        shared_key = private_key.exchange(ephemeral_public)
        derived_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=b"AITBC-DEK-Encryption", backend=self.backend
        ).derive(shared_key)
        aesgcm = AESGCM(derived_key)
        dek = aesgcm.decrypt(nonce, dek_ciphertext, None)
        return dek

    def _log_access(
        self,
        transaction_id: str | None,
        participant_id: str,
        purpose: str,
        success: bool,
        error: str | None = None,
        authorization: str | None = None,
    ) -> None:
        """Log access to confidential data"""
        try:
            log_entry = {
                "transaction_id": transaction_id,
                "participant_id": participant_id,
                "purpose": purpose,
                "timestamp": datetime.now(UTC).isoformat(),
                "success": success,
                "error": error,
                "authorization": authorization,
            }
            logger.info("Confidential data access: %s", json.dumps(log_entry))
        except Exception as e:
            logger.error("Failed to log access: %s", e)


class EncryptionError(Exception):
    """Base exception for encryption errors"""

    pass


class DecryptionError(EncryptionError):
    """Exception for decryption errors"""

    pass


class AccessDeniedError(EncryptionError):
    """Exception for access denied errors"""

    pass
