"""
Crypto Security Tests
Tests for AITBC crypto security utilities
"""

import pytest

# Password hashing moved out of aitbc.crypto into aitbc.auth.password, where the salted
# tuple-returning pair is named *_pbkdf2 (PasswordManager.hash_password is bcrypt and
# has a different signature).
from aitbc.auth.api_key import APIKeyManager
from aitbc.auth.password import hash_password_pbkdf2 as hash_password
from aitbc.auth.password import verify_password_pbkdf2 as verify_password
from aitbc.crypto import (
    SecretManager,
    SessionManager,
    generate_api_key,
    generate_hmac,
    generate_nonce,
    generate_secure_random_int,
    generate_secure_random_string,
    generate_token,
    validate_api_key,
    validate_token_format,
    verify_hmac,
)


class TestTokenGeneration:
    """Test token generation functions"""

    def test_generate_token(self):
        """Test generate_token function"""
        token = generate_token(length=32)
        assert token is not None
        assert len(token) > 0

    def test_generate_token_with_prefix(self):
        """Test generate_token with prefix"""
        token = generate_token(length=32, prefix="test_")
        assert token.startswith("test_")

    def test_generate_token_uniqueness(self):
        """Test generate_token produces unique tokens"""
        token1 = generate_token(length=32)
        token2 = generate_token(length=32)
        assert token1 != token2

    def test_generate_api_key(self):
        """Test generate_api_key function"""
        api_key = generate_api_key()
        assert api_key is not None
        assert api_key.startswith("aitbc_")

    def test_generate_api_key_custom_prefix(self):
        """Test generate_api_key with custom prefix"""
        api_key = generate_api_key(prefix="custom")
        assert api_key.startswith("custom_")

    def test_generate_api_key_uniqueness(self):
        """Test generate_api_key produces unique keys"""
        key1 = generate_api_key()
        key2 = generate_api_key()
        assert key1 != key2

    def test_validate_token_format_valid(self):
        """Test validate_token_format with valid token"""
        token = generate_token(length=32)
        assert validate_token_format(token) is True

    def test_validate_token_format_invalid_short(self):
        """Test validate_token_format with short token"""
        assert validate_token_format("short") is False

    def test_validate_token_format_invalid_chars(self):
        """Test validate_token_format with invalid characters"""
        assert validate_token_format("token@#$") is False

    def test_validate_token_format_empty(self):
        """Test validate_token_format with empty string"""
        assert validate_token_format("") is False

    def test_validate_api_key_valid(self):
        """Test validate_api_key with valid key"""
        api_key = generate_api_key()
        assert validate_api_key(api_key) is True

    def test_validate_api_key_invalid_prefix(self):
        """Test validate_api_key with invalid prefix"""
        assert validate_api_key("wrong_prefix_abc123") is False

    def test_validate_api_key_custom_prefix(self):
        """Test validate_api_key with custom prefix"""
        api_key = generate_api_key(prefix="custom")
        assert validate_api_key(api_key, prefix="custom") is True

    def test_generate_secure_random_string(self):
        """Test generate_secure_random_string function"""
        random_str = generate_secure_random_string(length=32)
        assert random_str is not None
        assert len(random_str) > 0

    def test_generate_secure_random_int(self):
        """Test generate_secure_random_int function"""
        random_int = generate_secure_random_int(min_val=0, max_val=1000)
        assert 0 <= random_int < 1000

    def test_generate_secure_random_int_default(self):
        """Test generate_secure_random_int with defaults"""
        random_int = generate_secure_random_int()
        assert 0 <= random_int < 2**32

    def test_generate_nonce(self):
        """Test generate_nonce function"""
        nonce = generate_nonce(length=16)
        assert nonce is not None
        assert len(nonce) == 32  # 16 bytes = 32 hex chars

    def test_generate_nonce_custom_length(self):
        """Test generate_nonce with custom length"""
        nonce = generate_nonce(length=8)
        assert len(nonce) == 16  # 8 bytes = 16 hex chars


