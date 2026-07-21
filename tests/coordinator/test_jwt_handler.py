"""
JWT Handler Tests
Tests for JWT token generation, validation, and password management
"""

from datetime import timedelta

import pytest
from fastapi import HTTPException

from aitbc.auth import APIKeyManager, JWTAuth, JWTHandler
from aitbc.exceptions import ConfigurationError


class TestJWTHandler:
    """Test JWTHandler class"""

    def test_jwt_handler_initialization(self):
        """Test JWT handler initialization"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")

        assert handler.secret_key == "test_secret_key_for_testing_that_is_at_least_32_characters"
        assert handler.algorithm == "HS256"
        assert handler.token_expiry == timedelta(hours=24)
        assert handler.refresh_expiry == timedelta(days=7)

    def test_jwt_handler_default_secret(self, monkeypatch):
        """Test JWT handler with default secret in a non-production environment"""
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")

        handler = JWTHandler()

        assert handler.secret_key is not None
        assert len(handler.secret_key) > 0

    def test_jwt_handler_requires_secret_in_production(self, monkeypatch):
        """Test that missing JWT secret raises an error in production"""
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")

        with pytest.raises(ConfigurationError, match="JWT_SECRET"):
            JWTHandler()

    def test_jwt_handler_rejects_short_secret(self):
        """Test that an explicit short secret is rejected"""
        with pytest.raises(ValueError, match="at least 32"):
            JWTHandler("short")

    def test_jwt_handler_rejects_default_secret(self):
        """Test that known default secrets are rejected"""
        with pytest.raises(ValueError, match="default"):
            JWTHandler("change-me-in-production")

    def test_generate_token_success(self):
        """Test successful token generation"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123", "role": "admin"}

        result = handler.generate_token(payload)

        assert result["status"] == "success"
        assert "token" in result
        assert "expires_at" in result
        assert result["token_type"] == "Bearer"

    def test_generate_token_standardizes_sub_claim(self):
        """Test token generation creates a canonical `sub` claim from legacy `user_id`"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")

        result = handler.generate_token({"user_id": "user123", "role": "admin"})
        validation = handler.validate_token(result["token"])

        assert validation["valid"] is True
        assert validation["payload"]["sub"] == "user123"
        assert validation["payload"]["user_id"] == "user123"

    def test_generate_token_custom_expiry(self):
        """Test token generation with custom expiry"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123"}
        custom_expiry = timedelta(hours=1)

        result = handler.generate_token(payload, expires_delta=custom_expiry)

        assert result["status"] == "success"
        assert "token" in result

    def test_generate_refresh_token_success(self):
        """Test successful refresh token generation"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123"}

        result = handler.generate_refresh_token(payload)

        assert result["status"] == "success"
        assert "refresh_token" in result
        assert "expires_at" in result

    def test_validate_token_valid(self):
        """Test validation of valid token"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123", "role": "admin"}
        token_result = handler.generate_token(payload)

        validation = handler.validate_token(token_result["token"])

        assert validation["status"] == "success"
        assert validation["valid"] is True
        assert "payload" in validation

    def test_validate_token_invalid(self):
        """Test validation of invalid token"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")

        validation = handler.validate_token("invalid_token")

        assert validation["status"] == "error"
        assert validation["valid"] is False

    def test_validate_token_expired(self):
        """Test validation of expired token"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123"}
        # Generate token with very short expiry
        token_result = handler.generate_token(payload, expires_delta=timedelta(seconds=-1))

        validation = handler.validate_token(token_result["token"])

        assert validation["status"] == "error"
        assert validation["valid"] is False
        assert "expired" in validation["message"].lower()

    def test_validate_token_does_not_expose_internals(self):
        """Test that invalid token validation returns a generic error message"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")

        validation = handler.validate_token("not.a.token")

        assert validation["status"] == "error"
        assert "PyJWT" not in validation["message"]
        assert "decode" not in validation["message"].lower()

    def test_refresh_access_token_success(self):
        """Test successful access token refresh"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123", "username": "testuser", "role": "admin"}
        refresh_result = handler.generate_refresh_token(payload)

        new_token = handler.refresh_access_token(refresh_result["refresh_token"])

        assert new_token["status"] == "success"
        assert "token" in new_token

    def test_refresh_access_token_invalid_refresh(self):
        """Test refresh with invalid refresh token"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")

        result = handler.refresh_access_token("invalid_refresh_token")

        assert result["status"] == "error"

    def test_decode_token_without_validation(self):
        """Test token decoding without validation"""
        handler = JWTHandler("test_secret_key_for_testing_that_is_at_least_32_characters")
        payload = {"user_id": "user123"}
        token_result = handler.generate_token(payload)

        decoded = handler.decode_token_without_validation(token_result["token"])

        assert decoded["status"] == "success"
        assert "payload" in decoded

    def test_cross_style_claim_compatibility(self):
        """Test tokens produced by JWTAuth are readable by JWTHandler and vice versa"""
        secret = "test_secret_key_for_testing_that_is_at_least_32_characters"
        auth = JWTAuth(secret=secret)
        handler = JWTHandler(secret_key=secret)

        # Exception-style token decoded by dict-style handler
        token = auth.create_token({"sub": "user1", "role": "client"})
        validation = handler.validate_token(token)
        assert validation["valid"] is True
        assert validation["payload"]["sub"] == "user1"
        assert validation["payload"]["user_id"] == "user1"

        # Dict-style token decoded by exception-style auth
        result = handler.generate_token({"user_id": "user2", "role": "admin"})
        payload = auth.decode_token(result["token"])
        assert payload["sub"] == "user2"
        assert payload["role"] == "admin"

    def test_jwt_restart_stability(self):
        """Test that a new handler instance with the same secret validates an existing token"""
        secret = "test_secret_key_for_testing_that_is_at_least_32_characters"
        handler1 = JWTHandler(secret_key=secret)
        token = handler1.generate_token({"user_id": "user123", "role": "admin"})["token"]

        handler2 = JWTHandler(secret_key=secret)
        validation = handler2.validate_token(token)

        assert validation["valid"] is True


class TestJWTAuth:
    """Test JWTAuth exception-style API"""

    def test_verify_token_rejects_invalid_role(self):
        """Test verify_token rejects a token whose role does not match the required role"""
        auth = JWTAuth(secret="test_secret_key_for_testing_that_is_at_least_32_characters")
        token = auth.create_token({"sub": "user1", "role": "client"})

        with pytest.raises(HTTPException) as exc_info:
            auth.verify_token(token, required_role="admin")

        assert exc_info.value.status_code == 403


class TestAPIKeyManager:
    """Test APIKeyManager class"""

    def test_api_key_manager_initialization(self):
        """Test API key manager initialization"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")

        assert manager.storage_path == "/tmp/test_api_keys.json"
        assert isinstance(manager.api_keys, dict)

    def test_generate_api_key_success(self):
        """Test successful API key generation"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")

        result = manager.generate_api_key("user123", ["read", "write"])

        assert result["status"] == "success"
        assert "api_key" in result
        assert len(result["api_key"]) > 20
        assert result["permissions"] == ["read", "write"]

    def test_generate_api_key_no_permissions(self):
        """Test API key generation without permissions"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")

        result = manager.generate_api_key("user123")

        assert result["status"] == "success"
        assert result["permissions"] == []

    def test_api_keys_are_not_stored_plaintext(self):
        """Test that generated API keys are stored as one-way digests"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")
        gen_result = manager.generate_api_key("user123", ["read"])

        plaintext_key = gen_result["api_key"]
        assert plaintext_key not in manager.api_keys
        assert manager._hash_key(plaintext_key) in manager.api_keys

    def test_validate_api_key_valid(self):
        """Test validation of valid API key"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")
        gen_result = manager.generate_api_key("user123", ["read"])

        validate_result = manager.validate_api_key(gen_result["api_key"])

        assert validate_result["status"] == "success"
        assert validate_result["valid"] is True
        assert validate_result["user_id"] == "user123"
        assert validate_result["permissions"] == ["read"]

    def test_validate_api_key_invalid(self):
        """Test validation of invalid API key"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")

        validate_result = manager.validate_api_key("invalid_key")

        assert validate_result["status"] == "error"
        assert validate_result["valid"] is False

    def test_revoke_api_key_success(self):
        """Test successful API key revocation"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")
        gen_result = manager.generate_api_key("user123", ["read"])

        revoke_result = manager.revoke_api_key(gen_result["api_key"])

        assert revoke_result["status"] == "success"
        assert "revoked" in revoke_result["message"].lower()

    def test_revoke_api_key_not_found(self):
        """Test revocation of non-existent API key"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")

        revoke_result = manager.revoke_api_key("nonexistent_key")

        assert revoke_result["status"] == "error"
        assert "not found" in revoke_result["message"].lower()

    def test_api_key_usage_tracking(self):
        """Test that API key usage is tracked"""
        manager = APIKeyManager(storage_path="/tmp/test_api_keys.json")
        gen_result = manager.generate_api_key("user123", ["read"])

        # First validation
        manager.validate_api_key(gen_result["api_key"])
        # Second validation
        validate_result = manager.validate_api_key(gen_result["api_key"])

        assert validate_result["status"] == "success"
        # Usage count should be incremented
        assert validate_result["usage_count"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
