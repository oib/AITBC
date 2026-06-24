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
    "APIKeyManager",
    "SecretManager",
    "SessionManager",
    "generate_api_key",
    "generate_hmac",
    "generate_nonce",
    "generate_secure_random_int",
    "generate_secure_random_string",
    "generate_token",
    "get_secret_manager",
    "hash_password",
    "validate_api_key",
    "validate_token_format",
    "verify_hmac",
    "verify_password",
]
