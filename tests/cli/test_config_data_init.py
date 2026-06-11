"""
Config Data Init Tests
Tests for configuration management
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestConfig:
    """Test Config dataclass"""

    def test_config_defaults(self):
        """Test Config with default values"""
        from config_data import Config
        
        config = Config()
        
        assert config.coordinator_url == "http://127.0.0.1:8011"
        assert config.api_key is None
        assert config.role is None
        assert config.blockchain_rpc_url == "http://127.0.0.1:8202"
        assert config.wallet_url == "http://127.0.0.1:8002"

    def test_config_custom_values(self):
        """Test Config with custom values (URLs enforced to localhost)"""
        from config_data import Config
        
        config = Config(
            coordinator_url="http://custom:8203",
            api_key="test_key",
            role="admin",
            blockchain_rpc_url="http://custom:8202"
        )
        
        # URLs are enforced to localhost in __post_init__
        assert config.coordinator_url == "http://localhost:8011"
        assert config.api_key == "test_key"
        assert config.role == "admin"

    @patch.dict('os.environ', {
        'AITBC_URL': 'http://env:8203',
        'AITBC_API_KEY': 'env_key',
        'AITBC_ROLE': 'client'
    })
    def test_config_env_override(self):
        """Test Config with environment variable overrides"""
        from config_data import Config
        
        config = Config()
        
        assert config.coordinator_url == "http://localhost:8011"  # Enforced to localhost
        assert config.api_key == "env_key"
        assert config.role == "client"

    def test_validate_localhost_urls(self):
        """Test localhost URL validation - non-localhost URLs are forced to localhost"""
        from config_data import Config
        
        # Use a non-localhost URL to trigger validation
        config = Config(
            coordinator_url="http://remote:8203",
            blockchain_rpc_url="http://remote:8202"
        )
        
        # Should force to localhost (127.0.0.1 is also valid localhost)
        assert config.coordinator_url in ["http://localhost:8011", "http://127.0.0.1:8011"]
        # blockchain_rpc_url should be forced to localhost (port may vary)
        assert config.blockchain_rpc_url.startswith(("http://localhost:", "http://127.0.0.1:"))

    def test_load_from_file(self):
        """Test loading config from file"""
        from config_data import Config
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_data = {
                'coordinator_url': 'http://file:8203',
                'api_key': 'file_key',
                'role': 'miner'
            }
            
            with open(config_file, 'w') as f:
                yaml.dump(config_data, f)
            
            config = Config(config_file=str(config_file))
            
            # Should be enforced to localhost
            assert config.coordinator_url == "http://localhost:8011"
            assert config.api_key == "file_key"
            assert config.role == "miner"

    def test_load_from_nonexistent_file(self):
        """Test loading from non-existent file"""
        from config_data import Config
        
        config = Config(config_file="/nonexistent/config.yaml")
        
        # Should use defaults
        assert config.coordinator_url == "http://127.0.0.1:8011"

    def test_save_to_file(self):
        """Test saving config to file"""
        from config_data import Config
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config = Config(
                config_file=str(config_file),
                coordinator_url="http://localhost:8011",
                api_key="test_key",
                role="admin"
            )
            
            config.save_to_file()
            
            assert config_file.exists()
            
            with open(config_file) as f:
                loaded_data = yaml.safe_load(f)
            
            assert loaded_data['coordinator_url'] == "http://localhost:8011"
            assert loaded_data['api_key'] == "test_key"
            assert loaded_data['role'] == "admin"

    def test_save_to_file_no_config_file(self):
        """Test saving when no config file is set"""
        from config_data import Config
        
        config = Config(config_file=None)
        
        # Should not raise error
        config.save_to_file()

    def test_role_based_config_file(self):
        """Test config file name based on role"""
        from config_data import Config
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            config = Config(role="admin", config_dir=config_dir)
            
            assert "admin-config.yaml" in config.config_file


class TestGetConfig:
    """Test get_config function"""

    def test_get_config_no_args(self):
        """Test get_config with no arguments"""
        from config_data import get_config
        
        config = get_config()
        
        assert config is not None
        assert config.coordinator_url == "http://127.0.0.1:8011"

    def test_get_config_with_role(self):
        """Test get_config with role"""
        from config_data import get_config
        
        config = get_config(role="client")
        
        assert config.role == "client"

    def test_get_config_with_file(self):
        """Test get_config with config file"""
        from config_data import get_config
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_data = {'coordinator_url': 'http://custom:8203'}
            
            with open(config_file, 'w') as f:
                yaml.dump(config_data, f)
            
            config = get_config(config_file=str(config_file))
            
            # Enforced to localhost
            assert config.coordinator_url == "http://localhost:8011"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
