"""Security utilities — re-export from aitbc/security/ (v0.10.7 §B6).

This module is a backward-compatibility shim. New code should import
directly from ``aitbc.security``.
"""

from aitbc.security.encryption import (  # noqa: F401
    EncryptionConfig,
    decrypt_value,
    derive_secure_key,
    encrypt_value,
    generate_secure_password,
    migrate_legacy_wallet,
    validate_password_rules,
    validate_password_strength,
    wipe_buffer,
)

__all__ = [
    "EncryptionConfig",
    "decrypt_value",
    "derive_secure_key",
    "encrypt_value",
    "generate_secure_password",
    "migrate_legacy_wallet",
    "validate_password_rules",
    "validate_password_strength",
    "wipe_buffer",
]
