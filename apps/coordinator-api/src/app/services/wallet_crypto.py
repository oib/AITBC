"""
Secure Cryptographic Operations for Agent Wallets
Fixed implementation using proper Ethereum cryptography
"""

import secrets
from typing import Tuple, Dict, Any
from eth_account import Account
from eth_utils import to_checksum_address
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64
import hashlib


def generate_ethereum_keypair() -> Tuple[str, str, str]:
    """
    Generate proper Ethereum keypair using secp256k1
    
    Returns:
        Tuple of (private_key, public_key, address)
    """
    # Use eth_account which properly implements secp256k1
    account = Account.create()
    
    private_key = account.key.hex()
    public_key = account._private_key.public_key.to_hex()
    address = account.address
    
    return private_key, public_key, address


def verify_keypair_consistency(private_key: str, expected_address: str) -> bool:
    """
    Verify that a private key generates the expected address
    
    Args:
        private_key: 32-byte private key hex
        expected_address: Expected Ethereum address
        
    Returns:
        True if keypair is consistent
    """
    try:
        account = Account.from_key(private_key)
        return to_checksum_address(account.address) == to_checksum_address(expected_address)
    except Exception:
        return False


def derive_secure_key(password: str, salt: bytes = None) -> bytes:
    """
    Derive secure encryption key using PBKDF2
    
    Args:
        password: User password
        salt: Optional salt (generated if not provided)
        
    Returns:
        Tuple of (key, salt) for storage
    """
    if salt is None:
        salt = secrets.token_bytes(32)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,  # OWASP recommended minimum
    )
    
    key = kdf.derive(password.encode())
    return base64.urlsafe_b64encode(key), salt


def encrypt_private_key(private_key: str, password: str) -> Dict[str, str]:
    """
    Encrypt private key with proper KDF and Fernet
    
    Args:
        private_key: 32-byte private key hex
        password: User password
        
    Returns:
        Dict with encrypted data and salt
    """
    # Derive encryption key
    fernet_key, salt = derive_secure_key(password)
    
    # Encrypt
    f = Fernet(fernet_key)
    encrypted = f.encrypt(private_key.encode())
    
    return {
        "encrypted_key": encrypted.decode(),
        "salt": base64.b64encode(salt).decode(),
        "algorithm": "PBKDF2-SHA256-Fernet",
        "iterations": 600_000
    }


def decrypt_private_key(encrypted_data: Dict[str, str], password: str) -> str:
    """
    Decrypt private key with proper verification
    
    Args:
        encrypted_data: Dict with encrypted key and salt
        password: User password
        
    Returns:
        Decrypted private key
        
    Raises:
        ValueError: If decryption fails
    """
    try:
        # Extract salt and encrypted key
        salt = base64.b64decode(encrypted_data["salt"])
        encrypted_key = encrypted_data["encrypted_key"].encode()
        
        # Derive same key
        fernet_key, _ = derive_secure_key(password, salt)
        
        # Decrypt
        f = Fernet(fernet_key)
        decrypted = f.decrypt(encrypted_key)
        
        return decrypted.decode()
    except Exception as e:
        raise ValueError(f"Failed to decrypt private key: {str(e)}")


def validate_private_key_format(private_key: str) -> bool:
    """
    Validate private key format
    
    Args:
        private_key: Private key to validate
        
    Returns:
        True if format is valid
    """
    try:
        # Remove 0x prefix if present
        if private_key.startswith("0x"):
            private_key = private_key[2:]
        
        # Check length (32 bytes = 64 hex chars)
        if len(private_key) != 64:
            return False
        
        # Check if valid hex
        int(private_key, 16)
        
        # Try to create account to verify it's a valid secp256k1 key
        Account.from_key("0x" + private_key)
        
        return True
    except Exception:
        return False


# Security configuration constants
class SecurityConfig:
    """Security configuration constants"""
    
    # PBKDF2 settings
    PBKDF2_ITERATIONS = 600_000
    PBKDF2_ALGORITHM = hashes.SHA256
    SALT_LENGTH = 32
    
    # Fernet settings
    FERNET_KEY_LENGTH = 32
    
    # Validation
    PRIVATE_KEY_LENGTH = 64  # 32 bytes in hex
    ADDRESS_LENGTH = 40     # 20 bytes in hex (without 0x)


# Backward compatibility wrapper for existing code
def create_secure_wallet(agent_id: str, password: str) -> Dict[str, Any]:
    """
    Create a wallet with proper security
    
    Args:
        agent_id: Agent identifier
        password: Strong password for encryption
        
    Returns:
        Wallet data with encrypted private key
    """
    # Generate proper keypair
    private_key, public_key, address = generate_ethereum_keypair()
    
    # Validate consistency
    if not verify_keypair_consistency(private_key, address):
        raise RuntimeError("Keypair generation failed consistency check")
    
    # Encrypt private key
    encrypted_data = encrypt_private_key(private_key, password)
    
    return {
        "agent_id": agent_id,
        "address": address,
        "public_key": public_key,
        "encrypted_private_key": encrypted_data,
        "created_at": secrets.token_hex(16),  # For tracking
        "version": "1.0"
    }


def recover_wallet(encrypted_data: Dict[str, str], password: str) -> Dict[str, str]:
    """
    Recover wallet from encrypted data
    
    Args:
        encrypted_data: Encrypted wallet data
        password: Password for decryption
        
    Returns:
        Wallet keys
    """
    # Decrypt private key
    private_key = decrypt_private_key(encrypted_data, password)
    
    # Validate format
    if not validate_private_key_format(private_key):
        raise ValueError("Decrypted private key has invalid format")
    
    # Derive address and public key to verify
    account = Account.from_key("0x" + private_key)
    
    return {
        "private_key": private_key,
        "public_key": account._private_key.public_key.to_hex(),
        "address": account.address
    }
