"""Unit tests for database encryption module."""

import os
import stat
import tempfile
from pathlib import Path

import pytest

from aitbc_chain.database_encryption import (
    KeyManager,
    DatabaseEncryptor,
    is_database_encrypted,
    encrypt_database,
    decrypt_database,
    get_encryption_key,
    ENCRYPTION_MAGIC,
    ENCRYPTION_VERSION,
)


class TestKeyManager:
    """Tests for KeyManager class."""
    
    def test_generate_key_without_password(self, tmp_path: Path):
        """Test key generation without password."""
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        
        assert len(key) == 32
        assert isinstance(key, bytes)
    
    def test_generate_key_with_password(self, tmp_path: Path):
        """Test key generation with password."""
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key(password="test_password")
        
        # Key with salt should be longer (16 bytes salt + 32 bytes key)
        assert len(key) == 48
        assert isinstance(key, bytes)
    
    def test_save_and_load_key(self, tmp_path: Path):
        """Test saving and loading key."""
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        key_manager.save_key(key)
        
        loaded_key = key_manager.load_key()
        assert loaded_key == key
    
    def test_get_or_generate_key_new(self, tmp_path: Path):
        """Test get_or_generate_key when key doesn't exist."""
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.get_or_generate_key()
        
        assert len(key) == 32
        assert key_manager.load_key() == key
    
    def test_get_or_generate_key_existing(self, tmp_path: Path):
        """Test get_or_generate_key when key already exists."""
        key_manager = KeyManager(tmp_path / "test.key")
        original_key = key_manager.generate_key()
        key_manager.save_key(original_key)
        
        retrieved_key = key_manager.get_or_generate_key()
        assert retrieved_key == original_key
    
    def test_ensure_key_permissions_correct(self, tmp_path: Path):
        """Test ensure_key_permissions with correct permissions."""
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        key_manager.save_key(key)
        
        assert key_manager.ensure_key_permissions() is True
    
    def test_ensure_key_permissions_incorrect(self, tmp_path: Path):
        """Test ensure_key_permissions with incorrect permissions."""
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        key_manager.save_key(key)
        
        # Set incorrect permissions
        os.chmod(tmp_path / "test.key", 0o644)
        
        assert key_manager.ensure_key_permissions() is False
    
    def test_ensure_key_permissions_nonexistent(self, tmp_path: Path):
        """Test ensure_key_permissions when file doesn't exist."""
        key_manager = KeyManager(tmp_path / "nonexistent.key")
        assert key_manager.ensure_key_permissions() is True


class TestDatabaseEncryptor:
    """Tests for DatabaseEncryptor class."""
    
    def test_encrypt_decrypt_file(self, tmp_path: Path):
        """Test encrypting and decrypting a file."""
        # Create test file
        test_file = tmp_path / "test.db"
        test_file.write_bytes(b"test database content")
        
        # Generate key
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        
        # Encrypt
        encryptor = DatabaseEncryptor(key)
        encrypted_file = tmp_path / "test.db.encrypted"
        encryptor.encrypt_file(test_file, encrypted_file)
        
        assert encrypted_file.exists()
        assert is_database_encrypted(encrypted_file)
        
        # Decrypt
        decrypted_file = tmp_path / "test_decrypted.db"
        encryptor.decrypt_file(encrypted_file, decrypted_file)
        
        assert decrypted_file.read_bytes() == b"test database content"
    
    def test_is_encrypted_true(self, tmp_path: Path):
        """Test is_encrypted with encrypted file."""
        test_file = tmp_path / "test.db"
        test_file.write_bytes(b"test content")
        
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        encryptor = DatabaseEncryptor(key)
        
        encrypted_file = tmp_path / "test.db.encrypted"
        encryptor.encrypt_file(test_file, encrypted_file)
        
        assert encryptor.is_encrypted(encrypted_file) is True
    
    def test_is_encrypted_false(self, tmp_path: Path):
        """Test is_encrypted with unencrypted file."""
        test_file = tmp_path / "test.db"
        test_file.write_bytes(b"test content")
        
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        encryptor = DatabaseEncryptor(key)
        
        assert encryptor.is_encrypted(test_file) is False
    
    def test_is_encrypted_nonexistent(self, tmp_path: Path):
        """Test is_encrypted with nonexistent file."""
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        encryptor = DatabaseEncryptor(key)
        
        assert encryptor.is_encrypted(tmp_path / "nonexistent.db") is False
    
    def test_decrypt_with_magic_header_verification(self, tmp_path: Path):
        """Test that decrypt verifies magic header."""
        test_file = tmp_path / "test.db"
        test_file.write_bytes(b"not encrypted content")
        
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        encryptor = DatabaseEncryptor(key)
        
        decrypted_file = tmp_path / "test_decrypted.db"
        
        with pytest.raises(ValueError, match="not an encrypted database"):
            encryptor.decrypt_file(test_file, decrypted_file)
    
    def test_key_too_short(self, tmp_path: Path):
        """Test that short keys are rejected."""
        with pytest.raises(ValueError, match="at least 32 bytes"):
            DatabaseEncryptor(b"short_key")


