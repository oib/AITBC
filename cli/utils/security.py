"""
Secure Encryption Utilities - Fixed Version
Replaces the broken encryption in utils/__init__.py
"""

import base64
import hashlib
import secrets
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def derive_secure_key(password: str, salt: bytes = None) -> tuple[bytes, bytes]:
    """
    Derive secure encryption key using PBKDF2 with SHA-256
    
    Args:
        password: User password (required - no defaults)
        salt: Optional salt (generated if not provided)
        
    Returns:
        Tuple of (fernet_key, salt)
        
    Raises:
        ValueError: If password is empty or too weak
    """
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    
    if salt is None:
        salt = secrets.token_bytes(32)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,  # OWASP recommended minimum
    )
    
    key = kdf.derive(password.encode())
    fernet_key = base64.urlsafe_b64encode(key)
    
    return fernet_key, salt


def encrypt_value(value: str, password: str) -> Dict[str, str]:
    """
    Encrypt a value using PBKDF2 + Fernet (no more hardcoded keys)
    
    Args:
        value: Value to encrypt
        password: Strong password (required)
        
    Returns:
        Dict with encrypted data and metadata
        
    Raises:
        ValueError: If password is too weak
    """
    if not value:
        raise ValueError("Cannot encrypt empty value")
    
    # Derive secure key
    fernet_key, salt = derive_secure_key(password)
    
    # Encrypt
    f = Fernet(fernet_key)
    encrypted = f.encrypt(value.encode())
    
    # Fernet already returns base64, no double encoding
    return {
        "encrypted_data": encrypted.decode(),
        "salt": base64.b64encode(salt).decode(),
        "algorithm": "PBKDF2-SHA256-Fernet",
        "iterations": 600_000,
        "version": "1.0"
    }


def decrypt_value(encrypted_data: Dict[str, str] | str, password: str) -> str:
    """
    Decrypt a PBKDF2 + Fernet encrypted value
    
    Args:
        encrypted_data: Dict with encrypted data or legacy string
        password: Password used for encryption
        
    Returns:
        Decrypted value
        
    Raises:
        ValueError: If decryption fails or password is wrong
        InvalidToken: If the encrypted data is corrupted
    """
    # Handle legacy format (backward compatibility)
    if isinstance(encrypted_data, str):
        # This is the old broken format - we can't decrypt it securely
        raise ValueError(
            "Legacy encrypted format detected. "
            "This data was encrypted with a broken implementation and cannot be securely recovered. "
            "Please recreate the wallet with proper encryption."
        )
    
    try:
        # Extract salt and encrypted data
        salt = base64.b64decode(encrypted_data["salt"])
        encrypted = encrypted_data["encrypted_data"].encode()
        
        # Derive same key
        fernet_key, _ = derive_secure_key(password, salt)
        
        # Decrypt
        f = Fernet(fernet_key)
        decrypted = f.decrypt(encrypted)
        
        return decrypted.decode()
    except InvalidToken:
        raise ValueError("Invalid password or corrupted encrypted data")
    except Exception as e:
        raise ValueError(f"Decryption failed: {str(e)}")


def validate_password_strength(password: str) -> Dict[str, Any]:
    """
    Validate password strength
    
    Args:
        password: Password to validate
        
    Returns:
        Dict with validation results
    """
    issues = []
    score = 0
    
    if len(password) < 8:
        issues.append("Password must be at least 8 characters")
    else:
        score += 1
    
    if len(password) < 12:
        issues.append("Consider using 12+ characters for better security")
    else:
        score += 1
    
    if not any(c.isupper() for c in password):
        issues.append("Include uppercase letters")
    else:
        score += 1
    
    if not any(c.islower() for c in password):
        issues.append("Include lowercase letters")
    else:
        score += 1
    
    if not any(c.isdigit() for c in password):
        issues.append("Include numbers")
    else:
        score += 1
    
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        issues.append("Include special characters")
    else:
        score += 1
    
    # Check for common patterns
    if password.lower() in ["password", "123456", "qwerty", "admin"]:
        issues.append("Avoid common passwords")
        score = 0
    
    strength_levels = {
        0: "Very Weak",
        1: "Weak", 
        2: "Fair",
        3: "Good",
        4: "Strong",
        5: "Very Strong",
        6: "Excellent"
    }
    
    return {
        "score": score,
        "strength": strength_levels.get(score, "Unknown"),
        "issues": issues,
        "is_acceptable": score >= 3
    }


def generate_secure_password(length: int = 16) -> str:
    """
    Generate a secure random password
    
    Args:
        length: Password length
        
    Returns:
        Secure random password
    """
    alphabet = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "!@#$%^&*()_+-=[]{}|;:,.<>?"
    )
    
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    
    # Ensure it meets minimum requirements
    while not validate_password_strength(password)["is_acceptable"]:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
    
    return password


# Migration helper for existing wallets
def migrate_legacy_wallet(legacy_data: Dict[str, Any], new_password: str) -> Dict[str, Any]:
    """
    Migrate a wallet from broken encryption to secure encryption
    
    Args:
        legacy_data: Legacy wallet data with broken encryption
        new_password: New strong password
        
    Returns:
        Migrated wallet data
        
    Raises:
        ValueError: If migration cannot be performed safely
    """
    # Check if this is legacy format
    if "encrypted" not in legacy_data or not legacy_data.get("encrypted"):
        raise ValueError("Not a legacy encrypted wallet")
    
    if "private_key" not in legacy_data:
        raise ValueError("Cannot migrate wallet without private key")
    
    # The legacy wallet might have a plaintext private key
    # If it's truly encrypted with the broken method, we cannot recover it
    private_key = legacy_data["private_key"]
    
    if private_key.startswith("[ENCRYPTED_MOCK]") or private_key.startswith("["):
        # This was never actually encrypted - it's a mock
        raise ValueError(
            "Cannot migrate mock wallet. "
            "Please create a new wallet with proper key generation."
        )
    
    # If we get here, we have a plaintext private key (security issue!)
    # Re-encrypt it properly
    try:
        encrypted_data = encrypt_value(private_key, new_password)
        
        return {
            **legacy_data,
            "private_key": encrypted_data,
            "encryption_version": "1.0",
            "migration_timestamp": secrets.token_hex(16)
        }
    except Exception as e:
        raise ValueError(f"Migration failed: {str(e)}")


# Security constants
class EncryptionConfig:
    """Encryption configuration constants"""
    
    PBKDF2_ITERATIONS = 600_000
    SALT_LENGTH = 32
    MIN_PASSWORD_LENGTH = 8
    RECOMMENDED_PASSWORD_LENGTH = 16
    
    # Algorithm identifiers
    ALGORITHM_PBKDF2_FERNET = "PBKDF2-SHA256-Fernet"
    ALGORITHM_LEGACY = "LEGACY-BROKEN"
    
    # Version tracking
    CURRENT_VERSION = "1.0"
    LEGACY_VERSIONS = ["0.9", "legacy", "broken"]
