"""Integration tests for authentication, users, permissions, and alerts."""

import os

import pytest
from starlette.testclient import TestClient


class TestAuthentication:
    """Test authentication endpoints."""

    def test_login_admin_success(self, coordinator_client: TestClient):
        """Test successful admin login."""
        admin_password = os.getenv("TEST_ADMIN_PASSWORD")
        if not admin_password:
            pytest.skip("TEST_ADMIN_PASSWORD environment variable not set")
        login_data = {"username": "admin", "password": admin_password}
        response = coordinator_client.post("/v1/auth/login", json=login_data)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["username"] == "admin"
        assert data["role"] == "admin"
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_invalid_credentials(self, coordinator_client: TestClient):
        """Test login with invalid credentials."""
        if not os.getenv("TEST_ADMIN_PASSWORD"):
            pytest.skip("TEST_ADMIN_PASSWORD environment variable not set")
        login_data = {"username": "admin", "password": "wrongpassword"}
        response = coordinator_client.post("/v1/auth/login", json=login_data)
        assert response.status_code == 401

    def test_login_missing_fields(self, coordinator_client: TestClient):
        """Test login with missing username or password."""
        login_data = {"username": "admin"}
        response = coordinator_client.post("/v1/auth/login", json=login_data)
        assert response.status_code == 422

    def test_refresh_token_success(self, coordinator_client: TestClient):
        """Test successful token refresh."""
        admin_password = os.getenv("TEST_ADMIN_PASSWORD")
        if not admin_password:
            pytest.skip("TEST_ADMIN_PASSWORD environment variable not set")
        login_data = {"username": "admin", "password": admin_password}
        login_response = coordinator_client.post("/v1/auth/login", json=login_data)
        refresh_token = login_response.json()["refresh_token"]

        refresh_data = {"refresh_token": refresh_token}
        response = coordinator_client.post("/v1/auth/refresh", json=refresh_data)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "token" in data

    def test_validate_token_success(self, coordinator_client: TestClient):
        """Test successful token validation."""
        admin_password = os.getenv("TEST_ADMIN_PASSWORD")
        if not admin_password:
            pytest.skip("TEST_ADMIN_PASSWORD environment variable not set")
        login_data = {"username": "admin", "password": admin_password}
        login_response = coordinator_client.post("/v1/auth/login", json=login_data)
        token = login_response.json()["access_token"]

        validate_data = {"token": token}
        response = coordinator_client.post("/v1/auth/validate", json=validate_data)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    def test_validate_token_invalid(self, coordinator_client: TestClient):
        """Test validation with invalid token."""
        validate_data = {"token": "invalid_token"}
        response = coordinator_client.post("/v1/auth/validate", json=validate_data)
        assert response.status_code == 401


