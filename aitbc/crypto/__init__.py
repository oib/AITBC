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
from .security import (
    generate_api_key,
    generate_hmac,
    generate_nonce,
    generate_secure_random_int,
    generate_secure_random_string,
    generate_token,
    hash_password,
    validate_api_key,
    validate_token_format,
    verify_hmac,
    verify_password,
)

__all__ = [
    # Crypto functions
    'derive_ethereum_address',
    'sign_transaction_hash',
    'verify_signature',
    'encrypt_private_key',
    'decrypt_private_key',
    'generate_secure_random_bytes',
    'keccak256_hash',
    'sha256_hash',
    'validate_ethereum_address',
    'generate_ethereum_private_key',
    # Security functions
    'generate_token',
    'generate_api_key',
    'validate_token_format',
    'validate_api_key',
    'generate_secure_random_string',
    'generate_secure_random_int',
    'hash_password',
    'verify_password',
    'generate_nonce',
    'generate_hmac',
    'verify_hmac'
]
