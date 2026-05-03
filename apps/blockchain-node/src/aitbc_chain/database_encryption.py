"""Database encryption module for AITBC blockchain node.

This module provides AES-GCM encryption for SQLite database files at rest,
using the existing cryptography library. It supports key management,
encryption/decryption operations, and detection of encrypted databases.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import secrets


# Magic header to identify encrypted databases
ENCRYPTION_MAGIC = b"AITBCENC"
ENCRYPTION_VERSION = 1


class KeyManager:
    """Manages encryption key generation, storage, and retrieval."""
    
    def __init__(self, key_path: Path):
        """Initialize key manager.
        
        Args:
            key_path: Path to the key file.
        """
        self.key_path = key_path
        self._key: Optional[bytes] = None
    
    def generate_key(self, password: Optional[str] = None) -> bytes:
        """Generate a new encryption key.
        
        Args:
            password: Optional password for key derivation. If None, generates random key.
        
        Returns:
            256-bit encryption key.
        """
        if password:
            # Derive key from password using PBKDF2
            salt = secrets.token_bytes(16)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100_000,
                backend=default_backend()
            )
            key = kdf.derive(password.encode('utf-8'))
            # Store salt with key for later derivation
            return salt + key
        else:
            # Generate random key
            return secrets.token_bytes(32)
    
    def save_key(self, key: bytes) -> None:
        """Save encryption key to file with restricted permissions.
        
        Args:
            key: Encryption key to save.
        """
        # Ensure parent directory exists
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write key with restricted permissions
        with open(self.key_path, 'wb') as f:
            f.write(key)
        
        # Set file permissions to 600 (owner read/write only)
        os.chmod(self.key_path, stat.S_IRUSR | stat.S_IWUSR)
    
    def load_key(self) -> Optional[bytes]:
        """Load encryption key from file.
        
        Returns:
            Encryption key or None if file doesn't exist.
        """
        if not self.key_path.exists():
            return None
        
        with open(self.key_path, 'rb') as f:
            return f.read()
    
    def get_or_generate_key(self, password: Optional[str] = None) -> bytes:
        """Get existing key or generate a new one.
        
        Args:
            password: Optional password for key derivation.
        
        Returns:
            Encryption key.
        """
        key = self.load_key()
        if key is None:
            key = self.generate_key(password)
            self.save_key(key)
        return key
    
    def ensure_key_permissions(self) -> bool:
        """Ensure key file has restricted permissions.
        
        Returns:
            True if permissions are correct or file doesn't exist, False otherwise.
        """
        if not self.key_path.exists():
            return True
        
        mode = self.key_path.stat().st_mode
        return mode & 0o777 == 0o600


class DatabaseEncryptor:
    """Handles encryption and decryption of database files."""
    
    def __init__(self, key: bytes):
        """Initialize encryptor with encryption key.
        
        Args:
            key: 256-bit encryption key.
        """
        if len(key) < 32:
            # If key has salt prefix (first 16 bytes), extract actual key
            if len(key) >= 48:
                salt = key[:16]
                actual_key = key[16:48]
            else:
                raise ValueError("Encryption key must be at least 32 bytes")
        else:
            salt = key[:16] if len(key) > 32 else b''
            actual_key = key[:32] if len(key) >= 32 else key
        
        self.key = actual_key
        self.salt = salt if len(key) > 32 else None
        self.aesgcm = AESGCM(actual_key)
    
    def encrypt_file(self, input_path: Path, output_path: Path) -> None:
        """Encrypt a database file.
        
        Args:
            input_path: Path to input database file.
            output_path: Path to write encrypted database.
        """
        # Read plaintext database
        with open(input_path, 'rb') as f:
            plaintext = f.read()
        
        # Generate nonce
        nonce = secrets.token_bytes(12)
        
        # Encrypt data
        ciphertext = self.aesgcm.encrypt(nonce, plaintext, None)
        
        # Write encrypted file with magic header
        with open(output_path, 'wb') as f:
            f.write(ENCRYPTION_MAGIC)
            f.write(bytes([ENCRYPTION_VERSION]))
            f.write(nonce)
            f.write(ciphertext)
    
    def decrypt_file(self, input_path: Path, output_path: Path) -> None:
        """Decrypt an encrypted database file.
        
        Args:
            input_path: Path to encrypted database file.
            output_path: Path to write decrypted database.
        """
        # Read encrypted file
        with open(input_path, 'rb') as f:
            data = f.read()
        
        # Verify magic header
        if not data.startswith(ENCRYPTION_MAGIC):
            raise ValueError("File is not an encrypted database")
        
        # Extract version, nonce, and ciphertext
        version = data[len(ENCRYPTION_MAGIC)]
        if version != ENCRYPTION_VERSION:
            raise ValueError(f"Unsupported encryption version: {version}")
        
        nonce_start = len(ENCRYPTION_MAGIC) + 1
        nonce_end = nonce_start + 12
        nonce = data[nonce_start:nonce_end]
        ciphertext = data[nonce_end:]
        
        # Decrypt data
        plaintext = self.aesgcm.decrypt(nonce, ciphertext, None)
        
        # Write decrypted file
        with open(output_path, 'wb') as f:
            f.write(plaintext)
    
    def is_encrypted(self, file_path: Path) -> bool:
        """Check if a database file is encrypted.
        
        Args:
            file_path: Path to database file.
        
        Returns:
            True if file is encrypted, False otherwise.
        """
        if not file_path.exists():
            return False
        
        with open(file_path, 'rb') as f:
            header = f.read(len(ENCRYPTION_MAGIC))
        
        return header == ENCRYPTION_MAGIC


def get_encryption_key(key_path: Path) -> Optional[bytes]:
    """Get encryption key from file or generate new one.
    
    Args:
        key_path: Path to key file.
    
    Returns:
        Encryption key or None if encryption is disabled.
    """
    key_manager = KeyManager(key_path)
    return key_manager.get_or_generate_key()


def encrypt_database(db_path: Path, key: bytes) -> Path:
    """Encrypt a database file.
    
    Args:
        db_path: Path to database file.
        key: Encryption key.
    
    Returns:
        Path to encrypted database file.
    """
    encryptor = DatabaseEncryptor(key)
    encrypted_path = db_path.with_suffix('.db.encrypted')
    encryptor.encrypt_file(db_path, encrypted_path)
    return encrypted_path


def decrypt_database(encrypted_path: Path, key: bytes, output_path: Optional[Path] = None) -> Path:
    """Decrypt an encrypted database file.
    
    Args:
        encrypted_path: Path to encrypted database file.
        key: Encryption key.
        output_path: Optional output path. If None, removes .encrypted suffix.
    
    Returns:
        Path to decrypted database file.
    """
    encryptor = DatabaseEncryptor(key)
    if output_path is None:
        output_path = encrypted_path.with_suffix('').with_suffix('.db')
    encryptor.decrypt_file(encrypted_path, output_path)
    return output_path


def is_database_encrypted(db_path: Path) -> bool:
    """Check if a database file is encrypted.
    
    Args:
        db_path: Path to database file.
    
    Returns:
        True if database is encrypted, False otherwise.
    """
    if not db_path.exists():
        return False
    
    # Check for magic header
    with open(db_path, 'rb') as f:
        header = f.read(len(ENCRYPTION_MAGIC))
    
    return header == ENCRYPTION_MAGIC
