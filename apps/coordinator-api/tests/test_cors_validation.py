"""Test CORS configuration validation"""

from unittest.mock import patch

import pytest
from pydantic import ValidationError


def test_cors_localhost_allowed_in_dev():
    """Test that localhost origins are allowed in development"""
    from app.config import Settings

    with patch.dict("os.environ", {"ENVIRONMENT": "development"}):
        settings = Settings(allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"])
        assert "http://localhost:8000" in settings.allow_origins


def test_cors_localhost_blocked_in_production():
    """Test that localhost origins are blocked in production"""
    from app.config import Settings

    with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                client_api_keys=["test-key-long-enough-1"],
                miner_api_keys=["test-key-long-enough-2"],
                admin_api_keys=["test-key-long-enough-3"],
                allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
                blockchain_rpc_url="https://rpc.example.com",
            )

        assert "CORS cannot allow localhost origins in production" in str(exc_info.value)


def test_cors_production_origins_allowed():
    """Test that non-localhost origins are allowed in production"""
    from app.config import Settings

    with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
        settings = Settings(
            environment="production",
            debug=False,
            client_api_keys=["test-key-long-enough-1"],
            miner_api_keys=["test-key-long-enough-2"],
            admin_api_keys=["test-key-long-enough-3"],
            allow_origins=["https://api.example.com", "https://app.example.com"],
            blockchain_rpc_url="https://rpc.example.com",
            secret_key="test-secret-key-32-chars-long-xxx",
            jwt_secret="test-jwt-secret-32-chars-long-xxx",
        )
        assert "https://api.example.com" in settings.allow_origins