class TestModuleFunctions:
    """Tests for module-level functions."""
    
    def test_is_database_encrypted_true(self, tmp_path: Path):
        """Test is_database_encrypted with encrypted database."""
        test_file = tmp_path / "test.db"
        test_file.write_bytes(b"test content")
        
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        encryptor = DatabaseEncryptor(key)
        
        encrypted_file = tmp_path / "test.db.encrypted"
        encryptor.encrypt_file(test_file, encrypted_file)
        
        assert is_database_encrypted(encrypted_file) is True
    
    def test_is_database_encrypted_false(self, tmp_path: Path):
        """Test is_database_encrypted with unencrypted database."""
        test_file = tmp_path / "test.db"
        test_file.write_bytes(b"test content")
        
        assert is_database_encrypted(test_file) is False
    
    def test_is_database_encrypted_nonexistent(self, tmp_path: Path):
        """Test is_database_encrypted with nonexistent file."""
        assert is_database_encrypted(tmp_path / "nonexistent.db") is False
    
    def test_encrypt_decrypt_database(self, tmp_path: Path):
        """Test encrypt_database and decrypt_database functions."""
        # Create test database
        test_db = tmp_path / "test.db"
        test_db.write_bytes(b"SQLite database content")
        
        # Generate key
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        
        # Encrypt
        encrypted_db = encrypt_database(test_db, key)
        assert encrypted_db.exists()
        assert is_database_encrypted(encrypted_db)
        
        # Decrypt
        decrypted_db = decrypt_database(encrypted_db, key)
        assert decrypted_db.read_bytes() == b"SQLite database content"
    
    def test_get_encryption_key(self, tmp_path: Path):
        """Test get_encryption_key function."""
        key_path = tmp_path / "test.key"
        
        # First call should generate key
        key = get_encryption_key(key_path)
        assert len(key) == 32
        assert key_path.exists()
        
        # Second call should load existing key
        key2 = get_encryption_key(key_path)
        assert key == key2


class TestEncryptionIntegration:
    """Integration tests for encryption with actual database-like content."""
    
    def test_encrypt_decrypt_sqlite_like_content(self, tmp_path: Path):
        """Test encryption/decryption with SQLite-like content."""
        # Create a file with SQLite-like content
        test_db = tmp_path / "test.db"
        sqlite_header = b"SQLite format 3\x00"
        test_db.write_bytes(sqlite_header + b"\x00" * 100)
        
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        
        # Encrypt
        encrypted_db = encrypt_database(test_db, key)
        assert is_database_encrypted(encrypted_db)
        
        # Decrypt
        decrypted_db = decrypt_database(encrypted_db, key)
        assert decrypted_db.read_bytes() == test_db.read_bytes()
    
    def test_multiple_encrypt_decrypt_cycles(self, tmp_path: Path):
        """Test multiple encryption/decryption cycles."""
        test_db = tmp_path / "test.db"
        test_db.write_bytes(b"test content" * 1000)
        
        key_manager = KeyManager(tmp_path / "test.key")
        key = key_manager.generate_key()
        
        # Multiple cycles
        for i in range(3):
            encrypted = encrypt_database(test_db, key)
            decrypted = decrypt_database(encrypted, key)
            test_db = decrypted
            assert test_db.read_bytes() == b"test content" * 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