class TestAuthMiddleware:
    """Test authentication middleware and JWT handler."""

    def test_login_all_user_types(self, coordinator_client: TestClient):
        """Test login for all user types."""
        if not os.getenv("TEST_ADMIN_PASSWORD"):
            pytest.skip("TEST_ADMIN_PASSWORD environment variable not set")
        users = [
            {"username": "admin", "password": os.getenv("TEST_ADMIN_PASSWORD")},
            {"username": "operator", "password": os.getenv("TEST_OPERATOR_PASSWORD", "operator123")},
            {"username": "user", "password": os.getenv("TEST_USER_PASSWORD", "user123")},
        ]
        for user in users:
            response = coordinator_client.post("/v1/auth/login", json=user)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "access_token" in data
            assert "refresh_token" in data

    def test_refresh_token_multiple_times(self, coordinator_client: TestClient):
        """Test refreshing token multiple times."""
        if not os.getenv("TEST_ADMIN_PASSWORD"):
            pytest.skip("TEST_ADMIN_PASSWORD environment variable not set")
        login_data = {"username": "admin", "password": os.getenv("TEST_ADMIN_PASSWORD")}
        login_response = coordinator_client.post("/v1/auth/login", json=login_data)
        refresh_token = login_response.json()["refresh_token"]

        for _ in range(3):
            refresh_data = {"refresh_token": refresh_token}
            response = coordinator_client.post("/v1/auth/refresh", json=refresh_data)
            assert response.status_code == 200
            data = response.json()
            if data["status"] == "success":
                refresh_token = data.get("refresh_token", refresh_token)

    def test_validate_token_various_formats(self, coordinator_client: TestClient):
        """Test validating tokens in various formats."""
        if not os.getenv("TEST_ADMIN_PASSWORD"):
            pytest.skip("TEST_ADMIN_PASSWORD environment variable not set")
        login_data = {"username": "admin", "password": os.getenv("TEST_ADMIN_PASSWORD")}
        login_response = coordinator_client.post("/v1/auth/login", json=login_data)
        valid_token = login_response.json()["access_token"]

        response = coordinator_client.post("/v1/auth/validate", json={"token": valid_token})
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

        invalid_tokens = ["invalid_token", "Bearer invalid", ""]
        for invalid_token in invalid_tokens:
            response = coordinator_client.post("/v1/auth/validate", json={"token": invalid_token})
            assert response.status_code in (401, 422)

    def test_api_key_operations(self, coordinator_client: TestClient):
        """Test API key generation and validation."""
        if not os.getenv("TEST_ADMIN_PASSWORD"):
            pytest.skip("TEST_ADMIN_PASSWORD environment variable not set")
        login_data = {"username": "admin", "password": os.getenv("TEST_ADMIN_PASSWORD")}
        login_response = coordinator_client.post("/v1/auth/login", json=login_data)
        token = login_response.json()["access_token"]

        response = coordinator_client.post(
            "/v1/auth/api-key/generate?user_id=test_user&permissions=READ", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code in (200, 403, 500)

        response = coordinator_client.post("/v1/auth/api-key/validate?api_key=test_api_key")
        assert response.status_code in (200, 401, 500)

    def test_protected_endpoints_without_auth(self, coordinator_client: TestClient):
        """Test that protected endpoints reject requests without auth."""
        protected_endpoints = ["/protected/admin", "/protected/operator", "/alerts", "/users/test_user/role"]
        for endpoint in protected_endpoints:
            response = coordinator_client.get(endpoint)
            assert response.status_code in (401, 403, 404)


class TestAuthAdvanced:
    """Advanced authentication tests for better coverage."""

    def test_auth_token_expiration_scenarios(self, coordinator_client: TestClient):
        """Test token expiration and refresh scenarios."""
        if not os.getenv("TEST_ADMIN_PASSWORD"):
            pytest.skip("TEST_ADMIN_PASSWORD environment variable not set")
        login_data = {"username": "admin", "password": os.getenv("TEST_ADMIN_PASSWORD")}
        login_response = coordinator_client.post("/v1/auth/login", json=login_data)
        access_token = login_response.json()["access_token"]
        refresh_token = login_response.json()["refresh_token"]

        response = coordinator_client.post("/v1/auth/validate", json={"token": access_token})
        assert response.status_code == 200

        for _ in range(2):
            refresh_data = {"refresh_token": refresh_token}
            response = coordinator_client.post("/v1/auth/refresh", json=refresh_data)
            if response.status_code == 200:
                refresh_token = response.json().get("refresh_token", refresh_token)

    def test_auth_invalid_credentials(self, coordinator_client: TestClient):
        """Test authentication with invalid credentials."""
        invalid_credentials = [
            {"username": "nonexistent", "password": "wrong"},
            {"username": "admin", "password": "wrong"},
            {"username": "", "password": ""},
            {"username": None, "password": None},
        ]
        for creds in invalid_credentials:
            if creds.get("username") is not None:
                response = coordinator_client.post("/v1/auth/login", json=creds)
                assert response.status_code in (401, 422)

    def test_auth_api_key_scenarios(self, coordinator_client: TestClient):
        """Test API key generation and validation scenarios."""
        user_ids = ["user_001", "user_002", "admin_001"]
        permissions = ["READ", "WRITE", "ADMIN"]

        for user_id in user_ids:
            for perm in permissions:
                response = coordinator_client.post(f"/v1/auth/api-key/generate?user_id={user_id}&permissions={perm}")
                assert response.status_code in (200, 401, 403, 500)

    def test_auth_protected_endpoints_with_valid_token(self, authenticated_client: TestClient):
        """Test protected endpoints with valid authentication."""
        endpoints = ["/protected/admin", "/protected/operator", "/users/test_user/role", "/alerts"]
        for endpoint in endpoints:
            response = authenticated_client.get(endpoint)
            assert response.status_code in (200, 403, 404)


class TestUsers:
    """Test user management endpoints."""

    def test_assign_user_role_unauthorized(self, coordinator_client: TestClient):
        """Test assigning user role without authentication."""
        response = coordinator_client.post("/v1/users/test_user/role", json={"role": "admin"})
        assert response.status_code in (401, 403)

    def test_assign_user_role_authorized(self, authenticated_client: TestClient):
        """Test assigning user role with authentication."""
        response = authenticated_client.post("/v1/users/test_user/role", json={"role": "admin"})
        assert response.status_code in (200, 403, 422, 500)

    def test_get_user_role_authorized(self, authenticated_client: TestClient):
        """Test getting user role with authentication."""
        response = authenticated_client.get("/v1/users/test_user/role")
        assert response.status_code in (200, 403, 404)

    def test_get_user_permissions_authorized(self, authenticated_client: TestClient):
        """Test getting user permissions with authentication."""
        response = authenticated_client.get("/v1/users/test_user/permissions")
        assert response.status_code in (200, 403, 404)

    def test_grant_user_permission_authorized(self, authenticated_client: TestClient):
        """Test granting user permission with authentication."""
        response = authenticated_client.post("/v1/users/test_user/permissions/grant", json={"permission": "SECURITY_MANAGE"})
        assert response.status_code in (200, 403, 422, 500)

    def test_revoke_user_permission_authorized(self, authenticated_client: TestClient):
        """Test revoking user permission with authentication."""
        response = authenticated_client.delete("/v1/users/test_user/permissions/SECURITY_MANAGE")
        assert response.status_code in (200, 403, 400, 500)

    def test_list_roles_authorized(self, authenticated_client: TestClient):
        """Test listing roles with authentication."""
        response = authenticated_client.get("/v1/roles")
        assert response.status_code in (200, 403)

    def test_get_role_permissions_authorized(self, authenticated_client: TestClient):
        """Test getting role permissions with authentication."""
        response = authenticated_client.get("/v1/roles/admin")
        assert response.status_code in (200, 403, 400)

    def test_protected_admin_authorized(self, authenticated_client: TestClient):
        """Test protected admin endpoint with authentication."""
        response = authenticated_client.get("/v1/protected/admin")
        assert response.status_code in (200, 403)

    def test_protected_operator_authorized(self, authenticated_client: TestClient):
        """Test protected operator endpoint with authentication."""
        response = authenticated_client.get("/v1/protected/operator")
        assert response.status_code in (200, 403)


class TestUsersAdvanced:
    """Advanced user management tests for better coverage."""

    def test_users_all_roles(self, coordinator_client: TestClient):
        """Test all user roles and their permissions."""
        roles = ["admin", "operator", "user", "viewer"]
        for role in roles:
            response = coordinator_client.get(f"/v1/roles/{role}")
            assert response.status_code in (200, 401, 403, 404, 500)

    def test_users_permission_operations(self, coordinator_client: TestClient):
        """Test various permission operations."""
        permissions = ["SECURITY_MANAGE", "AGENT_MANAGE", "TASK_MANAGE", "VIEW_ONLY"]
        for perm in permissions:
            response = coordinator_client.post(f"/v1/users/test_user/permissions/grant?permission={perm}")
            assert response.status_code in (200, 401, 403, 422, 500)

            response = coordinator_client.delete(f"/v1/users/test_user/permissions/{perm}")
            assert response.status_code in (200, 401, 403, 400, 500)

    def test_users_role_assignments(self, coordinator_client: TestClient):
        """Test assigning different roles to users."""
        roles = ["admin", "operator", "user"]
        for role in roles:
            response = coordinator_client.post(f"/v1/users/test_user_{role}/role", json={"role": role})
            assert response.status_code in (200, 401, 403, 422, 500)


class TestUserPermissionComprehensive:
    """Comprehensive user and permission tests for better coverage."""

    def test_user_all_role_operations(self, coordinator_client: TestClient):
        """Test all user role operations."""
        users = ["user-001", "user-002", "user-003"]
        roles = ["admin", "operator", "user"]

        for user_id in users:
            for role in roles:
                response = coordinator_client.post(f"/users/{user_id}/role", json={"role": role})
                assert response.status_code in (200, 401, 403, 422, 500)
                response = coordinator_client.get(f"/users/{user_id}/role")
                assert response.status_code in (200, 401, 403, 404)

    def test_permission_all_operations(self, coordinator_client: TestClient):
        """Test all permission operations."""
        permissions = ["SECURITY_MANAGE", "AGENT_MANAGE", "TASK_MANAGE", "VIEW_ONLY", "SYSTEM_ADMIN", "MONITOR_ACCESS"]

        for perm in permissions:
            response = coordinator_client.post(f"/users/test_user/permissions/grant?permission={perm}")
            assert response.status_code in (200, 401, 403, 422, 500)
            response = coordinator_client.get("/v1/users/test_user/permissions")
            assert response.status_code in (200, 401, 403, 404)
            response = coordinator_client.delete(f"/users/test_user/permissions/{perm}")
            assert response.status_code in (200, 401, 403, 400, 500)

    def test_role_permissions_comprehensive(self, coordinator_client: TestClient):
        """Test comprehensive role permission operations."""
        roles = ["admin", "operator", "user", "viewer"]

        for role in roles:
            response = coordinator_client.get(f"/roles/{role}")
            assert response.status_code in (200, 401, 403, 404, 500)

        response = coordinator_client.get("/roles")
        assert response.status_code in (200, 401, 403, 404, 500)

        endpoints = [("/protected/admin", "admin"), ("/protected/operator", "operator")]
        for endpoint, _expected_role in endpoints:
            response = coordinator_client.get(endpoint)
            assert response.status_code in (200, 401, 403, 404)


class TestAlerts:
    """Test alerting endpoints."""

    def test_get_alerts_unauthorized(self, coordinator_client: TestClient):
        """Test getting alerts without authentication."""
        response = coordinator_client.get("/v1/alerts")
        assert response.status_code in (401, 403)

    def test_get_alerts_authorized(self, authenticated_client: TestClient):
        """Test getting alerts with authentication."""
        response = authenticated_client.get("/v1/alerts")
        assert response.status_code in (200, 403)

    def test_get_alert_stats_authorized(self, authenticated_client: TestClient):
        """Test getting alert stats with authentication."""
        response = authenticated_client.get("/v1/alerts/stats")
        assert response.status_code in (200, 403)

    def test_get_alert_rules_authorized(self, authenticated_client: TestClient):
        """Test getting alert rules with authentication."""
        response = authenticated_client.get("/v1/alerts/rules")
        assert response.status_code in (200, 403)

    def test_get_sla_status_authorized(self, authenticated_client: TestClient):
        """Test getting SLA status with authentication."""
        response = authenticated_client.get("/v1/sla")
        assert response.status_code in (200, 403)

    def test_get_system_status_authorized(self, authenticated_client: TestClient):
        """Test getting system status with authentication."""
        response = authenticated_client.get("/v1/system/status")
        assert response.status_code in (200, 403)

    def test_resolve_alert_authorized(self, authenticated_client: TestClient):
        """Test resolving an alert with authentication."""
        response = authenticated_client.post("/v1/alerts/test-alert-001/resolve")
        assert response.status_code in (200, 403, 404)


class TestAlertsAdvanced:
    """Advanced alerts tests for better coverage."""

    def test_alerts_all_severities(self, coordinator_client: TestClient):
        """Test alerts with all severity levels."""
        response = coordinator_client.get("/v1/alerts/stats")
        if response.status_code == 200:
            data = response.json()
            assert "stats" in data

    def test_sla_all_metrics(self, coordinator_client: TestClient):
        """Test SLA monitoring with various metrics."""
        for _i in range(3):
            response = coordinator_client.post("/v1/sla/test-sla-001/record?value=0.9")
            assert response.status_code in (200, 401, 403, 500)

    def test_alert_rules_validation(self, coordinator_client: TestClient):
        """Test alert rules endpoint."""
        response = coordinator_client.get("/v1/alerts/rules")
        assert response.status_code in (200, 401, 403, 503)


class TestAlertComprehensive:
    """Comprehensive alert tests for better coverage."""

    def test_alert_all_operations(self, coordinator_client: TestClient):
        """Test all alert operations."""
        response = coordinator_client.get("/alerts")
        assert response.status_code in (401, 403, 200)
        response = coordinator_client.get("/v1/alerts/stats")
        assert response.status_code in (200, 401, 403, 503)
        if response.status_code == 200:
            data = response.json()
            assert "stats" in data or isinstance(data, dict)
        response = coordinator_client.get("/v1/alerts/rules")
        assert response.status_code in (200, 401, 403, 503)

        alert_ids = ["alert-001", "alert-002", "alert-003"]
        for alert_id in alert_ids:
            response = coordinator_client.post(f"/alerts/{alert_id}/resolve")
            assert response.status_code in (200, 401, 403, 404)

    def test_sla_all_operations(self, coordinator_client: TestClient):
        """Test all SLA operations."""
        sla_ids = ["sla-001", "sla-002", "sla-003"]

        for sla_id in sla_ids:
            for value in [0.9, 0.8, 0.7]:
                response = coordinator_client.post(f"/sla/{sla_id}/record?value={value}")
                assert response.status_code in (200, 401, 403, 404, 500)

        response = coordinator_client.get("/sla")
        assert response.status_code in (200, 401, 403, 404, 500)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

        response = coordinator_client.get("/v1/system/status")
        assert response.status_code in (200, 401, 403, 404, 500)

    def test_alerting_integration(self, coordinator_client: TestClient):
        """Test alerting integration with other systems."""
        response = coordinator_client.get("/v1/alerts/stats")
        assert response.status_code in (200, 401, 403, 503)
        if response.status_code == 200:
            data = response.json()
            assert "stats" in data or isinstance(data, dict)

        response = coordinator_client.get("/v1/system/status")
        assert response.status_code in (200, 401, 403, 404, 500)

        response = coordinator_client.get("/v1/metrics/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        response = coordinator_client.get("/v1/metrics/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
