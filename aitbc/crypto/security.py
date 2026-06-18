"""
Security utilities for AITBC
Provides token generation, session management, API key management, and secret management
"""

import hashlib
import json
import os
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet


def generate_token(length: int = 32, prefix: str = "") -> str:
    """Generate a secure random token"""
    token = secrets.token_urlsafe(length)
    return f"{prefix}{token}" if prefix else token


def generate_api_key(prefix: str = "aitbc") -> str:
    """Generate a secure API key with prefix"""
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}_{random_part}"


def validate_token_format(token: str, min_length: int = 16) -> bool:
    """Validate token format"""
    return bool(token) and len(token) >= min_length and all(c.isalnum() or c in "-_" for c in token)


def validate_api_key(api_key: str, prefix: str = "aitbc") -> bool:
    """Validate API key format"""
    if not api_key or not api_key.startswith(f"{prefix}_"):
        return False
    token_part = api_key[len(prefix) + 1 :]
    return validate_token_format(token_part)


class SessionManager:
    """Simple in-memory session manager"""

    def __init__(self, session_timeout: int = 3600):
        """Initialize session manager with timeout in seconds"""
        self.sessions: dict[str, dict[str, Any]] = {}
        self.session_timeout = session_timeout

    def create_session(self, user_id: str, data: dict[str, Any] | None = None) -> str:
        """Create a new session"""
        session_id = generate_token()
        self.sessions[session_id] = {
            "user_id": user_id,
            "data": data or {},
            "created_at": time.time(),
            "expires_at": time.time() + self.session_timeout,
        }
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session data"""
        session = self.sessions.get(session_id)
        if not session:
            return None

        # Check if session expired
        if time.time() > session["expires_at"]:
            del self.sessions[session_id]
            return None

        return session

    def update_session(self, session_id: str, data: dict[str, Any]) -> bool:
        """Update session data"""
        session = self.get_session(session_id)
        if not session:
            return False

        session["data"].update(data)
        return True

    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions"""
        current_time = time.time()
        expired_keys = [key for key, session in self.sessions.items() if current_time > session["expires_at"]]

        for key in expired_keys:
            del self.sessions[key]

        return len(expired_keys)