class TestSessionManager:
    """Test SessionManager class"""

    def test_initialization(self):
        """Test SessionManager initialization"""
        manager = SessionManager(session_timeout=3600)
        assert manager.session_timeout == 3600
        assert manager.sessions == {}

    def test_create_session(self):
        """Test create_session method"""
        manager = SessionManager()
        session_id = manager.create_session("user123", {"role": "admin"})
        assert session_id is not None
        assert session_id in manager.sessions

    def test_get_session(self):
        """Test get_session method"""
        manager = SessionManager()
        session_id = manager.create_session("user123", {"role": "admin"})
        session = manager.get_session(session_id)
        assert session is not None
        assert session["user_id"] == "user123"

    def test_get_session_nonexistent(self):
        """Test get_session with nonexistent session"""
        manager = SessionManager()
        session = manager.get_session("nonexistent")
        assert session is None

    def test_update_session(self):
        """Test update_session method"""
        manager = SessionManager()
        session_id = manager.create_session("user123", {"role": "admin"})
        result = manager.update_session(session_id, {"role": "superadmin"})
        assert result is True
        session = manager.get_session(session_id)
        assert session["data"]["role"] == "superadmin"

    def test_update_session_nonexistent(self):
        """Test update_session with nonexistent session"""
        manager = SessionManager()
        result = manager.update_session("nonexistent", {"role": "admin"})
        assert result is False

    def test_delete_session(self):
        """Test delete_session method"""
        manager = SessionManager()
        session_id = manager.create_session("user123")
        result = manager.delete_session(session_id)
        assert result is True
        assert session_id not in manager.sessions

    def test_delete_session_nonexistent(self):
        """Test delete_session with nonexistent session"""
        manager = SessionManager()
        result = manager.delete_session("nonexistent")
        assert result is False

    def test_cleanup_expired_sessions(self):
        """Test cleanup_expired_sessions method"""
        manager = SessionManager(session_timeout=0)
        manager.create_session("user123")

        import time

        time.sleep(0.1)

        count = manager.cleanup_expired_sessions()
        assert count >= 0


class TestAPIKeyManager:
    """Test APIKeyManager class (persistent JSON store, aitbc.auth.api_key)"""

    @pytest.fixture
    def manager(self, tmp_path):
        """APIKeyManager backed by a tmp_path store, never the default /var/lib path."""
        return APIKeyManager(storage_path=str(tmp_path / "api_keys.json"))

    def test_initialization(self, manager):
        """Test APIKeyManager initialization"""
        assert manager.api_keys == {}

    def test_generate_api_key(self, manager):
        """Test generate_api_key method"""
        result = manager.generate_api_key("user123", permissions=["read", "write"])
        assert result["status"] == "success"
        api_key = result["api_key"]
        assert api_key
        # plaintext key is never stored — only its sha256 digest is a key in api_keys
        key_hash = APIKeyManager._hash_key(api_key)
        assert api_key not in manager.api_keys
        assert key_hash in manager.api_keys
        assert manager.api_keys[key_hash]["user_id"] == "user123"
        assert manager.api_keys[key_hash]["permissions"] == ["read", "write"]

    def test_generate_api_key_default_permissions(self, manager):
        """Test generate_api_key with default permissions"""
        result = manager.generate_api_key("user123")
        assert result["status"] == "success"
        assert result["permissions"] == []

    def test_validate_api_key(self, manager):
        """Test validate_api_key method"""
        result = manager.generate_api_key("user123")
        api_key = result["api_key"]
        validation = manager.validate_api_key(api_key)
        assert validation["status"] == "success"
        assert validation["valid"] is True
        assert validation["user_id"] == "user123"

    def test_validate_api_key_invalid(self, manager):
        """Test validate_api_key with invalid key"""
        validation = manager.validate_api_key("invalid_key")
        assert validation["status"] == "error"
        assert validation["valid"] is False

    def test_revoke_api_key(self, manager):
        """Test revoke_api_key method"""
        result = manager.generate_api_key("user123")
        api_key = result["api_key"]
        key_hash = APIKeyManager._hash_key(api_key)
        revoke_result = manager.revoke_api_key(api_key)
        assert revoke_result["status"] == "success"
        assert key_hash not in manager.api_keys
        assert manager.validate_api_key(api_key)["valid"] is False

    def test_revoke_api_key_nonexistent(self, manager):
        """Test revoke_api_key with nonexistent key"""
        result = manager.revoke_api_key("nonexistent")
        assert result["status"] == "error"

    def test_list_user_keys(self, manager):
        """Test listing keys for a user (no list_user_keys method; scan api_keys)"""
        key1 = manager.generate_api_key("user123")["api_key"]
        key2 = manager.generate_api_key("user123")["api_key"]
        key3 = manager.generate_api_key("user456")["api_key"]

        user_hashes = {APIKeyManager._hash_key(k) for k in (key1, key2, key3)}
        user_keys = [h for h, data in manager.api_keys.items() if data["user_id"] == "user123"]
        assert len(user_keys) == 2
        assert APIKeyManager._hash_key(key1) in user_keys
        assert APIKeyManager._hash_key(key2) in user_keys
        assert APIKeyManager._hash_key(key3) not in user_keys
        assert set(user_keys) <= user_hashes


