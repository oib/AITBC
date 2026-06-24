"""
Cryptographic utilities for AITBC
Provides encryption, signing, hashing, and security-related functions
"""

from .crypto import (
    decrypt_private_key,
    derive_ethereum_address,
    encrypt_private_key,
    generate_ethereum_private_key,
    generate_secure_random_bytes,
    keccak256_hash,
    sha256_hash,
    sign_transaction_hash,
    validate_ethereum_address,
    verify_signature,
)
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
from .transaction_service import TransactionService

__all__ = [
    "APIKeyManager",
    # Secret management
    "SecretManager",
    "SessionManager",
    # Transaction service
    "TransactionService",
    "decrypt_private_key",
    # Crypto functions
    "derive_ethereum_address",
    "encrypt_private_key",
    "generate_api_key",
    "generate_ethereum_private_key",
    # Hashing functions
    "generate_hmac",
    "generate_nonce",
    "generate_secure_random_bytes",
    "generate_secure_random_int",
    "generate_secure_random_string",
    # Token functions
    "generate_token",
    "get_secret_manager",
    # Password functions
    "hash_password",
    "keccak256_hash",
    "sha256_hash",
    "sign_transaction_hash",
    "validate_api_key",
    "validate_ethereum_address",
    "validate_token_format",
    "verify_hmac",
    "verify_password",
    "verify_signature",
]
