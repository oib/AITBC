"""Tests for aitbc.access_control"""

import os
from datetime import timedelta
from unittest.mock import patch

import pytest

from aitbc.access_control import (
    APIKeyAuth,
    AccessController,
    AccessControlError,
    AuthenticationError,
    AuthorizationError,
    SecureHeaders,
    get_access_controller,
    get_api_key_auth,
)


class TestAccessController:
    def test_init_default(self):
        ac = AccessController()
        assert ac.algorithm == "HS256"
        assert ac.token_expiry == 3600

    def test_init_custom(self):
        ac = AccessController(secret_key="test", algorithm="HS512", token_expiry=60)
        assert ac.secret_key == "test"
        assert ac.algorithm == "HS512"
        assert ac.token_expiry == 60

    def test_check_permission_admin(self):
        ac = AccessController()
        assert ac.check_permission(["admin"], "write") is True

    def test_check_permission_user_read(self):
        ac = AccessController()
        assert ac.check_permission(["user"], "read") is True

    def test_check_permission_user_write(self):
        ac = AccessController()
        assert ac.check_permission(["user"], "write") is False

    def test_check_permission_unknown_role(self):
        ac = AccessController()
        assert ac.check_permission(["unknown"], "read") is False

    def test_check_permission_multiple_roles(self):
        ac = AccessController()
        assert ac.check_permission(["user", "operator"], "write") is True

    @pytest.mark.skipif(
        not hasattr(AccessController, "jwt_available") or not AccessController().jwt_available, reason="JWT not available"
    )
    def test_create_and_verify_token(self):
        ac = AccessController(secret_key="test-secret")
        token = ac.create_token("user1", ["user"])
        assert isinstance(token, str)
        claims = ac.verify_token(token)
        assert claims["sub"] == "user1"
        assert "user" in claims["roles"]

    def test_create_token_no_jwt(self):
        with patch("aitbc.access_control.JWT_AVAILABLE", False):
            ac = AccessController()
            with pytest.raises(AccessControlError):
                ac.create_token("user1", ["user"])

    def test_verify_token_no_jwt(self):
        with patch("aitbc.access_control.JWT_AVAILABLE", False):
            ac = AccessController()
            with pytest.raises(AccessControlError):
                ac.verify_token("token")

    def test_verify_token_invalid(self):
        ac = AccessController(secret_key="test-secret")
        with pytest.raises(AuthenticationError):
            ac.verify_token("invalid.token.here")

    def test_require_role_no_token(self):
        ac = AccessController()

        @ac.require_role("admin")
        def admin_func(token=None):
            return "ok"

        with pytest.raises(AuthorizationError):
            admin_func()

    def test_require_permission_no_token(self):
        ac = AccessController()

        @ac.require_permission("read")
        def read_func(token=None):
            return "ok"

        with pytest.raises(AuthorizationError):
            read_func()


class TestAPIKeyAuth:
    def test_verify_key_valid(self):
        auth = APIKeyAuth(valid_keys=["key1", "key2"])
        assert auth.verify_key("key1") is True

    def test_verify_key_invalid(self):
        auth = APIKeyAuth(valid_keys=["key1"])
        assert auth.verify_key("bad") is False

    def test_verify_key_from_env(self):
        with patch.dict(os.environ, {"VALID_API_KEYS": "key1, key2"}):
            auth = APIKeyAuth()
            assert auth.verify_key("key2") is True

    def test_require_api_key_success(self):
        auth = APIKeyAuth(valid_keys=["secret"])

        @auth.require_api_key()
        def protected(api_key=None):
            return "ok"

        assert protected(api_key="secret") == "ok"

    def test_require_api_key_missing(self):
        auth = APIKeyAuth(valid_keys=["secret"])

        @auth.require_api_key()
        def protected(api_key=None):
            return "ok"

        with pytest.raises(AuthorizationError):
            protected()

    def test_require_api_key_invalid(self):
        auth = APIKeyAuth(valid_keys=["secret"])

        @auth.require_api_key()
        def protected(api_key=None):
            return "ok"

        with pytest.raises(AuthorizationError):
            protected(api_key="bad")


class TestSecureHeaders:
    def test_get_security_headers(self):
        headers = SecureHeaders.get_security_headers()
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-Content-Type-Options"] == "nosniff"


class TestGlobalInstances:
    def test_get_access_controller(self):
        ac1 = get_access_controller()
        ac2 = get_access_controller()
        assert ac1 is ac2

    def test_get_api_key_auth(self):
        auth = get_api_key_auth()
        assert isinstance(auth, APIKeyAuth)
