"""
Key management service for confidential transactions
"""

import asyncio
import base64
import json
import os
from datetime import datetime, timedelta

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey

from ..schemas import KeyPair, KeyRotationLog


class KeyManager:
    """Manages encryption keys for confidential transactions"""

    def __init__(self, storage_backend: "KeyStorageBackend"):
        self.storage = storage_backend
        self.backend = default_backend()
        self._key_cache = {}
        self._audit_key = None
        self._audit_private = None
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
                version=1,
            )

            # Store securely
            await self.storage.store_key_pair(key_pair)

            # Cache public key
            self._key_cache[participant_id] = {"public_key": public_key, "version": key_pair.version}

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
            new_key_pair.version = current_key.version + 1
            # Persist updated version
            await self.storage.store_key_pair(new_key_pair)
            # Update cache
            self._key_cache[participant_id] = {
                "public_key": X25519PublicKey.from_public_bytes(new_key_pair.public_key),
                "version": new_key_pair.version,
            }

            # Log rotation
            rotation_log = KeyRotationLog(
                participant_id=participant_id,
                old_version=current_key.version,
                new_version=new_key_pair.version,
                rotated_at=datetime.utcnow(),
                reason="scheduled_rotation",
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
        self._key_cache[participant_id] = {"public_key": public_key, "version": key_pair.version}

        return public_key

    def get_private_key(self, participant_id: str) -> X25519PrivateKey:
        """Get private key for participant (from secure storage)"""
        key_pair = self.storage.get_key_pair_sync(participant_id)
        if not key_pair:
            raise KeyNotFoundError(f"No keys found for participant: {participant_id}")

        # Reconstruct private key
        private_key = X25519PrivateKey.from_private_bytes(key_pair.private_key)
        return private_key

    def get_audit_key(self) -> X25519PublicKey:
        """Get public audit key for escrow (synchronous for tests)."""
        if not self._audit_key or self._should_rotate_audit_key():
            self._generate_audit_key_in_memory()
        return self._audit_key

    def get_audit_private_key_sync(self, authorization: str) -> X25519PrivateKey:
        """Get private audit key with authorization (sync helper)."""
        if not self.verify_audit_authorization_sync(authorization):
            raise AccessDeniedError("Invalid audit authorization")
        # Ensure audit key exists
        if not self._audit_key or not self._audit_private:
            self._generate_audit_key_in_memory()

        return X25519PrivateKey.from_private_bytes(self._audit_private)

    async def get_audit_private_key(self, authorization: str) -> X25519PrivateKey:
        """Async wrapper for audit private key."""
        return self.get_audit_private_key_sync(authorization)

    def verify_audit_authorization_sync(self, authorization: str) -> bool:
        """Verify audit authorization token (sync helper)."""
        try:
            auth_data = base64.b64decode(authorization).decode()
            auth_json = json.loads(auth_data)

            expires_at = datetime.fromisoformat(auth_json["expires_at"])
            if datetime.utcnow() > expires_at:
                return False

            required_fields = ["issuer", "subject", "expires_at", "signature"]
            return all(field in auth_json for field in required_fields)
        except Exception as e:
            logger.error(f"Failed to verify audit authorization: {e}")
            return False

    async def verify_audit_authorization(self, authorization: str) -> bool:
        """Verify audit authorization token (async API)."""
        return self.verify_audit_authorization_sync(authorization)

    async def create_audit_authorization(self, issuer: str, purpose: str, expires_in_hours: int = 24) -> str:
        """Create audit authorization token"""
        try:
            # Create authorization payload
            payload = {
                "issuer": issuer,
                "subject": "audit_access",
                "purpose": purpose,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(hours=expires_in_hours)).isoformat(),
                "signature": "placeholder",  # In production, sign with issuer key
            }

            # Encode and return
            auth_json = json.dumps(payload)
            return base64.b64encode(auth_json.encode()).decode()

        except Exception as e:
            logger.error(f"Failed to create audit authorization: {e}")
            raise KeyManagementError(f"Authorization creation failed: {e}")

    async def list_participants(self) -> list[str]:
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

    def _generate_audit_key_in_memory(self):
        """Generate and cache an audit key (in-memory for tests/dev)."""
        try:
            audit_private = X25519PrivateKey.generate()
            audit_public = audit_private.public_key()

            self._audit_private = audit_private.private_bytes_raw()

            audit_key_pair = KeyPair(
                participant_id="audit",
                private_key=self._audit_private,
                public_key=audit_public.public_bytes_raw(),
                algorithm="X25519",
                created_at=datetime.utcnow(),
                version=1,
            )

            # Try to persist if backend supports it
            try:
                store = getattr(self.storage, "store_audit_key", None)
                if store:
                    maybe_coro = store(audit_key_pair)
                    if hasattr(maybe_coro, "__await__"):
                        try:
                            loop = asyncio.get_running_loop()
                            if not loop.is_running():
                                loop.run_until_complete(maybe_coro)
                        except RuntimeError:
                            asyncio.run(maybe_coro)
            except Exception:
                pass

            self._audit_key = audit_public
        except Exception as e:
            logger.error(f"Failed to generate audit key: {e}")
            raise KeyManagementError(f"Audit key generation failed: {e}")

    def _should_rotate_audit_key(self) -> bool:
        """Check if audit key needs rotation"""
        # In production, check last rotation time
        return self._audit_key is None

    async def _reencrypt_transactions(self, participant_id: str, old_key_pair: KeyPair, new_key_pair: KeyPair):
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

    async def get_key_pair(self, participant_id: str) -> KeyPair | None:
        """Get key pair for participant"""
        raise NotImplementedError

    def get_key_pair_sync(self, participant_id: str) -> KeyPair | None:
        """Synchronous get key pair"""
        raise NotImplementedError

    async def store_audit_key(self, key_pair: KeyPair) -> bool:
        """Store audit key pair"""
        raise NotImplementedError

    async def get_audit_key(self) -> KeyPair | None:
        """Get audit key pair"""
        raise NotImplementedError

    async def list_participants(self) -> list[str]:
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
                "version": key_pair.version,
            }

            with open(file_path, "w") as f:
                json.dump(metadata, f)

            return True

        except Exception as e:
            logger.error(f"Failed to store key pair: {e}")
            return False

    async def get_key_pair(self, participant_id: str) -> KeyPair | None:
        """Get key pair from file"""
        return self.get_key_pair_sync(participant_id)

    def get_key_pair_sync(self, participant_id: str) -> KeyPair | None:
        """Synchronous get key pair"""
        try:
            file_path = os.path.join(self.storage_path, f"{participant_id}.json")
            private_path = os.path.join(self.storage_path, f"{participant_id}.priv")

            if not os.path.exists(file_path) or not os.path.exists(private_path):
                return None

            # Load metadata
            with open(file_path) as f:
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
                version=metadata["version"],
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
                "version": key_pair.version,
            }

            with open(audit_path, "w") as f:
                json.dump(metadata, f)

            return True

        except Exception as e:
            logger.error(f"Failed to store audit key: {e}")
            return False

    async def get_audit_key(self) -> KeyPair | None:
        """Get audit key"""
        return self.get_key_pair_sync("audit")

    async def list_participants(self) -> list[str]:
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
                f.write(
                    json.dumps(
                        {
                            "participant_id": rotation_log.participant_id,
                            "old_version": rotation_log.old_version,
                            "new_version": rotation_log.new_version,
                            "rotated_at": rotation_log.rotated_at.isoformat(),
                            "reason": rotation_log.reason,
                        }
                    )
                    + "\n"
                )

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


