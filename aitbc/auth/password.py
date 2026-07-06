"""
Password hashing and verification for AITBC services.

Consolidates:
- ``apps/agent-coordinator/src/app/auth/jwt_handler.py::PasswordManager`` (bcrypt)
- ``aitbc/crypto/password.py`` (PBKDF2HMAC)

Provides both bcrypt (recommended) and PBKDF2 (legacy) options.
"""

from __future__ import annotations

import base64
import secrets
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class PasswordManager:
    """Password hashing and verification using bcrypt.

    This is the recommended password manager. Uses bcrypt for hashing,
    which is the industry standard for password storage.

    All methods return dicts with ``status`` and either the result or error
    message, compatible with the agent-coordinator's original API.
    """

    @staticmethod
    def hash_password(password: str) -> dict[str, Any]:
        """Hash password using bcrypt.

        Returns:
            ``{"status": "success", "hashed_password": ..., "salt": ...}``
            or ``{"status": "error", "message": ...}``
        """
        try:
            import bcrypt  # type: ignore[import-not-found]

            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
            return {"status": "success", "hashed_password": hashed.decode("utf-8"), "salt": salt.decode("utf-8")}
        except Exception as e:
            logger.error("Error hashing password: %s", e)
            return {"status": "error", "message": str(e)}

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> dict[str, Any]:
        """Verify password against bcrypt hash.

        Returns:
            ``{"status": "success", "valid": bool}``
            or ``{"status": "error", "message": ...}``
        """
        try:
            import bcrypt

            hashed_bytes = hashed_password.encode("utf-8")
            password_bytes = password.encode("utf-8")
            is_valid = bcrypt.checkpw(password_bytes, hashed_bytes)
            return {"status": "success", "valid": is_valid}
        except Exception as e:
            logger.error("Error verifying password: %s", e)
            return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# PBKDF2 fallback (legacy, from aitbc/crypto/password.py)
# ---------------------------------------------------------------------------


def hash_password_pbkdf2(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash a password with salt using PBKDF2HMAC.

    This is the legacy PBKDF2-based hashing from ``aitbc/crypto/password.py``.
    Prefer ``PasswordManager.hash_password`` (bcrypt) for new code.

    Args:
        password: Password to hash.
        salt: Optional salt (generated if not provided).

    Returns:
        Tuple of (hashed_password_b64, salt).
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    if salt is None:
        salt = secrets.token_hex(16)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt.encode("utf-8"),
        iterations=100000,
    )
    hashed = kdf.derive(password.encode("utf-8"))
    return base64.b64encode(hashed).decode("utf-8"), salt


def verify_password_pbkdf2(password: str, hashed_password: str, salt: str) -> bool:
    """Verify a password against a PBKDF2 hash.

    Args:
        password: Password to verify.
        hashed_password: Base64-encoded hash.
        salt: Salt used during hashing.

    Returns:
        True if password matches hash.
    """
    new_hash, _ = hash_password_pbkdf2(password, salt)
    return new_hash == hashed_password


# Global instance (agent-coordinator compatibility)
password_manager = PasswordManager()


__all__ = [
    "PasswordManager",
    "hash_password_pbkdf2",
    "password_manager",
    "verify_password_pbkdf2",
]
