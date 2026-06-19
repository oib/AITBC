"""Test CORS configuration validation"""

import os

import pytest
from pydantic import ValidationError


def test_cors_localhost_allowed_in_dev():
    """Test that localhost origins are allowed in development"""
    os.environ["ENVIRONMENT"] = "dev"
    from app.config import Settings

    settings = Settings(allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"])
    assert "http://localhost:8000" in settings.allow_origins


def test_cors_localhost_blocked_in_production():
    """Test that localhost origins are blocked in production"""
    os.environ["ENVIRONMENT"] = "production"
    from app.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"])

    assert "CORS cannot allow localhost origins in production" in str(exc_info.value)


def test_cors_production_origins_allowed():
    """Test that non-localhost origins are allowed in production"""
    os.environ["ENVIRONMENT"] = "production"
    from app.config import Settings

    settings = Settings(allow_origins=["https://api.example.com", "https://app.example.com"])
    assert "https://api.example.com" in settings.allow_origins
