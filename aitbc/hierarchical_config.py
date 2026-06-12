"""
Hierarchical configuration system for AITBC
Provides multi-source configuration loading with validation
"""
import json
from pathlib import Path
from typing import Any
import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from .aitbc_logging import get_logger
from .constants import CONFIG_DIR, DATA_DIR, ENV_FILE, LOG_DIR
logger = get_logger(__name__)

class HierarchicalConfig:
    """
    Hierarchical configuration loader with multiple sources.

    Configuration loading priority (highest to lowest):
    1. CLI arguments (not implemented here, handled by application)
    2. Environment variables
    3. Configuration file (YAML/JSON)
    4. Default values

    This class provides a clean interface for loading configuration
    from multiple sources with proper precedence.
    """

    def __init__(self, config_file: Path | None=None, env_file: Path | None=None):
        """
        Initialize hierarchical configuration loader

        Args:
            config_file: Path to configuration file (YAML or JSON)
            env_file: Path to environment file (.env)
        """
        self.config_file = config_file or CONFIG_DIR / 'config.yaml'
        self.env_file = env_file or ENV_FILE
        self._config_cache: dict[str, Any] | None = None

    def load_config(self) -> dict[str, Any]:
        """
        Load configuration from all sources with proper precedence.

        Returns:
            Merged configuration dictionary

        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If configuration file format is invalid
        """
        if self._config_cache is not None:
            return self._config_cache
        config = self._get_defaults()
        if self.config_file and self.config_file.exists():
            file_config = self._load_file_config(self.config_file)
            config = self._merge_configs(config, file_config)
            logger.info('Loaded configuration from %s', self.config_file)
        if self.env_file and self.env_file.exists():
            env_config = self._load_env_file(self.env_file)
            config = self._merge_configs(config, env_config)
            logger.info('Loaded environment variables from %s', self.env_file)
        self._config_cache = config
        return config

    def _get_defaults(self) -> dict[str, Any]:
        """Get default configuration values"""
        return {'data_dir': str(DATA_DIR), 'config_dir': str(CONFIG_DIR), 'log_dir': str(LOG_DIR), 'app_name': 'AITBC Application', 'app_version': '1.0.0', 'environment': 'development', 'debug': False, 'log_level': 'INFO', 'host': '0.0.0.0', 'port': 8000, 'workers': 1, 'database_pool_size': 10, 'redis_max_connections': 10, 'redis_timeout': 5, 'jwt_algorithm': 'HS256', 'jwt_expiration_hours': 24, 'request_timeout': 30, 'max_request_size': 10 * 1024 * 1024}

    def _load_file_config(self, config_file: Path) -> dict[str, Any]:
        """
        Load configuration from YAML or JSON file

        Args:
            config_file: Path to configuration file

        Returns:
            Configuration dictionary

        Raises:
            ValueError: If file format is not supported
        """
        suffix = config_file.suffix.lower()
        if suffix in ('.yaml', '.yml'):
            with open(config_file) as f:
                return yaml.safe_load(f) or {}
        elif suffix == '.json':
            with open(config_file) as f:
                return json.load(f)
        else:
            raise ValueError(f'Unsupported configuration file format: {suffix}')

    def _load_env_file(self, env_file: Path) -> dict[str, Any]:
        """
        Load environment variables from .env file

        Args:
            env_file: Path to .env file

        Returns:
            Dictionary of environment variables
        """
        config = {}
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and (not line.startswith('#')) and ('=' in line):
                    key, value = line.split('=', 1)
                    value = value.strip().strip('"\'')
                    config[key] = self._convert_env_value(value)
        return config

    def _convert_env_value(self, value: str) -> Any:
        """
        Convert environment variable string to appropriate type

        Args:
            value: String value from environment variable

        Returns:
            Converted value (bool, int, float, or str)
        """
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def _merge_configs(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """
        Merge two configuration dictionaries with override taking precedence

        Args:
            base: Base configuration
            override: Override configuration

        Returns:
            Merged configuration
        """
        result = base.copy()
        result.update(override)
        return result

    def clear_cache(self) -> None:
        """Clear configuration cache"""
        self._config_cache = None

class ValidatedAITBCConfig(BaseSettings):
    """
    Validated AITBC configuration with schema checking.
    Extends BaseAITBCConfig with additional validation rules.
    """
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), env_file_encoding='utf-8', case_sensitive=False, extra='ignore')
    data_dir: Path = Field(default=DATA_DIR, description='AITBC data directory')
    config_dir: Path = Field(default=CONFIG_DIR, description='AITBC configuration directory')
    log_dir: Path = Field(default=LOG_DIR, description='AITBC log directory')
    app_name: str = Field(default='AITBC Application', description='Application name')
    app_version: str = Field(default='1.0.0', description='Application version')
    environment: str = Field(default='development', description='Environment (development/staging/production)')
    debug: bool = Field(default=False, description='Debug mode')
    log_level: str = Field(default='INFO', description='Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)')
    log_format: str = Field(default='%(asctime)s - %(name)s - %(levelname)s - %(message)s', description='Log format string')
    host: str = Field(default='0.0.0.0', description='Server host address')
    port: int = Field(default=8000, description='Server port')
    workers: int = Field(default=1, description='Number of worker processes')
    database_url: str | None = Field(default=None, description='Database connection URL')
    database_pool_size: int = Field(default=10, description='Database connection pool size')
    secret_key: str | None = Field(default=None, description='Application secret key')
    jwt_secret: str | None = Field(default=None, description='JWT secret key')
    jwt_algorithm: str = Field(default='HS256', description='JWT algorithm')
    jwt_expiration_hours: int = Field(default=24, description='JWT token expiration in hours')
    request_timeout: int = Field(default=30, description='Request timeout in seconds')
    max_request_size: int = Field(default=10 * 1024 * 1024, description='Max request size in bytes')

    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value"""
        valid_environments = ['development', 'staging', 'production', 'test']
        if v.lower() not in valid_environments:
            raise ValueError(f'Environment must be one of: {valid_environments}')
        return v.lower()

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level value"""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {valid_levels}')
        return v.upper()

    @field_validator('port')
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port number"""
        if not 1 <= v <= 65535:
            raise ValueError('Port must be between 1 and 65535')
        return v

    @field_validator('workers')
    @classmethod
    def validate_workers(cls, v: int) -> int:
        """Validate worker count"""
        if v < 1:
            raise ValueError('Workers must be at least 1')
        return v

    @field_validator('database_pool_size')
    @classmethod
    def validate_pool_size(cls, v: int) -> int:
        """Validate database pool size"""
        if v < 1:
            raise ValueError('Pool size must be at least 1')
        return v

    @field_validator('request_timeout')
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Validate request timeout"""
        if v < 1:
            raise ValueError('Request timeout must be at least 1 second')
        return v

    @model_validator(mode='after')
    def validate_production_settings(self) -> 'ValidatedAITBCConfig':
        """Validate production-specific settings"""
        if self.environment == 'production':
            if self.debug:
                raise ValueError('Debug mode should not be enabled in production')
            if not self.secret_key:
                raise ValueError('Secret key must be set in production')
            if not self.jwt_secret:
                raise ValueError('JWT secret must be set in production')
        return self

def load_config(config_file: Path | None=None, env_file: Path | None=None) -> ValidatedAITBCConfig:
    """
    Load and validate AITBC configuration from multiple sources

    Args:
        config_file: Path to configuration file (YAML or JSON)
        env_file: Path to environment file (.env)

    Returns:
        Validated AITBC configuration object

    Raises:
        ValidationError: If configuration validation fails
    """
    hierarchical_loader = HierarchicalConfig(config_file, env_file)
    hierarchical_loader.load_config()
    return ValidatedAITBCConfig()

def create_config_template(environment: str='development') -> dict[str, Any]:
    """
    Create configuration template for specific environment

    Args:
        environment: Environment name (development/staging/production)

    Returns:
        Configuration template dictionary
    """
    templates = {'development': {'environment': 'development', 'debug': True, 'log_level': 'DEBUG', 'host': '0.0.0.0', 'port': 8000, 'workers': 1}, 'staging': {'environment': 'staging', 'debug': False, 'log_level': 'INFO', 'host': '0.0.0.0', 'port': 8000, 'workers': 2}, 'production': {'environment': 'production', 'debug': False, 'log_level': 'WARNING', 'host': '0.0.0.0', 'port': 8000, 'workers': 4}}
    return templates.get(environment, templates['development'])