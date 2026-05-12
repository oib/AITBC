"""
Tests for AITBC configuration classes
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, Mock

from aitbc.config import BaseAITBCConfig, AITBCConfig


class TestBaseAITBCConfig:
    """Tests for BaseAITBCConfig"""

    def test_default_values(self):
        """Test BaseAITBCConfig with default values"""
        config = BaseAITBCConfig()
        assert config.app_name == "AITBC Application"
        assert config.app_version == "1.0.0"
        assert config.environment == "development"
        assert config.debug is False
        assert config.log_level == "INFO"

    def test_custom_values(self):
        """Test BaseAITBCConfig with custom values"""
        config = BaseAITBCConfig(
            app_name="Custom App",
            app_version="2.0.0",
            environment="production",
            debug=True,
            log_level="DEBUG"
        )
        assert config.app_name == "Custom App"
        assert config.app_version == "2.0.0"
        assert config.environment == "production"
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

    def test_default_values(self):
        """Test AITBCConfig with default values"""
        config = AITBCConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.workers == 1
        assert config.database_url is None
        assert config.database_pool_size == 10
        assert config.redis_url is None
        assert config.redis_max_connections == 10
        assert config.redis_timeout == 5
        assert config.secret_key is None
        assert config.jwt_secret is None
        assert config.jwt_algorithm == "HS256"
        assert config.jwt_expiration_hours == 24
        assert config.request_timeout == 30
        assert config.max_request_size == 10 * 1024 * 1024

    def test_custom_server_settings(self):
        """Test AITBCConfig with custom server settings"""
        config = AITBCConfig(
            host="127.0.0.1",
            port=9000,
            workers=4
        )
        assert config.host == "127.0.0.1"
        assert config.port == 9000
        assert config.workers == 4

    def test_custom_database_settings(self):
        """Test AITBCConfig with custom database settings"""
        config = AITBCConfig(
            database_url="postgresql://localhost/test",
            database_pool_size=20
        )
        assert config.database_url == "postgresql://localhost/test"
        assert config.database_pool_size == 20

    def test_custom_redis_settings(self):
        """Test AITBCConfig with custom redis settings"""
        config = AITBCConfig(
            redis_url="redis://localhost:6379",
            redis_max_connections=50,
            redis_timeout=10
        )
        assert config.redis_url == "redis://localhost:6379"
        assert config.redis_max_connections == 50
        assert config.redis_timeout == 10

    def test_custom_security_settings(self):
        """Test AITBCConfig with custom security settings"""
        config = AITBCConfig(
            secret_key="test-secret-key",
            jwt_secret="test-jwt-secret",
            jwt_algorithm="RS256",
            jwt_expiration_hours=48
        )
        assert config.secret_key == "test-secret-key"
        assert config.jwt_secret == "test-jwt-secret"
        assert config.jwt_algorithm == "RS256"
        assert config.jwt_expiration_hours == 48

    def test_custom_performance_settings(self):
        """Test AITBCConfig with custom performance settings"""
        config = AITBCConfig(
            request_timeout=60,
            max_request_size=20 * 1024 * 1024
        )
        assert config.request_timeout == 60
        assert config.max_request_size == 20 * 1024 * 1024

    def test_inherits_base_config(self):
        """Test AITBCConfig inherits from BaseAITBCConfig"""
        config = AITBCConfig(
            app_name="Test App",
            environment="staging"
        )
        assert config.app_name == "Test App"
        assert config.environment == "staging"
        assert config.host == "0.0.0.0"  # AITBCConfig default
        assert config.port == 8000  # AITBCConfig default

    @patch('aitbc.config.logger')
    def test_init_logs_configuration(self, mock_logger):
        """Test __init__ logs configuration"""
        config = AITBCConfig(host="localhost", port=9000)
        mock_logger.info.assert_called_once()
        assert "localhost:9000" in mock_logger.info.call_args[0][0]
        mock_logger.debug.assert_called_once()
