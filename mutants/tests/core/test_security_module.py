"""
Tests for AITBC security utilities module (crypto/security.py)
This module has 0% coverage and 220 statements.
"""

import importlib.util
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path


# Load module directly by file path to avoid namespace conflicts
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


security = load_module_from_path("aitbc.crypto.security", Path("/opt/aitbc/aitbc/crypto/security.py"))


# ============================================================================
# Token Generation Tests
# ============================================================================


class TestTokenGeneration:
    """Test token generation functions"""

    def test_generate_token(self):
        token = security.generate_token(length=32)
        assert len(token) >= 32
        assert isinstance(token, str)

    def test_generate_token_with_prefix(self):
        token = security.generate_token(length=32, prefix="test_")
        assert token.startswith("test_")
        assert len(token) >= 37  # prefix + 32

    def test_generate_api_key(self):
        api_key = security.generate_api_key()
        assert api_key.startswith("aitbc_")
        assert len(api_key) > 10

    def test_generate_api_key_custom_prefix(self):
        api_key = security.generate_api_key(prefix="custom")
        assert api_key.startswith("custom_")

    def test_validate_token_format_valid(self):
        token = security.generate_token(length=32)
        result = security.validate_token_format(token)
        assert result is True

    def test_validate_token_format_invalid_empty(self):
        result = security.validate_token_format("")
        assert result is False

    def test_validate_token_format_invalid_short(self):
        result = security.validate_token_format("short")
        assert result is False

    def test_validate_token_format_invalid_chars(self):
        result = security.validate_token_format("invalid@token")
        assert result is False

    def test_validate_api_key_valid(self):
        api_key = security.generate_api_key()
        result = security.validate_api_key(api_key)
        assert result is True

    def test_validate_api_key_invalid_prefix(self):
        result = security.validate_api_key("invalid_token")
        assert result is False

    def test_validate_api_key_invalid_empty(self):
        result = security.validate_api_key("")
        assert result is False

    def test_validate_api_key_custom_prefix(self):
        api_key = security.generate_api_key(prefix="custom")
        result = security.validate_api_key(api_key, prefix="custom")
        assert result is True


# ============================================================================
# Session Manager Tests
# ============================================================================


class TestSessionManager:
    """Test SessionManager class"""

    def test_session_manager_initialization(self):
        manager = security.SessionManager(session_timeout=3600)
        assert manager.session_timeout == 3600
        assert manager.sessions == {}

    def test_create_session(self):
        manager = security.SessionManager()
        session_id = manager.create_session("user123", {"role": "admin"})
        assert session_id is not None
        assert session_id in manager.sessions
        assert manager.sessions[session_id]["user_id"] == "user123"

    def test_create_session_no_data(self):
        manager = security.SessionManager()
        session_id = manager.create_session("user123")
        assert session_id is not None
        assert manager.sessions[session_id]["data"] == {}

    def test_get_session_valid(self):
        manager = security.SessionManager()
        session_id = manager.create_session("user123")
        session = manager.get_session(session_id)
        assert session is not None
        assert session["user_id"] == "user123"

    def test_get_session_nonexistent(self):
        manager = security.SessionManager()
        session = manager.get_session("nonexistent")
        assert session is None

    def test_get_session_expired(self):
        manager = security.SessionManager(session_timeout=0)
        session_id = manager.create_session("user123")
        time.sleep(0.01)
        session = manager.get_session(session_id)
        assert session is None

    def test_update_session_valid(self):
        manager = security.SessionManager()
        session_id = manager.create_session("user123")
        result = manager.update_session(session_id, {"role": "admin"})
        assert result is True
        assert manager.sessions[session_id]["data"]["role"] == "admin"

    def test_update_session_invalid(self):
        manager = security.SessionManager()
        result = manager.update_session("nonexistent", {"role": "admin"})
        assert result is False

    def test_delete_session(self):
        manager = security.SessionManager()
        session_id = manager.create_session("user123")
        result = manager.delete_session(session_id)
        assert result is True
        assert session_id not in manager.sessions

    def test_delete_session_nonexistent(self):
        manager = security.SessionManager()
        result = manager.delete_session("nonexistent")
        assert result is False

    def test_cleanup_expired_sessions(self):
        manager = security.SessionManager(session_timeout=0)
        manager.create_session("user1")
        manager.create_session("user2")
        time.sleep(0.01)
        count = manager.cleanup_expired_sessions()
        assert count == 2
        assert len(manager.sessions) == 0

    def test_cleanup_expired_sessions_none(self):
        manager = security.SessionManager()
        manager.create_session("user1")
        count = manager.cleanup_expired_sessions()
        assert count == 0


