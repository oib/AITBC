"""
Security Utils Tests
Tests for secure encryption utilities
"""


import pytest


class TestDeriveSecureKey:
    """Test derive_secure_key function"""

    def test_derive_secure_key_with_password(self):
        """Test key derivation with valid password"""
        from utils.security import derive_secure_key

        password = "test_password_123"
        fernet_key, salt = derive_secure_key(password)

        assert fernet_key is not None
        assert salt is not None
        assert len(salt) == 32
        assert isinstance(fernet_key, bytes)

    def test_derive_secure_key_with_salt(self):
        """Test key derivation with provided salt"""
        from utils.security import derive_secure_key

        password = "test_password_123"
        salt = b"test_salt_32_bytes_1234567890AB"

        fernet_key, returned_salt = derive_secure_key(password, salt)

        assert returned_salt == salt
        assert fernet_key is not None

    def test_derive_secure_key_short_password(self):
        """Test key derivation with short password"""
        from utils.security import derive_secure_key

        with pytest.raises(ValueError, match="Password must be at least 8 characters"):
            derive_secure_key("short")

    def test_derive_secure_key_empty_password(self):
        """Test key derivation with empty password"""
        from utils.security import derive_secure_key

        with pytest.raises(ValueError, match="Password must be at least 8 characters"):
            derive_secure_key("")


class TestEncryptValue:
    """Test encrypt_value function"""

    def test_encrypt_value(self):
        """Test encrypting a value"""
        from utils.security import encrypt_value

        value = "secret_data"
        password = "test_password_123"

        result = encrypt_value(value, password)

        assert "encrypted_data" in result
        assert "salt" in result
        assert "algorithm" in result
        assert result["algorithm"] == "PBKDF2-SHA256-Fernet"
        assert result["iterations"] == 600_000

    def test_encrypt_value_empty(self):
        """Test encrypting empty value"""
        from utils.security import encrypt_value

        with pytest.raises(ValueError, match="Cannot encrypt empty value"):
            encrypt_value("", "password")

    def test_encrypt_value_weak_password(self):
        """Test encrypting with weak password"""
        from utils.security import encrypt_value

        with pytest.raises(ValueError, match="Password must be at least 8 characters"):
            encrypt_value("value", "short")


class TestDecryptValue:
    """Test decrypt_value function"""

    def test_decrypt_value(self):
        """Test decrypting a value"""
        from utils.security import decrypt_value, encrypt_value

        value = "secret_data"
        password = "test_password_123"

        encrypted = encrypt_value(value, password)
        decrypted = decrypt_value(encrypted, password)

        assert decrypted == value

    def test_decrypt_value_wrong_password(self):
        """Test decrypting with wrong password"""
        from utils.security import decrypt_value, encrypt_value

        value = "secret_data"
        password = "test_password_123"

        encrypted = encrypt_value(value, password)

        with pytest.raises(ValueError, match="Invalid password or corrupted"):
            decrypt_value(encrypted, "wrong_password")

    def test_decrypt_value_legacy_format(self):
        """Test decrypting legacy format (should fail)"""
        from utils.security import decrypt_value

        with pytest.raises(ValueError, match="Legacy encrypted format"):
            decrypt_value("legacy_string", "password")


class TestValidatePasswordStrength:
    """Test validate_password_strength function"""

    def test_validate_weak_password(self):
        """Test weak password validation"""
        from utils.security import validate_password_strength

        result = validate_password_strength("short")

        assert result["score"] < 3
        assert result["is_acceptable"] is False
        assert len(result["issues"]) > 0

    def test_validate_strong_password(self):
        """Test strong password validation"""
        from utils.security import validate_password_strength

        result = validate_password_strength("StrongP@ssw0rd123!")

        assert result["score"] >= 3
        assert result["is_acceptable"] is True
        assert result["strength"] in ["Strong", "Very Strong", "Excellent"]

    def test_validate_common_password(self):
        """Test common password detection"""
        from utils.security import validate_password_strength

        result = validate_password_strength("password")

        assert result["score"] == 0
        assert result["is_acceptable"] is False
        assert "Avoid common passwords" in result["issues"]


class TestGenerateSecurePassword:
    """Test generate_secure_password function"""

    def test_generate_secure_password_default(self):
        """Test generating password with default length"""
        from utils.security import generate_secure_password, validate_password_strength

        password = generate_secure_password()

        assert len(password) == 16
        result = validate_password_strength(password)
        assert result["is_acceptable"] is True

    def test_generate_secure_password_custom_length(self):
        """Test generating password with custom length"""
        from utils.security import generate_secure_password, validate_password_strength

        password = generate_secure_password(length=24)

        assert len(password) == 24
        result = validate_password_strength(password)
        assert result["is_acceptable"] is True


class TestMigrateLegacyWallet:
    """Test migrate_legacy_wallet function"""

    def test_migrate_legacy_wallet_success(self):
        """Test successful wallet migration"""
        from utils.security import migrate_legacy_wallet

        legacy_data = {"encrypted": True, "private_key": "0x1234567890abcdef", "address": "0xabc"}
        new_password = "StrongP@ssw0rd123!"

        result = migrate_legacy_wallet(legacy_data, new_password)

        assert "private_key" in result
        assert "encryption_version" in result
        assert result["encryption_version"] == "1.0"
        assert "migration_timestamp" in result

    def test_migrate_legacy_wallet_not_encrypted(self):
        """Test migrating non-encrypted wallet"""
        from utils.security import migrate_legacy_wallet

        legacy_data = {"private_key": "0x1234567890abcdef"}

        with pytest.raises(ValueError, match="Not a legacy encrypted wallet"):
            migrate_legacy_wallet(legacy_data, "password")

    def test_migrate_legacy_wallet_no_private_key(self):
        """Test migrating wallet without private key"""
        from utils.security import migrate_legacy_wallet

        legacy_data = {"encrypted": True}

        with pytest.raises(ValueError, match="Cannot migrate wallet without private key"):
            migrate_legacy_wallet(legacy_data, "password")

    def test_migrate_legacy_wallet_mock(self):
        """Test migrating mock wallet"""
        from utils.security import migrate_legacy_wallet

        legacy_data = {"encrypted": True, "private_key": "[ENCRYPTED_MOCK]data"}

        with pytest.raises(ValueError, match="Cannot migrate mock wallet"):
            migrate_legacy_wallet(legacy_data, "password")


class TestEncryptionConfig:
    """Test EncryptionConfig class"""

    def test_encryption_config_constants(self):
        """Test encryption configuration constants"""
        from utils.security import EncryptionConfig

        assert EncryptionConfig.PBKDF2_ITERATIONS == 600_000
        assert EncryptionConfig.SALT_LENGTH == 32
        assert EncryptionConfig.MIN_PASSWORD_LENGTH == 8
        assert EncryptionConfig.RECOMMENDED_PASSWORD_LENGTH == 16
        assert EncryptionConfig.ALGORITHM_PBKDF2_FERNET == "PBKDF2-SHA256-Fernet"
        assert EncryptionConfig.CURRENT_VERSION == "1.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
