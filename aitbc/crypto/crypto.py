"""
Cryptographic utilities for AITBC
Provides Ethereum-specific cryptographic operations and security functions
"""

import base64
import hashlib
import json
import os
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def derive_ethereum_address(private_key: str) -> str:
    """Derive Ethereum address from private key using eth-account"""
    try:
        from eth_account import Account

        # Remove 0x prefix if present
        if private_key.startswith("0x"):
            private_key = private_key[2:]

        account = Account.from_key(private_key)
        return str(account.address)
    except ImportError:
        raise ImportError(
            "eth-account is required for Ethereum address derivation. Install with: pip install eth-account"
        ) from None
    except Exception as e:
        raise ValueError(f"Failed to derive address from private key: {e}") from e


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
        return str(signed_message.signature.hex())
    except ImportError:
        raise ImportError("eth-account is required for signing. Install with: pip install eth-account") from None
    except Exception as e:
        raise ValueError(f"Failed to sign transaction hash: {e}") from e


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
        return bool(recovered_address.lower() == address.lower())
    except ImportError:
        raise ImportError(
            "eth-account and eth-utils are required for signature verification. Install with: pip install eth-account eth-utils"
        ) from None
    except Exception as e:
        raise ValueError(f"Failed to verify signature: {e}") from e


def recover_signer(message_data: dict[str, Any], signature: str) -> str | None:
    """Recover the signer's checksum address from a canonical-JSON signature.

    This is the single canonical implementation that all AITBC services should
    use for request/proof signature verification. It replaces the duplicated
    ``verify_transaction_signature`` / ``verify_request_signature`` /
    ``_verify_proposer_signature`` copies in the blockchain node.

    The signed message is ``keccak256(json.dumps(message_data, sort_keys=True,
    separators=(",", ":")))`` and the signature is a 65-byte secp256k1
    ``r‖s‖v`` hex string (optionally ``0x``-prefixed).

    Args:
        message_data: The dict that was signed (without any ``signature`` key).
        signature: The 65-byte hex signature.

    Returns:
        The recovered checksum address (str) on success, or ``None`` on any
        failure (invalid signature, wrong length, recovery error).
    """
    if not signature:
        return None
    try:
        from eth_keys import keys
        from eth_utils import keccak

        message = json.dumps(message_data, sort_keys=True, separators=(",", ":")).encode()
        msg_hash = keccak(message)
        sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
        if len(sig_bytes) != 65:
            return None
        sig = keys.Signature(sig_bytes)
        pub_key = sig.recover_public_key_from_msg_hash(msg_hash)
        return pub_key.to_checksum_address()
    except Exception:
        return None


def encrypt_private_key(private_key: str, password: str) -> str:
    """Encrypt private key using Fernet symmetric encryption"""
    try:
        # Derive key from password
        password_bytes = password.encode("utf-8")
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
        encrypted_key = fernet.encrypt(private_key.encode("utf-8"))

        # Combine salt and encrypted key
        combined = salt + encrypted_key
        return base64.urlsafe_b64encode(combined).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Failed to encrypt private key: {e}") from e


def decrypt_private_key(encrypted_key: str, password: str) -> str:
    """Decrypt private key using Fernet symmetric encryption"""
    try:
        # Decode combined salt + encrypted data
        combined = base64.urlsafe_b64decode(encrypted_key.encode("utf-8"))

        # Extract salt (first 16 bytes) and encrypted data (remaining bytes)
        salt = combined[:16]
        encrypted_data = combined[16:]

        # Derive same encryption key from password using stored salt
        # Must use identical parameters as encryption for successful decryption
        password_bytes = password.encode("utf-8")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password_bytes))

        # Decrypt private key using derived key
        fernet = Fernet(key)
        decrypted_key = fernet.decrypt(encrypted_data)
        return decrypted_key.decode("utf-8")
    except Exception as e:
        raise ValueError(f"Failed to decrypt private key: {e}") from e


def generate_secure_random_bytes(length: int = 32) -> str:
    """Generate cryptographically secure random bytes as hex string"""
    return os.urandom(length).hex()


def keccak256_hash(data: str | bytes) -> str:
    """Compute Keccak-256 hash of data"""
    try:
        from eth_hash.auto import keccak

        data_bytes = data.encode("utf-8") if isinstance(data, str) else data
        return keccak(data_bytes).hex()
    except ImportError:
        raise ImportError("eth-hash is required for Keccak-256 hashing. Install with: pip install eth-hash") from None
    except Exception as e:
        raise ValueError(f"Failed to compute Keccak-256 hash: {e}") from e


def sha256_hash(data: str | bytes) -> str:
    """Compute SHA-256 hash of data"""
    try:
        data_bytes = data.encode("utf-8") if isinstance(data, str) else data
        return hashlib.sha256(data_bytes).hexdigest()
    except Exception as e:
        raise ValueError(f"Failed to compute SHA-256 hash: {e}") from e


def validate_ethereum_address(address: str) -> bool:
    """Validate Ethereum address format and checksum"""
    try:
        from eth_utils import is_address, is_checksum_address

        return is_address(address) and is_checksum_address(address)
    except ImportError:
        raise ImportError("eth-utils is required for address validation. Install with: pip install eth-utils") from None
    except Exception:
        return False


def generate_ethereum_private_key() -> str:
    """Generate a new Ethereum private key"""
    try:
        from eth_account import Account

        account = Account.create()
        return str(account.key.hex())
    except ImportError:
        raise ImportError(
            "eth-account is required for private key generation. Install with: pip install eth-account"
        ) from None
    except Exception as e:
        raise ValueError(f"Failed to generate private key: {e}") from e
