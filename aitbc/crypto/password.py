"""
Password hashing and validation utilities
"""

import base64
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash a password with salt"""
    if salt is None:
        salt = secrets.token_hex(16)

    # Use PBKDF2 for password hashing
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
