"""Tests for AITBC configuration classes"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from aitbc.config import AITBCConfig, BaseAITBCConfig


class TestBaseAITBCConfig:
    """Tests for BaseAITBCConfig"""

    def test_custom_values(self):
        """Test BaseAITBCConfig with custom values"""
        config = BaseAITBCConfig(
            app_name="Custom App", app_version="2.0.0", environment="staging", debug=True, log_level="DEBUG"
        )
        assert config.app_name == "Custom App"
        assert config.app_version == "2.0.0"
        assert config.environment == "staging"
        assert config.debug is True
        assert config.log_level == "DEBUG"

    def test_data_dir_default(self):
        """Test default data directory is a Path"""
        config = BaseAITBCConfig()
        assert isinstance(config.data_dir, Path)

    def test_config_dir_default(self):
        """Test default config directory is a Path"""
        config = BaseAITBCConfig()
        assert isinstance(config.config_dir, Path)

    def test_log_dir_default(self):
        """Test default log directory is a Path"""
        config = BaseAITBCConfig()
        assert isinstance(config.log_dir, Path)

    def test_log_format_default(self):
        """Test default log format"""
        config = BaseAITBCConfig()
        assert "%(asctime)s" in config.log_format
        assert "%(name)s" in config.log_format
        assert "%(levelname)s" in config.log_format


class TestAITBCConfig:
    """Tests for AITBCConfig"""

    def test_custom_server_settings(self):
        """Test AITBCConfig with custom server settings"""
        config = AITBCConfig(host="127.0.0.1", port=9000, workers=4)
        assert config.host == "127.0.0.1"
        assert config.port == 9000
        assert config.workers == 4

    def test_custom_database_settings(self):
        """Test AITBCConfig with custom database settings"""
        config = AITBCConfig(database_url="postgresql://localhost/test", database_pool_size=20)
        assert config.database_url == "postgresql://localhost/test"
        assert config.database_pool_size == 20

    def test_custom_redis_settings(self):
        """Test AITBCConfig with custom redis settings"""
        config = AITBCConfig(redis_url="redis://localhost:6379", redis_max_connections=50, redis_timeout=10)
        assert config.redis_url == "redis://localhost:6379"
        assert config.redis_max_connections == 50
        assert config.redis_timeout == 10

    def test_custom_security_settings(self):
        """Test AITBCConfig with custom security settings"""
        config = AITBCConfig(
            secret_key="test-secret-key-thirty-two-characters",
            jwt_secret="test-jwt-secret-thirty-two-characters",
            jwt_algorithm="RS256",
            jwt_expiration_hours=48,
        )
        assert config.secret_key == "test-secret-key-thirty-two-characters"
        assert config.jwt_secret == "test-jwt-secret-thirty-two-characters"
        assert config.jwt_algorithm == "RS256"
        assert config.jwt_expiration_hours == 48

    def test_custom_performance_settings(self):
        """Test AITBCConfig with custom performance settings"""
        config = AITBCConfig(request_timeout=60, max_request_size=20 * 1024 * 1024)
        assert config.request_timeout == 60
        assert config.max_request_size == 20 * 1024 * 1024

    def test_inherits_base_config(self):
        """Test AITBCConfig inherits from BaseAITBCConfig"""
        config = AITBCConfig(app_name="Test App", environment="staging")
        assert config.app_name == "Test App"
        assert config.environment == "staging"
        assert config.host == "0.0.0.0"  # AITBCConfig default
        assert config.port == 8000  # AITBCConfig default


class TestProductionSecretValidation:
    """validate_secret_length uses the shared is_production() precedence.

    It previously read APP_ENV only, so a production deployment declared through
    ENVIRONMENT or NODE_ENV skipped the length/default checks on provided
    secrets. Requiredness stays tied to the ``environment`` field (set by
    ENVIRONMENT or an explicit value) — an explicit environment="development"
    keeps the model validator inert while the env var drives the length check.
    """

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        for var in ("ENVIRONMENT", "APP_ENV", "NODE_ENV"):
            monkeypatch.delenv(var, raising=False)

    @pytest.mark.parametrize("var", ["ENVIRONMENT", "APP_ENV", "NODE_ENV"])
    def test_short_secret_rejected_in_production(self, monkeypatch, var):
        monkeypatch.setenv(var, "production")
        with pytest.raises(ValidationError, match="at least 32 characters"):
            BaseAITBCConfig(secret_key="short", environment="development")

    @pytest.mark.parametrize("var", ["ENVIRONMENT", "APP_ENV", "NODE_ENV"])
    def test_strong_secret_accepted_in_production(self, monkeypatch, var):
        monkeypatch.setenv(var, "production")
        config = BaseAITBCConfig(secret_key="s" * 32, jwt_secret="j" * 32, environment="development")
        assert config.secret_key == "s" * 32

    def test_short_secret_accepted_when_not_production(self):
        config = BaseAITBCConfig(secret_key="short", environment="development")
        assert config.secret_key == "short"

    def test_missing_secret_passes_length_check_in_production(self, monkeypatch):
        """Requiredness belongs to validate_production_settings, not the length check."""
        monkeypatch.setenv("NODE_ENV", "production")
        config = BaseAITBCConfig(environment="development")
        assert config.secret_key in (None, "")
