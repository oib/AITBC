"""Tests for auth module."""

import pytest


def test_jwt_secret_exists_or_none():
    """Test JWT secret can be loaded from environment or defaults to None in test."""
    from coordinator_api.config import Settings

    settings = Settings()
    # In test mode without JWT_SECRET env var, it may be None or empty string
    # (empty string is treated as "not set" in development/test mode)
    assert settings.jwt_secret in (None, "") or len(settings.jwt_secret) >= 32


def test_api_keys_parsing():
    """Test API keys parsing from JSON string."""
    from coordinator_api.config import Settings

    settings = Settings(client_api_keys='["test-key-16chars-long", "another-key-16ch"]')
    assert "test-key-16chars-long" in settings.client_api_keys


def test_api_keys_empty_in_dev():
    """Test that empty API keys are allowed in development."""
    from coordinator_api.config import Settings

    settings = Settings(client_api_keys=[])
    assert settings.client_api_keys == []


def test_cors_validation_blocks_localhost_in_prod():
    """Test that localhost origins are blocked in production."""
    from coordinator_api.config import Settings
    import os

    original = os.environ.get("ENVIRONMENT")
    os.environ["ENVIRONMENT"] = "production"
    try:
        with pytest.raises(ValueError, match="localhost"):
            Settings(allow_origins=["http://localhost:8203"])
    finally:
        if original is None:
            os.environ.pop("ENVIRONMENT", None)
        else:
            os.environ["ENVIRONMENT"] = original


def test_admin_test_key_route_removed():
    """F7: the unauthenticated /admin/test-key key-validity oracle is gone."""
    from coordinator_api.contexts.infrastructure.routers.admin import router

    assert all(getattr(r, "path", "") != "/admin/test-key" for r in router.routes)


def test_api_key_membership_is_constant_time(monkeypatch):
    """F7: verify_api_key compares keys with hmac.compare_digest, not `in`."""
    import hmac as hmac_mod
    from unittest.mock import MagicMock

    from coordinator_api.utils import security as sec

    spy = MagicMock(side_effect=hmac_mod.compare_digest)
    monkeypatch.setattr(sec.hmac, "compare_digest", spy)

    from fastapi.security import HTTPAuthorizationCredentials

    from coordinator_api.config import settings

    settings.client_api_keys = ["a" * 64]
    try:
        # A wrong-format key never reaches the comparison; use a 64-hex guess.
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="b" * 64)
        request = MagicMock()
        request.client.host = "127.0.0.1"

        import asyncio

        with pytest.raises(Exception) as exc_info:
            asyncio.run(sec.verify_api_key(request, creds))
        assert getattr(exc_info.value, "status_code", None) == 401
        assert spy.called, "constant-time comparison was not used for key membership"
    finally:
        settings.client_api_keys = []
