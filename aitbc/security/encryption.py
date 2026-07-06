"""Encryption utilities for AITBC services (v0.10.7 §B6).

Provides PBKDF2 + Fernet encryption for sensitive data (wallet keys, etc.).
Consolidated from ``cli/utils/security.py`` and ``apps/coordinator-api/.../wallet_crypto.py``.
"""

import base64
import secrets
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def derive_secure_key(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive secure encryption key using PBKDF2 with SHA-256.

    Args:
        password: User password (required - no defaults)
        salt: Optional salt (generated if not provided)

    Returns:
        Tuple of (fernet_key, salt)

    Raises:
        ValueError: If password is empty or too weak
    """
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")

    if salt is None:
        salt = secrets.token_bytes(32)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,  # OWASP recommended minimum
    )

    key = kdf.derive(password.encode())
    fernet_key = base64.urlsafe_b64encode(key)

    return fernet_key, salt


def encrypt_value(value: str, password: str) -> dict[str, Any]:
    """Encrypt a value using PBKDF2 + Fernet.

    Args:
        value: Value to encrypt
        password: Strong password (required)

    Returns:
        Dict with encrypted data and metadata

    Raises:
        ValueError: If password is too weak
    """
    if not value:
        raise ValueError("Cannot encrypt empty value")

    fernet_key, salt = derive_secure_key(password)

    f = Fernet(fernet_key)
    encrypted = f.encrypt(value.encode())

    return {
        "encrypted_data": encrypted.decode(),
        "salt": base64.b64encode(salt).decode(),
        "algorithm": "PBKDF2-SHA256-Fernet",
        "iterations": 600_000,
        "version": "1.0",
    }


def decrypt_value(encrypted_data: dict[str, str] | str, password: str) -> str:
    """Decrypt a PBKDF2 + Fernet encrypted value.

    Args:
        encrypted_data: Dict with encrypted data or legacy string
        password: Password used for encryption

    Returns:
        Decrypted value

    Raises:
        ValueError: If decryption fails or password is wrong
        InvalidToken: If the encrypted data is corrupted
    """
    if isinstance(encrypted_data, str):
        raise ValueError(
            "Legacy encrypted format detected. "
            "This data was encrypted with a broken implementation and cannot be securely recovered. "
            "Please recreate the wallet with proper encryption."
        )

    try:
        salt = base64.b64decode(encrypted_data["salt"])
        encrypted = encrypted_data["encrypted_data"].encode()

        fernet_key, _ = derive_secure_key(password, salt)

        f = Fernet(fernet_key)
        decrypted = f.decrypt(encrypted)

        return decrypted.decode()
    except InvalidToken:
        raise ValueError("Invalid password or corrupted encrypted data") from None
    except Exception as e:
        raise ValueError(f"Decryption failed: {str(e)}") from e


def validate_password_strength(password: str) -> dict[str, Any]:
    """Validate password strength.

    Args:
        password: Password to validate

    Returns:
        Dict with validation results (score, strength, issues, is_acceptable)
    """
    issues = []
    score = 0

    if len(password) < 8:
        issues.append("Password must be at least 8 characters")
    else:
        score += 1

    if len(password) < 12:
        issues.append("Consider using 12+ characters for better security")
    else:
        score += 1

    if not any(c.isupper() for c in password):
        issues.append("Include uppercase letters")
    else:
        score += 1

    if not any(c.islower() for c in password):
        issues.append("Include lowercase letters")
    else:
        score += 1

    if not any(c.isdigit() for c in password):
        issues.append("Include numbers")
    else:
        score += 1

    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        issues.append("Include special characters")
    else:
        score += 1

    if password.lower() in ["password", "123456", "qwerty", "admin"]:
        issues.append("Avoid common passwords")
        score = 0

    strength_levels = {0: "Very Weak", 1: "Weak", 2: "Fair", 3: "Good", 4: "Strong", 5: "Very Strong", 6: "Excellent"}

    return {"score": score, "strength": strength_levels.get(score, "Unknown"), "issues": issues, "is_acceptable": score >= 3}


def generate_secure_password(length: int = 16) -> str:
    """Generate a secure random password.

    Args:
        length: Password length

    Returns:
        Secure random password
    """
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{}|;:,.<>?"

    password = "".join(secrets.choice(alphabet) for _ in range(length))

    while not validate_password_strength(password)["is_acceptable"]:
        password = "".join(secrets.choice(alphabet) for _ in range(length))

    return password


def migrate_legacy_wallet(legacy_data: dict[str, Any], new_password: str) -> dict[str, Any]:
    """Migrate a wallet from broken encryption to secure encryption.

    Args:
        legacy_data: Legacy wallet data with broken encryption
        new_password: New strong password

    Returns:
        Migrated wallet data

    Raises:
        ValueError: If migration cannot be performed safely
    """
    if "encrypted" not in legacy_data or not legacy_data.get("encrypted"):
        raise ValueError("Not a legacy encrypted wallet")

    if "private_key" not in legacy_data:
        raise ValueError("Cannot migrate wallet without private key")

    private_key = legacy_data["private_key"]

    if private_key.startswith("[ENCRYPTED_MOCK]") or private_key.startswith("["):
        raise ValueError("Cannot migrate mock wallet. Please create a new wallet with proper key generation.")

    try:
        encrypted_data = encrypt_value(private_key, new_password)

        return {
            **legacy_data,
            "private_key": encrypted_data,
            "encryption_version": "1.0",
            "migration_timestamp": secrets.token_hex(16),
        }
    except Exception as e:
        raise ValueError(f"Migration failed: {str(e)}") from e


def validate_password_rules(password: str) -> None:
    """Validate password meets minimum security rules.

    Raises ValueError if the password does not meet the rules:
    - At least 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one symbol
    """
    import re

    if len(password) < 12:
        raise ValueError("password must be at least 12 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("password must include at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("password must include at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("password must include at least one digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("password must include at least one symbol")


def wipe_buffer(buffer: bytearray) -> None:
    """Securely wipe a bytearray by zeroing all bytes."""
    for index in range(len(buffer)):
        buffer[index] = 0


class EncryptionConfig:
    """Encryption configuration constants"""

    PBKDF2_ITERATIONS = 600_000
    SALT_LENGTH = 32
    MIN_PASSWORD_LENGTH = 8
    RECOMMENDED_PASSWORD_LENGTH = 16

    ALGORITHM_PBKDF2_FERNET = "PBKDF2-SHA256-Fernet"
    ALGORITHM_LEGACY = "LEGACY-BROKEN"

    CURRENT_VERSION = "1.0"
    LEGACY_VERSIONS = ["0.9", "legacy", "broken"]