class MockHSMStorage(KeyStorageBackend):
    """Mock HSM storage for development/testing"""
    
    def __init__(self):
        self._keys = {}  # In-memory key storage
        self._audit_key = None
        self._rotation_logs = []
        self._revoked_keys = set()
        self.logger = get_logger("mock_hsm")
    
    async def store_key_pair(self, key_pair: KeyPair) -> bool:
        """Store key pair in mock HSM"""
        try:
            self._keys[key_pair.participant_id] = key_pair
            self.logger.info(f"Stored key pair for {key_pair.participant_id} in mock HSM")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store key pair in mock HSM: {e}")
            return False
    
    async def get_key_pair(self, participant_id: str) -> KeyPair | None:
        """Get key pair from mock HSM"""
        return self._keys.get(participant_id)
    
    def get_key_pair_sync(self, participant_id: str) -> KeyPair | None:
        """Synchronous get key pair"""
        return self._keys.get(participant_id)
    
    async def store_audit_key(self, key_pair: KeyPair) -> bool:
        """Store audit key in mock HSM"""
        try:
            self._audit_key = key_pair
            self.logger.info("Stored audit key in mock HSM")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store audit key in mock HSM: {e}")
            return False
    
    async def get_audit_key(self) -> KeyPair | None:
        """Get audit key from mock HSM"""
        return self._audit_key
    
    async def list_participants(self) -> list[str]:
        """List all participants in mock HSM"""
        return list(self._keys.keys())
    
    async def revoke_keys(self, participant_id: str, reason: str) -> bool:
        """Revoke keys in mock HSM"""
        try:
            if participant_id in self._keys:
                del self._keys[participant_id]
                self._revoked_keys.add(participant_id)
                self.logger.info(f"Revoked keys for {participant_id} in mock HSM: {reason}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to revoke keys in mock HSM: {e}")
            return False
    
    async def log_rotation(self, rotation_log: KeyRotationLog) -> bool:
        """Log key rotation in mock HSM"""
        try:
            self._rotation_logs.append(rotation_log)
            self.logger.info(f"Logged rotation for {rotation_log.participant_id} in mock HSM")
            return True
        except Exception as e:
            self.logger.error(f"Failed to log rotation in mock HSM: {e}")
            return False


class HSMProviderInterface:
    """Mock HSM provider interface for development/testing"""
    
    def __init__(self):
        self._connected = False
        self._stored_keys = {}
        self.logger = get_logger("hsm_provider")
    
    async def connect_to_hsm(self) -> bool:
        """Mock connection to HSM"""
        try:
            self._connected = True
            self.logger.info("Mock HSM connection established")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to mock HSM: {e}")
            return False
    
    async def store_key_in_hsm(self, key_id: str, key_data: bytes) -> bool:
        """Mock store key in HSM"""
        try:
            if not self._connected:
                raise Exception("HSM not connected")
            self._stored_keys[key_id] = key_data
            self.logger.info(f"Stored key {key_id} in mock HSM")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store key in mock HSM: {e}")
            return False
    
    async def retrieve_from_hsm(self, key_id: str) -> bytes | None:
        """Mock retrieve key from HSM"""
        try:
            if not self._connected:
                raise Exception("HSM not connected")
            return self._stored_keys.get(key_id)
        except Exception as e:
            self.logger.error(f"Failed to retrieve key from mock HSM: {e}")
            return None
