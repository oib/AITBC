"""
Security utilities for AITBC
Provides security hardening features including input validation, sanitization,
audit logging, encryption, and password validation.
"""

from .audit import SecurityAuditLog, SecurityAuditor
from .encryption import (
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
from .rate_limiter import RateLimiter
from .validators import SecurityValidator

__all__ = [
    "EncryptionConfig",
    "RateLimiter",
    "SecurityAuditLog",
    "SecurityAuditor",
    "SecurityValidator",
    "decrypt_value",
    "derive_secure_key",
    "encrypt_value",
    "generate_secure_password",
    "migrate_legacy_wallet",
    "validate_password_rules",
    "validate_password_strength",
    "wipe_buffer",
]
