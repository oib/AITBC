"""
Cryptographic utilities for AITBC
Provides Ethereum-specific cryptographic operations and security functions
"""

from typing import Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os
import hashlib


def derive_ethereum_address(private_key: str) -> str:
    """Derive Ethereum address from private key using eth-account"""
    try:
        from eth_account import Account
        # Remove 0x prefix if present
        if private_key.startswith("0x"):
            private_key = private_key[2:]
        
        account = Account.from_key(private_key)
        return account.address
    except ImportError:
        raise ImportError("eth-account is required for Ethereum address derivation. Install with: pip install eth-account")
    except Exception as e:
        raise ValueError(f"Failed to derive address from private key: {e}")


def sign_transaction_hash(transaction_hash: str, private_key: str) -> str:
    """Sign a transaction hash with private key using eth-account"""
    try:
        from eth_account import Account
        # Remove 0x prefix if present
        if private_key.startswith("0x"):
            private_key = private_key[2:]
        if transaction_hash.startswith("0x"):
            transaction_hash = transaction_hash[2:]
        
        account = Account.from_key(private_key)
        signed_message = account.sign_hash(bytes.fromhex(transaction_hash))
        return signed_message.signature.hex()
    except ImportError:
        raise ImportError("eth-account is required for signing. Install with: pip install eth-account")
    except Exception as e:
        raise ValueError(f"Failed to sign transaction hash: {e}")


def verify_signature(message_hash: str, signature: str, address: str) -> bool:
    """Verify a signature using eth-account"""
    try:
        from eth_account import Account
        from eth_utils import to_bytes
        
        # Remove 0x prefixes if present
        if message_hash.startswith("0x"):
            message_hash = message_hash[2:]
        if signature.startswith("0x"):
            signature = signature[2:]
        if address.startswith("0x"):
            address = address[2:]
        
        message_bytes = to_bytes(hexstr=message_hash)
        signature_bytes = to_bytes(hexstr=signature)
        
        recovered_address = Account.recover_message(message_bytes, signature_bytes)
        return recovered_address.lower() == address.lower()
    except ImportError:
        raise ImportError("eth-account and eth-utils are required for signature verification. Install with: pip install eth-account eth-utils")
    except Exception as e:
        raise ValueError(f"Failed to verify signature: {e}")


def encrypt_private_key(private_key: str, password: str) -> str:
    """Encrypt private key using Fernet symmetric encryption"""
    try:
        # Derive key from password
        password_bytes = password.encode('utf-8')
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password_bytes))
        
        # Encrypt private key
        fernet = Fernet(key)
        encrypted_key = fernet.encrypt(private_key.encode('utf-8'))
        
        # Combine salt and encrypted key
        combined = salt + encrypted_key
        return base64.urlsafe_b64encode(combined).decode('utf-8')
    except Exception as e:
        raise ValueError(f"Failed to encrypt private key: {e}")


def decrypt_private_key(encrypted_key: str, password: str) -> str:
    """Decrypt private key using Fernet symmetric encryption"""
    try:
        # Decode combined data
        combined = base64.urlsafe_b64decode(encrypted_key.encode('utf-8'))
        salt = combined[:16]
        encrypted_data = combined[16:]
        
        # Derive key from password
        password_bytes = password.encode('utf-8')
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password_bytes))
        
        # Decrypt private key
        fernet = Fernet(key)
        decrypted_key = fernet.decrypt(encrypted_data)
        return decrypted_key.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Failed to decrypt private key: {e}")


def generate_secure_random_bytes(length: int = 32) -> str:
    """Generate cryptographically secure random bytes as hex string"""
    return os.urandom(length).hex()


def keccak256_hash(data: str) -> str:
    """Compute Keccak-256 hash of data"""
    try:
        from eth_hash.auto import keccak
        if isinstance(data, str):
            data = data.encode('utf-8')
        return keccak(data).hex()
    except ImportError:
        raise ImportError("eth-hash is required for Keccak-256 hashing. Install with: pip install eth-hash")
    except Exception as e:
        raise ValueError(f"Failed to compute Keccak-256 hash: {e}")


def sha256_hash(data: str) -> str:
    """Compute SHA-256 hash of data"""
    try:
        if isinstance(data, str):
            data = data.encode('utf-8')
        return hashlib.sha256(data).hexdigest()
    except Exception as e:
        raise ValueError(f"Failed to compute SHA-256 hash: {e}")


def validate_ethereum_address(address: str) -> bool:
    """Validate Ethereum address format and checksum"""
    try:
        from eth_utils import is_address, is_checksum_address
        return is_address(address) and is_checksum_address(address)
    except ImportError:
        raise ImportError("eth-utils is required for address validation. Install with: pip install eth-utils")
    except Exception:
        return False


def generate_ethereum_private_key() -> str:
    """Generate a new Ethereum private key"""
    try:
        from eth_account import Account
        account = Account.create()
        return account.key.hex()
    except ImportError:
        raise ImportError("eth-account is required for private key generation. Install with: pip install eth-account")
    except Exception as e:
        raise ValueError(f"Failed to generate private key: {e}")