class APIKeyManager:
    """API key management with storage"""

    def __init__(self, storage_path: str | None = None):
        """Initialize API key manager"""
        self.storage_path = storage_path
        self.keys: dict[str, dict[str, Any]] = {}

        if storage_path:
            self._load_keys()

    def create_api_key(self, user_id: str, scopes: list[str] | None = None, name: str | None = None) -> str:
        """Create a new API key"""
        api_key = generate_api_key()
        self.keys[api_key] = {
            "user_id": user_id,
            "scopes": scopes or ["read"],
            "name": name,
            "created_at": datetime.now(UTC).isoformat(),
            "last_used": None,
        }

        if self.storage_path:
            self._save_keys()

        return api_key

    def validate_api_key(self, api_key: str) -> dict[str, Any] | None:
        """Validate API key and return key data"""
        key_data = self.keys.get(api_key)
        if not key_data:
            return None

        # Update last used
        key_data["last_used"] = datetime.now(UTC).isoformat()
        if self.storage_path:
            self._save_keys()

        return key_data

    def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key"""
        if api_key in self.keys:
            del self.keys[api_key]
            if self.storage_path:
                self._save_keys()
            return True
        return False

    def list_user_keys(self, user_id: str) -> list[str]:
        """List all API keys for a user"""
        return [key for key, data in self.items() if data["user_id"] == user_id]

    def _load_keys(self):
        """Load keys from storage"""
        if self.storage_path and os.path.exists(self.storage_path):
            try:
                with open(self.storage_path) as f:
                    self.keys = json.load(f)
            except Exception:
                self.keys = {}

    def _save_keys(self):
        """Save keys to storage"""
        if self.storage_path:
            try:
                with open(self.storage_path, "w") as f:
                    json.dump(self.keys, f)
            except Exception:
                pass

    def items(self):
        """Return key items"""
        return self.keys.items()


def generate_secure_random_string(length: int = 32) -> str:
    """Generate a cryptographically secure random string"""
    return secrets.token_urlsafe(length)


def generate_secure_random_int(min_val: int = 0, max_val: int = 2**32) -> int:
    """Generate a cryptographically secure random integer"""
    return secrets.randbelow(max_val - min_val) + min_val


class SecretManager:
    """Enhanced secret management with encryption, rotation, and expiration"""

    def __init__(self, encryption_key: str | None = None, default_ttl_hours: int = 24):
        """Initialize secret manager

        Args:
            encryption_key: Optional encryption key. If None, generates a new key.
            default_ttl_hours: Default time-to-live for secrets in hours
        """
        if encryption_key:
            self.fernet = Fernet(encryption_key)
        else:
            # Generate a new key if none provided
            self.fernet = Fernet(Fernet.generate_key())

        self.secrets: dict[str, dict[str, Any]] = {}
        self.default_ttl_hours = default_ttl_hours

    def set_secret(self, key: str, value: str, ttl_hours: int | None = None) -> None:
        """Store an encrypted secret with expiration tracking

        Args:
            key: Secret identifier
            value: Secret value to encrypt and store
            ttl_hours: Time-to-live in hours. Uses default if None.
        """
        ttl_hours = ttl_hours or self.default_ttl_hours
        encrypted = self.fernet.encrypt(value.encode("utf-8"))

        self.secrets[key] = {
            "encrypted_value": encrypted.decode("utf-8"),
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(hours=ttl_hours)).isoformat(),
            "version": 1,
            "rotated_at": None,
        }

    def get_secret(self, key: str) -> str | None:
        """Retrieve and decrypt a secret, checking expiration

        Args:
            key: Secret identifier

        Returns:
            Decrypted secret value or None if expired/not found
        """
        secret_data = self.secrets.get(key)
        if not secret_data:
            return None

        # Check expiration
        expires_at = datetime.fromisoformat(secret_data["expires_at"])
        if datetime.now(UTC) > expires_at:
            return None

        try:
            encrypted = secret_data["encrypted_value"]
            decrypted = self.fernet.decrypt(encrypted.encode("utf-8"))
            return decrypted.decode("utf-8")
        except Exception:
            return None

    def rotate_secret(self, key: str, new_value: str, ttl_hours: int | None = None) -> bool:
        """Rotate a secret with version tracking

        Args:
            key: Secret identifier
            new_value: New secret value
            ttl_hours: New time-to-live in hours

        Returns:
            True if rotation successful, False if secret not found
        """
        if key not in self.secrets:
            return False

        old_secret = self.secrets[key]
        ttl_hours = ttl_hours or self.default_ttl_hours

        encrypted = self.fernet.encrypt(new_value.encode("utf-8"))

        self.secrets[key] = {
            "encrypted_value": encrypted.decode("utf-8"),
            "created_at": old_secret["created_at"],  # Keep original creation time
            "expires_at": (datetime.now(UTC) + timedelta(hours=ttl_hours)).isoformat(),
            "version": old_secret["version"] + 1,
            "rotated_at": datetime.now(UTC).isoformat(),
        }

        return True

    def delete_secret(self, key: str) -> bool:
        """Delete a secret"""
        if key in self.secrets:
            del self.secrets[key]
            return True
        return False

    def list_secrets(self, include_expired: bool = False) -> list[str]:
        """List all secret keys

        Args:
            include_expired: Whether to include expired secrets

        Returns:
            List of secret keys
        """
        if include_expired:
            return list(self.secrets.keys())

        # Only return non-expired secrets
        current_time = datetime.now(UTC)
        return [key for key, data in self.secrets.items() if current_time <= datetime.fromisoformat(data["expires_at"])]

    def get_secret_metadata(self, key: str) -> dict[str, Any] | None:
        """Get metadata about a secret without decrypting it

        Args:
            key: Secret identifier

        Returns:
            Secret metadata or None if not found
        """
        secret_data = self.secrets.get(key)
        if not secret_data:
            return None

        return {
            "key": key,
            "created_at": secret_data["created_at"],
            "expires_at": secret_data["expires_at"],
            "version": secret_data["version"],
            "rotated_at": secret_data["rotated_at"],
            "is_expired": datetime.now(UTC) > datetime.fromisoformat(secret_data["expires_at"]),
        }

    def cleanup_expired_secrets(self) -> int:
        """Remove expired secrets from storage

        Returns:
            Number of secrets cleaned up
        """
        current_time = datetime.now(UTC)
        expired_keys = [key for key, data in self.secrets.items() if current_time > datetime.fromisoformat(data["expires_at"])]

        for key in expired_keys:
            del self.secrets[key]

        return len(expired_keys)

    def rotate_encryption_key(self, new_key: str) -> bool:
        """Rotate the master encryption key and re-encrypt all secrets

        Args:
            new_key: New encryption key

        Returns:
            True if rotation successful
        """
        try:
            new_fernet = Fernet(new_key)
            reencrypted_secrets = {}

            for key, data in self.secrets.items():
                # Decrypt with old key
                decrypted = self.fernet.decrypt(data["encrypted_value"].encode("utf-8"))
                # Re-encrypt with new key
                reencrypted = new_fernet.encrypt(decrypted)
                reencrypted_secrets[key] = {
                    **data,
                    "encrypted_value": reencrypted.decode("utf-8"),
                    "rotated_at": datetime.now(UTC).isoformat(),
                }

            self.fernet = new_fernet
            self.secrets = reencrypted_secrets
            return True
        except Exception:
            return False

    def get_encryption_key(self) -> str:
        """Get the encryption key (for backup purposes)"""
        import base64

        return base64.b64encode(self.fernet._signing_key).decode("utf-8")

    def export_secrets(self, include_values: bool = False) -> dict[str, Any]:
        """Export secret metadata for backup/audit

        Args:
            include_values: Whether to include decrypted secret values (use with caution)

        Returns:
            Dictionary of secret metadata
        """
        export_data = {}

        for key, data in self.secrets.items():
            export_data[key] = {
                "created_at": data["created_at"],
                "expires_at": data["expires_at"],
                "version": data["version"],
                "rotated_at": data["rotated_at"],
                "is_expired": datetime.now(UTC) > datetime.fromisoformat(data["expires_at"]),
            }

            if include_values:
                decrypted = self.get_secret(key)
                if decrypted:
                    export_data[key]["value"] = decrypted

        return export_data

    def start_rotation_scheduler(self, check_interval_hours: int = 1) -> None:
        """Start a background thread to periodically clean up expired secrets.

        Args:
            check_interval_hours: How often to check for expired secrets (in hours)
        """
        import threading

        def _rotation_loop():
            import time

            interval_secs = check_interval_hours * 3600
            while True:
                time.sleep(interval_secs)
                cleaned = self.cleanup_expired_secrets()
                if cleaned:
                    from aitbc.security import SecurityAuditor

                    auditor = SecurityAuditor()
                    auditor.log_event(action="secret_rotation_cleanup", details={"cleaned_count": cleaned}, severity="INFO")

        thread = threading.Thread(target=_rotation_loop, daemon=True, name="secret-rotation-scheduler")
        thread.start()


# Global SecretManager singleton
_global_secret_manager: SecretManager | None = None


def get_secret_manager(encryption_key: str | None = None, default_ttl_hours: int = 24) -> SecretManager:
    """Get or create the global SecretManager instance.

    Args:
        encryption_key: Optional encryption key for first-time initialization
        default_ttl_hours: Default secret TTL in hours

    Returns:
        Global SecretManager instance
    """
    global _global_secret_manager
    if _global_secret_manager is None:
        _global_secret_manager = SecretManager(
            encryption_key=encryption_key or os.getenv("AITBC_SECRET_MANAGER_KEY"), default_ttl_hours=default_ttl_hours
        )
        _global_secret_manager.start_rotation_scheduler()
    return _global_secret_manager


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash a password with salt"""
    if salt is None:
        salt = secrets.token_hex(16)

    # Use PBKDF2 for password hashing
    import base64

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt.encode("utf-8"),
        iterations=100000,
    )
    hashed = kdf.derive(password.encode("utf-8"))
    return base64.b64encode(hashed).decode("utf-8"), salt


def verify_password(password: str, hashed_password: str, salt: str) -> bool:
    """Verify a password against a hash"""
    new_hash, _ = hash_password(password, salt)
    return new_hash == hashed_password


def generate_nonce(length: int = 16) -> str:
    """Generate a nonce for cryptographic operations"""
    return secrets.token_hex(length)


def generate_hmac(data: str, secret: str) -> str:
    """Generate HMAC-SHA256 signature"""
    import hmac

    return hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_hmac(data: str, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature"""
    computed = generate_hmac(data, secret)
    return secrets.compare_digest(computed, signature)
