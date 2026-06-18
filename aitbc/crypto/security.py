"""
DEPRECATED: Security utilities for AITBC
This module is deprecated. Use aitbc.crypto instead.

Provides token generation, session management, API key management, and secret management
"""

import warnings

warnings.warn(
    "aitbc.crypto.security is deprecated, use aitbc.crypto instead",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new modules for backward compatibility
from .hashing import generate_hmac, verify_hmac
from .password import hash_password, verify_password
from .secrets import (
    SecretManager,
    generate_nonce,
    generate_secure_random_int,
    generate_secure_random_string,
    get_secret_manager,
)
from .tokens import (
    APIKeyManager,
    SessionManager,
    generate_api_key,
    generate_token,
    validate_api_key,
    validate_token_format,
)

__all__ = [
    "generate_token",
    "generate_api_key",
    "validate_token_format",
    "validate_api_key",
    "SessionManager",
    "APIKeyManager",
    "generate_secure_random_string",
    "generate_secure_random_int",
    "SecretManager",
    "get_secret_manager",
    "generate_nonce",
    "hash_password",
    "verify_password",
    "generate_hmac",
    "verify_hmac",
]