# ============================================================================
# API Key Manager Tests
# ============================================================================


class TestAPIKeyManager:
    """Test APIKeyManager class"""

    def test_api_key_manager_initialization(self):
        manager = security.APIKeyManager()
        assert manager.storage_path is None
        assert manager.keys == {}

    def test_api_key_manager_with_storage(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            storage_path = Path(f.name)
        try:
            manager = security.APIKeyManager(str(storage_path))
            assert manager.storage_path == str(storage_path)
        finally:
            storage_path.unlink(missing_ok=True)

    def test_create_api_key(self):
        manager = security.APIKeyManager()
        api_key = manager.create_api_key("user123", scopes=["read", "write"], name="test_key")
        assert api_key.startswith("aitbc_")
        assert api_key in manager.keys
        assert manager.keys[api_key]["user_id"] == "user123"
        assert manager.keys[api_key]["scopes"] == ["read", "write"]
        assert manager.keys[api_key]["name"] == "test_key"

    def test_create_api_key_defaults(self):
        manager = security.APIKeyManager()
        api_key = manager.create_api_key("user123")
        assert manager.keys[api_key]["scopes"] == ["read"]
        assert manager.keys[api_key]["name"] is None

    def test_validate_api_key_valid(self):
        manager = security.APIKeyManager()
        api_key = manager.create_api_key("user123")
        key_data = manager.validate_api_key(api_key)
        assert key_data is not None
        assert key_data["user_id"] == "user123"
        assert key_data["last_used"] is not None

    def test_validate_api_key_invalid(self):
        manager = security.APIKeyManager()
        key_data = manager.validate_api_key("invalid_key")
        assert key_data is None

    def test_revoke_api_key(self):
        manager = security.APIKeyManager()
        api_key = manager.create_api_key("user123")
        result = manager.revoke_api_key(api_key)
        assert result is True
        assert api_key not in manager.keys

    def test_revoke_api_key_nonexistent(self):
        manager = security.APIKeyManager()
        result = manager.revoke_api_key("nonexistent")
        assert result is False

    def test_list_user_keys(self):
        manager = security.APIKeyManager()
        key1 = manager.create_api_key("user1")
        key2 = manager.create_api_key("user1")
        key3 = manager.create_api_key("user2")
        user1_keys = manager.list_user_keys("user1")
        assert len(user1_keys) == 2
        assert key1 in user1_keys
        assert key2 in user1_keys
        assert key3 not in user1_keys

    def test_items(self):
        manager = security.APIKeyManager()
        api_key = manager.create_api_key("user123")
        items = list(manager.items())
        assert len(items) == 1
        assert items[0][0] == api_key

    def test_save_and_load_keys(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            storage_path = Path(f.name)
        try:
            manager1 = security.APIKeyManager(str(storage_path))
            api_key = manager1.create_api_key("user123")

            manager2 = security.APIKeyManager(str(storage_path))
            assert api_key in manager2.keys
            assert manager2.keys[api_key]["user_id"] == "user123"
        finally:
            storage_path.unlink(missing_ok=True)


# ============================================================================
# Secure Random Generation Tests
# ============================================================================


class TestSecureRandomGeneration:
    """Test secure random generation functions"""

    def test_generate_secure_random_string(self):
        result = security.generate_secure_random_string(length=32)
        assert len(result) >= 32
        assert isinstance(result, str)

    def test_generate_secure_random_int(self):
        result = security.generate_secure_random_int(min_val=0, max_val=100)
        assert 0 <= result < 100
        assert isinstance(result, int)

    def test_generate_secure_random_int_defaults(self):
        result = security.generate_secure_random_int()
        assert 0 <= result < 2**32
        assert isinstance(result, int)


# ============================================================================
# Secret Manager Tests
# ============================================================================


class TestSecretManager:
    """Test SecretManager class"""

    def test_secret_manager_initialization(self):
        manager = security.SecretManager()
        assert manager.fernet is not None
        assert manager.secrets == {}
        assert manager.default_ttl_hours == 24

    def test_secret_manager_with_key(self):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        manager = security.SecretManager(encryption_key=key)
        assert manager.fernet is not None

    def test_secret_manager_custom_ttl(self):
        manager = security.SecretManager(default_ttl_hours=12)
        assert manager.default_ttl_hours == 12

    def test_set_secret(self):
        manager = security.SecretManager()
        manager.set_secret("test_key", "test_value")
        assert "test_key" in manager.secrets
        assert manager.secrets["test_key"]["version"] == 1

    def test_set_secret_custom_ttl(self):
        manager = security.SecretManager()
        manager.set_secret("test_key", "test_value", ttl_hours=1)
        assert "test_key" in manager.secrets
        # Check expiration is set correctly
        expires_at = datetime.fromisoformat(manager.secrets["test_key"]["expires_at"])
        expected = datetime.now(UTC) + timedelta(hours=1)
        assert abs((expires_at - expected).total_seconds()) < 5

    def test_get_secret_valid(self):
        manager = security.SecretManager()
        manager.set_secret("test_key", "test_value")
        result = manager.get_secret("test_key")
        assert result == "test_value"

    def test_get_secret_nonexistent(self):
        manager = security.SecretManager()
        result = manager.get_secret("nonexistent")
        assert result is None

    def test_get_secret_expired(self):
        manager = security.SecretManager()
        manager.set_secret("test_key", "test_value", ttl_hours=-1)  # Already expired
        result = manager.get_secret("test_key")
        assert result is None

    def test_rotate_secret(self):
        manager = security.SecretManager()
        manager.set_secret("test_key", "old_value")
        result = manager.rotate_secret("test_key", "new_value")
        assert result is True
        assert manager.secrets["test_key"]["version"] == 2
        assert manager.secrets["test_key"]["rotated_at"] is not None

    def test_rotate_secret_nonexistent(self):
        manager = security.SecretManager()
        result = manager.rotate_secret("nonexistent", "new_value")
        assert result is False

    def test_rotate_secret_custom_ttl(self):
        manager = security.SecretManager()
        manager.set_secret("test_key", "old_value")
        manager.rotate_secret("test_key", "new_value", ttl_hours=2)
        expires_at = datetime.fromisoformat(manager.secrets["test_key"]["expires_at"])
        expected = datetime.now(UTC) + timedelta(hours=2)
        assert abs((expires_at - expected).total_seconds()) < 5

    def test_delete_secret(self):
        manager = security.SecretManager()
        manager.set_secret("test_key", "test_value")
        result = manager.delete_secret("test_key")
        assert result is True
        assert "test_key" not in manager.secrets

    def test_delete_secret_nonexistent(self):
        manager = security.SecretManager()
        result = manager.delete_secret("nonexistent")
        assert result is False

    def test_list_secrets_all(self):
        manager = security.SecretManager()
        manager.set_secret("key1", "value1")
        manager.set_secret("key2", "value2")
        keys = manager.list_secrets(include_expired=True)
        assert len(keys) == 2
        assert "key1" in keys
        assert "key2" in keys

    def test_list_secrets_active_only(self):
        manager = security.SecretManager()
        manager.set_secret("key1", "value1")
        manager.set_secret("key2", "value2", ttl_hours=-1)  # Already expired
        keys = manager.list_secrets(include_expired=False)
        assert len(keys) == 1
        assert "key1" in keys
        assert "key2" not in keys

    def test_get_secret_metadata(self):
        manager = security.SecretManager()
        manager.set_secret("test_key", "test_value")
        metadata = manager.get_secret_metadata("test_key")
        assert metadata is not None
        assert metadata["key"] == "test_key"
        assert metadata["version"] == 1
        assert metadata["is_expired"] is False

    def test_get_secret_metadata_nonexistent(self):
        manager = security.SecretManager()
        metadata = manager.get_secret_metadata("nonexistent")
        assert metadata is None

    def test_get_secret_metadata_expired(self):
        manager = security.SecretManager()
        manager.set_secret("test_key", "test_value", ttl_hours=-1)  # Already expired
        metadata = manager.get_secret_metadata("test_key")
        assert metadata is not None
        assert metadata["is_expired"] is True

    def test_cleanup_expired_secrets(self):
        manager = security.SecretManager()
        manager.set_secret("key1", "value1")
        manager.set_secret("key2", "value2", ttl_hours=-1)  # Already expired
        count = manager.cleanup_expired_secrets()
        assert count == 1
        assert "key1" in manager.secrets
        assert "key2" not in manager.secrets

    def test_rotate_encryption_key(self):
        from cryptography.fernet import Fernet

        manager = security.SecretManager()
        manager.set_secret("test_key", "test_value")
        new_key = Fernet.generate_key()
        result = manager.rotate_encryption_key(new_key)
        assert result is True
        # Verify secret still accessible
        assert manager.get_secret("test_key") == "test_value"

    def test_rotate_encryption_key_invalid(self):
        manager = security.SecretManager()
        result = manager.rotate_encryption_key("invalid_key")
        assert result is False

    def test_get_encryption_key(self):
        manager = security.SecretManager()
        key = manager.get_encryption_key()
        assert key is not None
        assert isinstance(key, str)

    def test_export_secrets_metadata_only(self):
        manager = security.SecretManager()
        manager.set_secret("key1", "value1")
        manager.set_secret("key2", "value2")
        export = manager.export_secrets(include_values=False)
        assert len(export) == 2
        assert "key1" in export
        assert "key2" in export
        assert "value" not in export["key1"]
        assert "value" not in export["key2"]

    def test_export_secrets_with_values(self):
        manager = security.SecretManager()
        manager.set_secret("key1", "value1")
        export = manager.export_secrets(include_values=True)
        assert "key1" in export
        assert export["key1"]["value"] == "value1"


# ============================================================================
# Global Secret Manager Tests
# ============================================================================


class TestGlobalSecretManager:
    """Test global secret manager singleton"""

    def test_get_secret_manager_singleton(self):
        # Reset global singleton
        security._global_secret_manager = None
        manager1 = security.get_secret_manager()
        manager2 = security.get_secret_manager()
        assert manager1 is manager2

    def test_get_secret_manager_with_key(self):
        from cryptography.fernet import Fernet

        security._global_secret_manager = None
        key = Fernet.generate_key()
        manager = security.get_secret_manager(encryption_key=key)
        assert manager is not None


# ============================================================================
# Password Hashing Tests
# ============================================================================


class TestPasswordHashing:
    """Test password hashing functions"""

    def test_hash_password(self):
        hashed, salt = security.hash_password("test_password")
        assert hashed is not None
        assert salt is not None
        assert len(salt) == 32  # 16 bytes as hex = 32 chars

    def test_hash_password_with_salt(self):
        salt = "a" * 32
        hashed, returned_salt = security.hash_password("test_password", salt=salt)
        assert returned_salt == salt

    def test_verify_password_valid(self):
        password = "test_password"
        hashed, salt = security.hash_password(password)
        result = security.verify_password(password, hashed, salt)
        assert result is True

    def test_verify_password_invalid(self):
        hashed, salt = security.hash_password("correct_password")
        result = security.verify_password("wrong_password", hashed, salt)
        assert result is False


# ============================================================================
# Cryptographic Utilities Tests
# ============================================================================


class TestCryptographicUtilities:
    """Test cryptographic utility functions"""

    def test_generate_nonce(self):
        nonce = security.generate_nonce(length=16)
        assert len(nonce) == 32  # 16 bytes as hex = 32 chars
        assert isinstance(nonce, str)

    def test_generate_nonce_custom_length(self):
        nonce = security.generate_nonce(length=32)
        assert len(nonce) == 64  # 32 bytes as hex = 64 chars

    def test_generate_hmac(self):
        data = "test_data"
        secret = "test_secret"
        hmac = security.generate_hmac(data, secret)
        assert hmac is not None
        assert len(hmac) == 64  # SHA256 hex = 64 chars

    def test_verify_hmac_valid(self):
        data = "test_data"
        secret = "test_secret"
        signature = security.generate_hmac(data, secret)
        result = security.verify_hmac(data, signature, secret)
        assert result is True

    def test_verify_hmac_invalid(self):
        data = "test_data"
        secret = "test_secret"
        signature = "invalid_signature"
        result = security.verify_hmac(data, signature, secret)
        assert result is False

    def test_verify_hmac_wrong_data(self):
        signature = security.generate_hmac("original_data", "secret")
        result = security.verify_hmac("modified_data", signature, "secret")
        assert result is False

    def test_verify_hmac_wrong_secret(self):
        signature = security.generate_hmac("data", "secret1")
        result = security.verify_hmac("data", signature, "secret2")
        assert result is False
