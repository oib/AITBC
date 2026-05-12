"""
Authentication and authorization test fixtures
Provides fixtures for testing auth flows, JWT tokens, and permissions
"""

import sys
from pathlib import Path
from datetime import UTC, datetime, timedelta
from typing import Dict, Any, Optional
from unittest.mock import Mock
import pytest
import jwt

project_root = Path(__file__).parent.parent.parent


@pytest.fixture
def mock_jwt_secret():
    """Mock JWT secret for testing"""
    return "test_secret_key_for_jwt_signing_please_change_in_production"


@pytest.fixture
def test_user_token(mock_jwt_secret):
    """Generate a valid JWT token for a test user"""
    payload = {
        "user_id": "test-user-123",
        "email": "test@example.com",
        "role": "user",
        "exp": datetime.now(UTC) + timedelta(hours=24),
        "iat": datetime.now(UTC)
    }
    return jwt.encode(payload, mock_jwt_secret, algorithm="HS256")


@pytest.fixture
def test_admin_token(mock_jwt_secret):
    """Generate a valid JWT token for an admin user"""
    payload = {
        "user_id": "admin-user-123",
        "email": "admin@example.com",
        "role": "admin",
        "permissions": ["read", "write", "delete", "admin"],
        "exp": datetime.now(UTC) + timedelta(hours=24),
        "iat": datetime.now(UTC)
    }
    return jwt.encode(payload, mock_jwt_secret, algorithm="HS256")


@pytest.fixture
def expired_token(mock_jwt_secret):
    """Generate an expired JWT token"""
    payload = {
        "user_id": "test-user-123",
        "email": "test@example.com",
        "role": "user",
        "exp": datetime.now(UTC) - timedelta(hours=1),  # Expired
        "iat": datetime.now(UTC) - timedelta(hours=25)
    }
    return jwt.encode(payload, mock_jwt_secret, algorithm="HS256")


@pytest.fixture
def invalid_token():
    """Generate an invalid JWT token"""
    return "invalid.token.string"


@pytest.fixture
def auth_headers(test_user_token):
    """Generate authentication headers with Bearer token"""
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.fixture
def admin_auth_headers(test_admin_token):
    """Generate authentication headers for admin user"""
    return {"Authorization": f"Bearer {test_admin_token}"}


@pytest.fixture
def mock_user():
    """Mock user object for testing"""
    user = Mock()
    user.user_id = "test-user-123"
    user.email = "test@example.com"
    user.username = "testuser"
    user.role = "user"
    user.is_active = True
    user.permissions = ["read", "write"]
    user.created_at = datetime.now(UTC)
    return user


@pytest.fixture
def mock_admin_user():
    """Mock admin user object for testing"""
    admin = Mock()
    admin.user_id = "admin-user-123"
    admin.email = "admin@example.com"
    admin.username = "admin"
    admin.role = "admin"
    admin.is_active = True
    admin.permissions = ["read", "write", "delete", "admin"]
    admin.created_at = datetime.now(UTC)
    return admin


@pytest.fixture
def mock_auth_service():
    """Mock authentication service"""
    service = Mock()
    
    def mock_verify_token(token: str) -> Optional[Dict[str, Any]]:
        try:
            decoded = jwt.decode(token, "test_secret_key_for_jwt_signing_please_change_in_production", algorithms=["HS256"])
            return decoded
        except:
            return None
    
    def mock_generate_token(user_id: str, role: str = "user") -> str:
        payload = {
            "user_id": user_id,
            "role": role,
            "exp": datetime.now(UTC) + timedelta(hours=24),
            "iat": datetime.now(UTC)
        }
        return jwt.encode(payload, "test_secret_key_for_jwt_signing_please_change_in_production", algorithm="HS256")
    
    service.verify_token = mock_verify_token
    service.generate_token = mock_generate_token
    service.get_user = Mock(return_value=Mock(user_id="test-user-123", email="test@example.com"))
    return service


@pytest.fixture
def permission_checker():
    """Mock permission checker for authorization"""
    checker = Mock()
    
    def mock_has_permission(user: Any, permission: str) -> bool:
        if not hasattr(user, 'permissions'):
            return False
        return permission in user.permissions
    
    checker.has_permission = mock_has_permission
    checker.check_role = Mock(return_value=True)
    return checker


@pytest.fixture
def api_key_headers():
    """Generate headers with API key authentication"""
    return {"X-API-Key": "test-api-key-123456"}


@pytest.fixture
def mock_api_keys():
    """Mock API keys for testing"""
    return {
        "test-api-key-123456": {"user_id": "test-user-123", "permissions": ["read", "write"]},
        "admin-api-key-789012": {"user_id": "admin-user-123", "permissions": ["read", "write", "delete", "admin"]}
    }