class TestSecretManager:
    """Test SecretManager class"""

    def test_initialization(self):
        """Test SecretManager initialization"""
        manager = SecretManager()
        assert manager.secrets == {}
        assert manager.fernet is not None

    def test_set_secret(self):
        """Test set_secret method"""
        manager = SecretManager()
        manager.set_secret("api_key", "secret_value")
        assert "api_key" in manager.secrets

    def test_get_secret(self):
        """Test get_secret method"""
        manager = SecretManager()
        manager.set_secret("api_key", "secret_value")
        value = manager.get_secret("api_key")
        assert value == "secret_value"

    def test_get_secret_nonexistent(self):
        """Test get_secret with nonexistent key"""
        manager = SecretManager()
        value = manager.get_secret("nonexistent")
        assert value is None

    def test_delete_secret(self):
        """Test delete_secret method"""
        manager = SecretManager()
        manager.set_secret("api_key", "secret_value")
        result = manager.delete_secret("api_key")
        assert result is True
        assert "api_key" not in manager.secrets

    def test_delete_secret_nonexistent(self):
        """Test delete_secret with nonexistent key"""
        manager = SecretManager()
        result = manager.delete_secret("nonexistent")
        assert result is False

    def test_list_secrets(self):
        """Test list_secrets method"""
        manager = SecretManager()
        manager.set_secret("key1", "value1")
        manager.set_secret("key2", "value2")
        keys = manager.list_secrets()
        assert len(keys) == 2
        assert "key1" in keys
        assert "key2" in keys

    def test_get_encryption_key(self):
        """Test get_encryption_key method"""
        manager = SecretManager()
        key = manager.get_encryption_key()
        assert key is not None
        assert len(key) > 0


class TestPasswordHashing:
    """Test password hashing functions"""

    def test_hash_password(self):
        """Test hash_password function"""
        password = "test_password"
        hashed, salt = hash_password(password)
        assert hashed is not None
        assert salt is not None
        assert hashed != password

    def test_hash_password_with_salt(self):
        """Test hash_password with provided salt"""
        password = "test_password"
        salt = "fixed_salt_12345678"
        hashed, returned_salt = hash_password(password, salt)
        assert returned_salt == salt

    def test_verify_password(self):
        """Test verify_password function"""
        password = "test_password"
        hashed, salt = hash_password(password)
        result = verify_password(password, hashed, salt)
        assert result is True

    def test_verify_password_wrong(self):
        """Test verify_password with wrong password"""
        password = "test_password"
        hashed, salt = hash_password(password)
        result = verify_password("wrong_password", hashed, salt)
        assert result is False

    def test_hash_password_consistency(self):
        """Test hash_password produces consistent results with same salt"""
        password = "test_password"
        salt = "fixed_salt_12345678"
        hashed1, _ = hash_password(password, salt)
        hashed2, _ = hash_password(password, salt)
        assert hashed1 == hashed2


class TestHMAC:
    """Test HMAC functions"""

    def test_generate_hmac(self):
        """Test generate_hmac function"""
        data = "test_data"
        secret = "test_secret"
        hmac_sig = generate_hmac(data, secret)
        assert hmac_sig is not None
        assert len(hmac_sig) == 64  # SHA-256 produces 64 hex chars

    def test_generate_hmac_consistency(self):
        """Test generate_hmac produces consistent results"""
        data = "test_data"
        secret = "test_secret"
        hmac1 = generate_hmac(data, secret)
        hmac2 = generate_hmac(data, secret)
        assert hmac1 == hmac2

    def test_verify_hmac(self):
        """Test verify_hmac function"""
        data = "test_data"
        secret = "test_secret"
        hmac_sig = generate_hmac(data, secret)
        result = verify_hmac(data, hmac_sig, secret)
        assert result is True

    def test_verify_hmac_invalid(self):
        """Test verify_hmac with invalid signature"""
        data = "test_data"
        secret = "test_secret"
        result = verify_hmac(data, "invalid_signature", secret)
        assert result is False

    def test_verify_hmac_wrong_secret(self):
        """Test verify_hmac with wrong secret"""
        data = "test_data"
        secret = "test_secret"
        hmac_sig = generate_hmac(data, secret)
        result = verify_hmac(data, hmac_sig, "wrong_secret")
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
