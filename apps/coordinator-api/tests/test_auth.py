"""Tests for auth module."""

import pytest


def test_jwt_secret_exists_or_none():
    """Test JWT secret can be loaded from environment or defaults to None in test."""
    from app.config import Settings

    settings = Settings()
    # In test mode without JWT_SECRET env var, it may be None
    assert settings.jwt_secret is None or len(settings.jwt_secret) >= 32


def test_api_keys_parsing():
    """Test API keys parsing from JSON string."""
    from app.config import Settings

    settings = Settings(client_api_keys='["test-key-16chars-long", "another-key-16ch"]')
    assert "test-key-16chars-long" in settings.client_api_keys


def test_api_keys_empty_in_dev():
    """Test that empty API keys are allowed in development."""
    from app.config import Settings

    settings = Settings(client_api_keys=[])
    assert settings.client_api_keys == []


def test_cors_validation_blocks_localhost_in_prod():
    """Test that localhost origins are blocked in production."""
    from app.config import Settings
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
