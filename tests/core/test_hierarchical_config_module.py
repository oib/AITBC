"""
Tests for AITBC hierarchical config module (hierarchical_config.py)
This module has 0% coverage and 146 statements.
"""

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

# Try to load module - skip if dependencies are missing
try:
    hierarchical_config = importlib.import_module("aitbc.hierarchical_config")
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    pytest.skip(f"Skipping hierarchical_config tests due to missing dependencies: {e}", allow_module_level=True)


# ============================================================================
# HierarchicalConfig Tests
# ============================================================================


class TestHierarchicalConfig:
    """Test HierarchicalConfig class"""

    def test_initialization(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            env_file = Path(tmpdir) / ".env"
            loader = hierarchical_config.HierarchicalConfig(config_file, env_file)
            assert loader.config_file == config_file
            assert loader.env_file == env_file
            assert loader._config_cache is None

    def test_initialization_defaults(self):
        loader = hierarchical_config.HierarchicalConfig()
        assert loader.config_file is not None
        assert loader.env_file is not None

    def test_get_defaults(self):
        loader = hierarchical_config.HierarchicalConfig()
        defaults = loader._get_defaults()
        assert "data_dir" in defaults
        assert "config_dir" in defaults
        assert "log_dir" in defaults
        assert "app_name" in defaults
        assert "environment" in defaults
        assert "debug" in defaults
        assert defaults["debug"] is False

    def test_load_yaml_config(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_data = {"app_name": "Test App", "port": 9000}
            with open(config_file, "w") as f:
                import yaml

                yaml.dump(config_data, f)

            loader = hierarchical_config.HierarchicalConfig()
            result = loader._load_file_config(config_file)
            assert result == config_data

    def test_load_json_config(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            config_data = {"app_name": "Test App", "port": 9000}
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            loader = hierarchical_config.HierarchicalConfig()
            result = loader._load_file_config(config_file)
            assert result == config_data

    def test_load_unsupported_format(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.txt"
            config_file.write_text("test")

            loader = hierarchical_config.HierarchicalConfig()
            with pytest.raises(ValueError, match="Unsupported configuration file format"):
                loader._load_file_config(config_file)

    def test_load_env_file(self):
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("APP_NAME=Test App\nPORT=9000\nDEBUG=true\n")

            loader = hierarchical_config.HierarchicalConfig()
            result = loader._load_env_file(env_file)
            assert result["APP_NAME"] == "Test App"
            assert result["PORT"] == 9000
            assert result["DEBUG"] is True

    def test_load_env_file_with_comments(self):
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("# Comment\nAPP_NAME=Test\nPORT=8000\n")

            loader = hierarchical_config.HierarchicalConfig()
            result = loader._load_env_file(env_file)
            assert "APP_NAME" in result
            assert "PORT" in result

    def test_convert_env_value_boolean_true(self):
        loader = hierarchical_config.HierarchicalConfig()
        assert loader._convert_env_value("true") is True
        assert loader._convert_env_value("yes") is True
        assert loader._convert_env_value("1") is True

    def test_convert_env_value_boolean_false(self):
        loader = hierarchical_config.HierarchicalConfig()
        assert loader._convert_env_value("false") is False
        assert loader._convert_env_value("no") is False
        assert loader._convert_env_value("0") is False

    def test_convert_env_value_integer(self):
        loader = hierarchical_config.HierarchicalConfig()
        assert loader._convert_env_value("42") == 42
        assert loader._convert_env_value("-10") == -10

    def test_convert_env_value_float(self):
        loader = hierarchical_config.HierarchicalConfig()
        assert loader._convert_env_value("3.14") == 3.14
        assert loader._convert_env_value("-2.5") == -2.5

    def test_convert_env_value_string(self):
        loader = hierarchical_config.HierarchicalConfig()
        assert loader._convert_env_value("hello") == "hello"
        assert loader._convert_env_value("test_value") == "test_value"

    def test_merge_configs(self):
        loader = hierarchical_config.HierarchicalConfig()
        base = {"key1": "value1", "key2": "value2"}
        override = {"key2": "new_value2", "key3": "value3"}
        result = loader._merge_configs(base, override)
        assert result["key1"] == "value1"
        assert result["key2"] == "new_value2"
        assert result["key3"] == "value3"

    def test_load_config_with_cache(self):
        loader = hierarchical_config.HierarchicalConfig()
        loader._config_cache = {"cached": True}
        result = loader.load_config()
        assert result == {"cached": True}

    def test_load_config_no_file(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "nonexistent.yaml"
            loader = hierarchical_config.HierarchicalConfig(config_file)
            result = loader.load_config()
            # Should return defaults
            assert "app_name" in result

    def test_load_config_with_yaml_file(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_data = {"app_name": "Custom App", "port": 9000}
            with open(config_file, "w") as f:
                import yaml

                yaml.dump(config_data, f)

            loader = hierarchical_config.HierarchicalConfig(config_file)
            result = loader.load_config()
            assert result["app_name"] == "Custom App"
            assert result["port"] == 9000

    def test_load_config_with_env_file(self):
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("APP_NAME=Env App\nPORT=8888\n")

            loader = hierarchical_config.HierarchicalConfig(env_file=env_file)
            result = loader.load_config()
            assert result["APP_NAME"] == "Env App"
            assert result["PORT"] == 8888

    def test_clear_cache(self):
        loader = hierarchical_config.HierarchicalConfig()
        loader._config_cache = {"cached": True}
        loader.clear_cache()
        assert loader._config_cache is None


# ============================================================================
# ValidatedAITBCConfig Tests
# ============================================================================


class TestValidatedAITBCConfig:
    """Test ValidatedAITBCConfig class"""

    def test_default_values(self):
        config = hierarchical_config.ValidatedAITBCConfig()
        assert config.app_name == "AITBC Application"
        assert config.app_version == "1.0.0"
        assert config.environment == "development"
        assert config.debug is False
        assert config.log_level == "INFO"
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.workers == 1

    def test_validate_environment_valid(self):
        config = hierarchical_config.ValidatedAITBCConfig(
            environment="production", secret_key="test_secret", jwt_secret="test_jwt_secret"
        )
        assert config.environment == "production"

    def test_validate_environment_invalid(self):
        with pytest.raises(ValueError, match="Environment must be one of"):
            hierarchical_config.ValidatedAITBCConfig(environment="invalid")

    def test_validate_environment_case_insensitive(self):
        config = hierarchical_config.ValidatedAITBCConfig(
            environment="PRODUCTION", secret_key="test_secret", jwt_secret="test_jwt_secret"
        )
        assert config.environment == "production"

    def test_validate_log_level_valid(self):
        config = hierarchical_config.ValidatedAITBCConfig(log_level="DEBUG")
        assert config.log_level == "DEBUG"

    def test_validate_log_level_invalid(self):
        with pytest.raises(ValueError, match="Log level must be one of"):
            hierarchical_config.ValidatedAITBCConfig(log_level="INVALID")

    def test_validate_log_level_case_insensitive(self):
        config = hierarchical_config.ValidatedAITBCConfig(log_level="debug")
        assert config.log_level == "DEBUG"

    def test_validate_port_valid(self):
        config = hierarchical_config.ValidatedAITBCConfig(port=8080)
        assert config.port == 8080

    def test_validate_port_invalid_low(self):
        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            hierarchical_config.ValidatedAITBCConfig(port=0)

    def test_validate_port_invalid_high(self):
        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            hierarchical_config.ValidatedAITBCConfig(port=70000)

    def test_validate_workers_valid(self):
        config = hierarchical_config.ValidatedAITBCConfig(workers=4)
        assert config.workers == 4

    def test_validate_workers_invalid(self):
        with pytest.raises(ValueError, match="Workers must be at least 1"):
            hierarchical_config.ValidatedAITBCConfig(workers=0)

    def test_validate_pool_size_valid(self):
        config = hierarchical_config.ValidatedAITBCConfig(database_pool_size=20)
        assert config.database_pool_size == 20

    def test_validate_pool_size_invalid(self):
        with pytest.raises(ValueError, match="Pool size must be at least 1"):
            hierarchical_config.ValidatedAITBCConfig(database_pool_size=0)

    def test_validate_timeout_valid(self):
        config = hierarchical_config.ValidatedAITBCConfig(request_timeout=60)
        assert config.request_timeout == 60

    def test_validate_timeout_invalid(self):
        with pytest.raises(ValueError, match="Request timeout must be at least 1 second"):
            hierarchical_config.ValidatedAITBCConfig(request_timeout=0)

    def test_validate_production_settings_valid(self):
        config = hierarchical_config.ValidatedAITBCConfig(
            environment="production", debug=False, secret_key="test_secret", jwt_secret="test_jwt_secret"
        )
        assert config.environment == "production"

    def test_validate_production_settings_debug_enabled(self):
        with pytest.raises(ValueError, match="Debug mode should not be enabled in production"):
            hierarchical_config.ValidatedAITBCConfig(
                environment="production", debug=True, secret_key="test_secret", jwt_secret="test_jwt_secret"
            )

    def test_validate_production_settings_no_secret_key(self):
        with pytest.raises(ValueError, match="Secret key must be set in production"):
            hierarchical_config.ValidatedAITBCConfig(
                environment="production", debug=False, secret_key=None, jwt_secret="test_jwt_secret"
            )

    def test_validate_production_settings_no_jwt_secret(self):
        with pytest.raises(ValueError, match="JWT secret must be set in production"):
            hierarchical_config.ValidatedAITBCConfig(
                environment="production", debug=False, secret_key="test_secret", jwt_secret=None
            )


# ============================================================================
# Module Functions Tests
# ============================================================================


class TestModuleFunctions:
    """Test module-level functions"""

    def test_load_config_function(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            env_file = Path(tmpdir) / ".env"

            config = hierarchical_config.load_config(config_file, env_file)
            assert config is not None
            assert isinstance(config, hierarchical_config.ValidatedAITBCConfig)

    def test_create_config_template_development(self):
        template = hierarchical_config.create_config_template("development")
        assert template["environment"] == "development"
        assert template["debug"] is True
        assert template["log_level"] == "DEBUG"

    def test_create_config_template_staging(self):
        template = hierarchical_config.create_config_template("staging")
        assert template["environment"] == "staging"
        assert template["debug"] is False
        assert template["log_level"] == "INFO"

    def test_create_config_template_production(self):
        template = hierarchical_config.create_config_template("production")
        assert template["environment"] == "production"
        assert template["debug"] is False
        assert template["log_level"] == "WARNING"

    def test_create_config_template_invalid(self):
        template = hierarchical_config.create_config_template("invalid")
        # Should default to development
        assert template["environment"] == "development"
