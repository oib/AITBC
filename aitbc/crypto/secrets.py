"""
Secret management with encryption, rotation, and expiration
"""

import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet


def generate_secure_random_string(length: int = 32) -> str:
    """Generate a cryptographically secure random string"""
    return secrets.token_urlsafe(length)


def generate_secure_random_int(min_val: int = 0, max_val: int = 2**32) -> int:
    """Generate a cryptographically secure random integer"""
    return secrets.randbelow(max_val - min_val) + min_val


def generate_nonce(length: int = 16) -> str:
    """Generate a nonce for cryptographic operations"""
    return secrets.token_hex(length)


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
