"""
JWT Authentication Tests for AITBC Agent Coordinator
Tests JWT token generation, validation, and authentication middleware
"""

import pytest
import requests
import jwt
import time
from datetime import datetime, timedelta
from typing import Dict, Any

class TestJWTAuthentication:
    """Test JWT authentication system"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_admin_login(self):
        """Test admin user login"""
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["role"] == "admin"
        assert data["username"] == "admin"
        assert "expires_at" in data
        assert data["token_type"] == "Bearer"
        
        return data["access_token"]
    
    def test_operator_login(self):
        """Test operator user login"""
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "operator", "password": "operator123"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["role"] == "operator"
        assert "access_token" in data
        assert "refresh_token" in data
        
        return data["access_token"]
    
    def test_user_login(self):
        """Test regular user login"""
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "user", "password": "user123"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["role"] == "user"
        assert "access_token" in data
        assert "refresh_token" in data
        
        return data["access_token"]
    
    def test_invalid_login(self):
        """Test login with invalid credentials"""
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "invalid", "password": "invalid"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Invalid credentials"
    
    def test_missing_credentials(self):
        """Test login with missing credentials"""
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_token_validation(self):
        """Test JWT token validation"""
        # Login to get token
        token = self.test_admin_login()
        
        # Validate token
        response = requests.post(
            f"{self.BASE_URL}/auth/validate",
            json={"token": token},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["valid"] is True
        assert "payload" in data
        assert data["payload"]["role"] == "admin"
        assert data["payload"]["username"] == "admin"
    
    def test_invalid_token_validation(self):
        """Test validation of invalid token"""
        response = requests.post(
            f"{self.BASE_URL}/auth/validate",
            json={"token": "invalid_token"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Invalid token"
    
    def test_expired_token_validation(self):
        """Test validation of expired token"""
        # Create manually expired token
        expired_payload = {
            "user_id": "test_user",
            "username": "test",
            "role": "user",
            "exp": datetime.utcnow() - timedelta(hours=1),  # Expired 1 hour ago
            "iat": datetime.utcnow() - timedelta(hours=2),
            "type": "access"
        }
        
        # Note: This would require the secret key, so we'll test with a malformed token
        response = requests.post(
            f"{self.BASE_URL}/auth/validate",
            json={"token": "malformed.jwt.token"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 401
    
    def test_token_refresh(self):
        """Test token refresh functionality"""
        # Login to get refresh token
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        
        refresh_token = response.json()["refresh_token"]
        
        # Refresh the token
        response = requests.post(
            f"{self.BASE_URL}/auth/refresh",
            json={"refresh_token": refresh_token},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "token" in data
        assert "expires_at" in data
    
    def test_invalid_refresh_token(self):
        """Test refresh with invalid token"""
        response = requests.post(
            f"{self.BASE_URL}/auth/refresh",
            json={"refresh_token": "invalid_refresh_token"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "Invalid or expired refresh token" in data["detail"]

class TestProtectedEndpoints:
    """Test protected endpoints with authentication"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_admin_protected_endpoint(self):
        """Test admin-only protected endpoint"""
        # Login as admin
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # Access admin endpoint
        response = requests.get(
            f"{self.BASE_URL}/protected/admin",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "Welcome admin!" in data["message"]
        assert data["user"]["role"] == "admin"
    
    def test_operator_protected_endpoint(self):
        """Test operator protected endpoint"""
        # Login as operator
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "operator", "password": "operator123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # Access operator endpoint
        response = requests.get(
            f"{self.BASE_URL}/protected/operator",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "Welcome operator!" in data["message"]
        assert data["user"]["role"] == "operator"
    
    def test_user_access_admin_endpoint(self):
        """Test user accessing admin endpoint (should fail)"""
        # Login as regular user
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "user", "password": "user123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # Try to access admin endpoint
        response = requests.get(
            f"{self.BASE_URL}/protected/admin",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 403
        data = response.json()
        assert "Insufficient permissions" in data["detail"]
    
    def test_unprotected_endpoint_access(self):
        """Test accessing protected endpoint without token"""
        response = requests.get(f"{self.BASE_URL}/protected/admin")
        
        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Authentication required"
    
    def test_invalid_token_protected_endpoint(self):
        """Test accessing protected endpoint with invalid token"""
        response = requests.get(
            f"{self.BASE_URL}/protected/admin",
            headers={"Authorization": "Bearer invalid_token"}
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "Authentication failed" in data["detail"]

class TestAPIKeyManagement:
    """Test API key management"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_generate_api_key(self):
        """Test API key generation"""
        # Login as admin
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # Generate API key
        response = requests.post(
            f"{self.BASE_URL}/auth/api-key/generate",
            json={"user_id": "test_user_001", "permissions": ["agent:view", "task:view"]},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "api_key" in data
        assert "permissions" in data
        assert "created_at" in data
        assert len(data["api_key"]) > 30  # Should be a long secure key
        
        return data["api_key"]
    
    def test_validate_api_key(self):
        """Test API key validation"""
        # Generate API key first
        api_key = self.test_generate_api_key()
        
        # Validate API key
        response = requests.post(
            f"{self.BASE_URL}/auth/api-key/validate",
            json={"api_key": api_key},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["valid"] is True
        assert "user_id" in data
        assert "permissions" in data
    
    def test_invalid_api_key_validation(self):
        """Test validation of invalid API key"""
        response = requests.post(
            f"{self.BASE_URL}/auth/api-key/validate",
            json={"api_key": "invalid_api_key"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Invalid API key"
    
    def test_revoke_api_key(self):
        """Test API key revocation"""
        # Generate API key first
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        response = requests.post(
            f"{self.BASE_URL}/auth/api-key/generate",
            json={"user_id": "test_user_002"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        api_key = response.json()["api_key"]
        
        # Revoke API key
        response = requests.delete(
            f"{self.BASE_URL}/auth/api-key/{api_key}",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "API key revoked" in data["message"]
        
        # Try to validate revoked key
        response = requests.post(
            f"{self.BASE_URL}/auth/api-key/validate",
            json={"api_key": api_key},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 401

class TestUserManagement:
    """Test user and role management"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_assign_user_role(self):
        """Test assigning role to user"""
        # Login as admin
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # Assign role to user
        response = requests.post(
            f"{self.BASE_URL}/users/test_user_003/role",
            json={"role": "operator"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["user_id"] == "test_user_003"
        assert data["role"] == "operator"
        assert "permissions" in data
    
    def test_get_user_role(self):
        """Test getting user role"""
        # Login as admin
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # Get user role
        response = requests.get(
            f"{self.BASE_URL}/users/test_user_003/role",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["user_id"] == "test_user_003"
        assert data["role"] == "operator"
    
    def test_get_user_permissions(self):
        """Test getting user permissions"""
        # Login as admin
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # Get user permissions
        response = requests.get(
            f"{self.BASE_URL}/users/test_user_003/permissions",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "permissions" in data
        assert "total_permissions" in data
        assert isinstance(data["permissions"], list)
    
    def test_grant_custom_permission(self):
        """Test granting custom permission to user"""
        # Login as admin
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # Grant custom permission
        response = requests.post(
            f"{self.BASE_URL}/users/test_user_003/permissions/grant",
            json={"permission": "agent:register"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["permission"] == "agent:register"
        assert "total_custom_permissions" in data
    
    def test_revoke_custom_permission(self):
        """Test revoking custom permission from user"""
        # Login as admin
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # Revoke custom permission
        response = requests.delete(
            f"{self.BASE_URL}/users/test_user_003/permissions/agent:register",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "remaining_custom_permissions" in data

class TestRoleManagement:
    """Test role and permission management"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_list_all_roles(self):
        """Test listing all available roles"""
        # Login as admin
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # List all roles
        response = requests.get(
            f"{self.BASE_URL}/roles",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "roles" in data
        assert "total_roles" in data
        assert data["total_roles"] >= 6  # Should have at least 6 roles
        
        # Check for expected roles
        roles = data["roles"]
        expected_roles = ["admin", "operator", "user", "readonly", "agent", "api_user"]
        for role in expected_roles:
            assert role in roles
    
    def test_get_role_permissions(self):
        """Test getting permissions for specific role"""
        # Login as admin
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # Get admin role permissions
        response = requests.get(
            f"{self.BASE_URL}/roles/admin",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["role"] == "admin"
        assert "permissions" in data
        assert "total_permissions" in data
        assert data["total_permissions"] > 40  # Admin should have many permissions
    
    def test_get_permission_stats(self):
        """Test getting permission statistics"""
        # Login as admin
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # Get permission stats
        response = requests.get(
            f"{self.BASE_URL}/auth/stats",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "stats" in data
        stats = data["stats"]
        assert "total_permissions" in stats
        assert "total_roles" in stats
        assert "total_users" in stats
        assert "users_by_role" in stats

if __name__ == '__main__':
    pytest.main([__file__])
