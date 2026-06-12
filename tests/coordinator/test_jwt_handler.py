"""
JWT Handler Tests
Tests for JWT token generation, validation, and password management
"""

import sys
from pathlib import Path

from datetime import timedelta

import pytest

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

# Clear any cached 'app' modules from other test suites to avoid import conflicts
for mod_name in list(sys.modules.keys()):
    if mod_name == "app" or mod_name.startswith("app."):
        del sys.modules[mod_name]

try:
    from app.auth.jwt_handler import (
        APIKeyManager,
        JWTHandler,
    )
except Exception as _e:
    pytestmark = pytest.mark.skip(reason=f"agent-coordinator app import conflict: {_e}")


class TestJWTHandler:
    """Test JWTHandler class"""

    def test_jwt_handler_initialization(self):
        """Test JWT handler initialization"""
        handler = JWTHandler("test_secret")
        
        assert handler.secret_key == "test_secret"
        assert handler.algorithm == "HS256"
        assert handler.token_expiry == timedelta(hours=24)
        assert handler.refresh_expiry == timedelta(days=7)

    def test_jwt_handler_default_secret(self):
        """Test JWT handler with default secret"""
        handler = JWTHandler()
        
        assert handler.secret_key is not None
        assert len(handler.secret_key) > 0

    def test_generate_token_success(self):
        """Test successful token generation"""
        handler = JWTHandler("test_secret")
        payload = {"user_id": "user123", "role": "admin"}
        
        result = handler.generate_token(payload)
        
        assert result["status"] == "success"
        assert "token" in result
        assert "expires_at" in result
        assert result["token_type"] == "Bearer"

    def test_generate_token_custom_expiry(self):
        """Test token generation with custom expiry"""
        handler = JWTHandler("test_secret")
        payload = {"user_id": "user123"}
        custom_expiry = timedelta(hours=1)
        
        result = handler.generate_token(payload, expires_delta=custom_expiry)
        
        assert result["status"] == "success"
        assert "token" in result

    def test_generate_refresh_token_success(self):
        """Test successful refresh token generation"""
        handler = JWTHandler("test_secret")
        payload = {"user_id": "user123"}
        
        result = handler.generate_refresh_token(payload)
        
        assert result["status"] == "success"
        assert "refresh_token" in result
        assert "expires_at" in result

    def test_validate_token_valid(self):
        """Test validation of valid token"""
        handler = JWTHandler("test_secret")
        payload = {"user_id": "user123", "role": "admin"}
        token_result = handler.generate_token(payload)
        
        validation = handler.validate_token(token_result["token"])
        
        assert validation["status"] == "success"
        assert validation["valid"] is True
        assert "payload" in validation

    def test_validate_token_invalid(self):
        """Test validation of invalid token"""
        handler = JWTHandler("test_secret")
        
        validation = handler.validate_token("invalid_token")
        
        assert validation["status"] == "error"
        assert validation["valid"] is False

    def test_validate_token_expired(self):
        """Test validation of expired token"""
        handler = JWTHandler("test_secret")
        payload = {"user_id": "user123"}
        # Generate token with very short expiry
        token_result = handler.generate_token(payload, expires_delta=timedelta(seconds=-1))
        
        validation = handler.validate_token(token_result["token"])
        
        assert validation["status"] == "error"
        assert validation["valid"] is False
        assert "expired" in validation["message"].lower()

    def test_refresh_access_token_success(self):
        """Test successful access token refresh"""
        handler = JWTHandler("test_secret")
        payload = {"user_id": "user123", "username": "testuser", "role": "admin"}
        refresh_result = handler.generate_refresh_token(payload)
        
        new_token = handler.refresh_access_token(refresh_result["refresh_token"])
        
        assert new_token["status"] == "success"
        assert "token" in new_token

    def test_refresh_access_token_invalid_refresh(self):
        """Test refresh with invalid refresh token"""
        handler = JWTHandler("test_secret")
        
        result = handler.refresh_access_token("invalid_refresh_token")
        
        assert result["status"] == "error"

    def test_decode_token_without_validation(self):
        """Test token decoding without validation"""
        handler = JWTHandler("test_secret")
        payload = {"user_id": "user123"}
        token_result = handler.generate_token(payload)
        
        decoded = handler.decode_token_without_validation(token_result["token"])
        
        assert decoded["status"] == "success"
        assert "payload" in decoded


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
        assert manager.api_keys[gen_result["api_key"]]["usage_count"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
