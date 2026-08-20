"""AITBC encryption helpers."""

import base64
import hashlib
import json
import os
from typing import Any


def encrypt_value(value: str, password: str) -> dict[str, Any]:
    """Stub PBKDF2 + base64 encryption for wallet files."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000, dklen=32)
    return {
        "encrypted_data": base64.b64encode(value.encode()).decode(),
        "salt": base64.b64encode(salt).decode(),
        "algorithm": "PBKDF2-SHA256-base64",
        "iterations": 100000,
        "version": "1.0",
    }


def decrypt_value(encrypted: dict[str, Any], password: str) -> str:
    """Stub decryption for wallet files."""
    return base64.b64decode(encrypted.get("encrypted_data", "")).decode()


__all__ = ["encrypt_value", "decrypt_value"]
